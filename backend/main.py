# backend/main.py
import asyncio
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from fastapi.staticfiles import StaticFiles

from backend.downloader import get_video_folder, write_video_files
from backend.fetcher import (
    fetch_transcript_and_metadata,
    get_available_fields,
    list_videos,
)
from backend.models import (
    DownloadRequest,
    DownloadResponse,
    FetchRequest,
    FetchResponse,
    ProgressResponse,
    VideoInfo,
    VideoProgress,
)

app = FastAPI()

# In-memory job store: job_id -> {status, videos: {video_id -> {status, title, error}}}
_jobs: dict[str, dict] = {}


@app.post("/api/fetch", response_model=FetchResponse)
async def fetch_videos(request: FetchRequest) -> FetchResponse:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, list_videos, request.url)
    videos = [VideoInfo(**v) for v in result["videos"]]
    return FetchResponse(
        videos=videos,
        source_type=result["source_type"],
        channel=result.get("channel"),
        playlist_title=result.get("playlist_title"),
    )


@app.get("/api/fields")
async def get_fields() -> list[str]:
    return get_available_fields()


@app.post("/api/download", response_model=DownloadResponse)
async def start_download(
    request: DownloadRequest, background_tasks: BackgroundTasks
) -> DownloadResponse:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "videos": {
            vid_id: {"status": "pending", "title": vid_id, "error": None}
            for vid_id in request.video_ids
        },
    }
    background_tasks.add_task(_run_download, job_id, request)
    return DownloadResponse(job_id=job_id)


@app.get("/api/progress/{job_id}", response_model=ProgressResponse)
async def get_progress(job_id: str) -> ProgressResponse:
    job = _jobs.get(job_id)
    if not job:
        return ProgressResponse(job_id=job_id, status="unknown", videos=[])
    videos = [
        VideoProgress(
            video_id=vid_id,
            title=v["title"],
            status=v["status"],
            error=v["error"],
        )
        for vid_id, v in job["videos"].items()
    ]
    return ProgressResponse(job_id=job_id, status=job["status"], videos=videos)


async def _run_download(job_id: str, request: DownloadRequest) -> None:
    loop = asyncio.get_running_loop()
    for video_id in request.video_ids:
        _jobs[job_id]["videos"][video_id]["status"] = "downloading"
        try:
            url = request.video_urls[video_id]
            metadata, transcript = await loop.run_in_executor(
                None, fetch_transcript_and_metadata, url, request.fields
            )
            title = metadata.get("title") or video_id
            _jobs[job_id]["videos"][video_id]["title"] = title
            folder = get_video_folder(
                request.output_folder,
                request.channel_name or metadata.get("channel") or "Unknown",
                request.playlist_title,
                metadata.get("upload_date") or "0000-00-00",
                title,
            )
            write_video_files(folder, metadata, transcript)
            _jobs[job_id]["videos"][video_id]["status"] = "done"
        except Exception as exc:
            _jobs[job_id]["videos"][video_id]["status"] = "error"
            _jobs[job_id]["videos"][video_id]["error"] = str(exc)
    _jobs[job_id]["status"] = "done"


# Serve frontend — must come last so /api routes take priority
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
