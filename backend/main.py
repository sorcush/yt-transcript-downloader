# backend/main.py
import asyncio
import json
import subprocess
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.downloader import get_video_folder, write_video_files
from backend.fetcher import (
    fetch_date,
    fetch_transcript_and_metadata,
    get_available_fields,
    iter_dates,
    list_videos,
)
from backend.models import (
    DatesRequest,
    DownloadRequest,
    DownloadResponse,
    FetchRequest,
    FetchResponse,
    ProgressResponse,
    VideoInfo,
    VideoProgress,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown: cancel all running jobs
    for job in _jobs.values():
        if job["status"] == "running":
            job["cancelled"] = True


app = FastAPI(lifespan=lifespan)

# In-memory job store: job_id -> {status, cancelled, videos: {video_id -> {status, title, error}}}
_jobs: dict[str, dict] = {}


@app.post("/api/fetch", response_model=FetchResponse)
async def fetch_videos(request: FetchRequest) -> FetchResponse:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, list_videos, request.url, request.cookies_browser)
    videos = [VideoInfo(**v) for v in result["videos"]]
    return FetchResponse(
        videos=videos,
        source_type=result["source_type"],
        channel=result.get("channel"),
        playlist_title=result.get("playlist_title"),
    )


@app.post("/api/dates")
async def stream_dates(request: DatesRequest) -> StreamingResponse:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _fetch_all():
        videos = [(v.video_id, v.url) for v in request.videos]
        for video_id, date in iter_dates(videos, request.cookies_browser):
            loop.call_soon_threadsafe(queue.put_nowait, (video_id, date))
        loop.call_soon_threadsafe(queue.put_nowait, None)

    async def generate():
        loop.run_in_executor(None, _fetch_all)
        while True:
            item = await queue.get()
            if item is None:
                break
            video_id, date = item
            yield f"data: {json.dumps({'video_id': video_id, 'upload_date': date})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/fields")
async def get_fields() -> list[str]:
    return get_available_fields()


@app.get("/api/pick-folder")
async def pick_folder() -> dict:
    loop = asyncio.get_running_loop()

    def _pick():
        try:
            result = subprocess.run(
                ["osascript", "-e", 'POSIX path of (choose folder with prompt "Choose output folder")'],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return {"folder": "", "cancelled": False, "error": "Folder picker timed out."}

        if result.returncode == 0:
            return {"folder": result.stdout.strip(), "cancelled": False, "error": None}

        stderr = (result.stderr or "").strip()
        is_cancelled = "(-128)" in stderr or "User canceled" in stderr
        if is_cancelled:
            return {"folder": "", "cancelled": True, "error": None}

        return {
            "folder": "",
            "cancelled": False,
            "error": stderr or "Unable to open folder picker.",
        }

    result = await loop.run_in_executor(None, _pick)
    if result["error"]:
        raise HTTPException(status_code=500, detail=result["error"])
    return {"folder": result["folder"], "cancelled": result["cancelled"]}


@app.post("/api/download", response_model=DownloadResponse)
async def start_download(
    request: DownloadRequest, background_tasks: BackgroundTasks
) -> DownloadResponse:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
        "cancelled": False,
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


@app.post("/api/cancel/{job_id}")
async def cancel_job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        return {"job_id": job_id, "status": "unknown"}
    job["cancelled"] = True
    return {"job_id": job_id, "status": "cancelled"}


async def _run_download(job_id: str, request: DownloadRequest) -> None:
    loop = asyncio.get_running_loop()
    for video_id in request.video_ids:
        if _jobs[job_id]["cancelled"]:
            _jobs[job_id]["videos"][video_id]["status"] = "cancelled"
            continue
        _jobs[job_id]["videos"][video_id]["status"] = "downloading"
        try:
            url = request.video_urls[video_id]
            metadata, transcript = await loop.run_in_executor(
                None, fetch_transcript_and_metadata, url, request.fields, request.cookies_browser
            )
            if _jobs[job_id]["cancelled"]:
                _jobs[job_id]["videos"][video_id]["status"] = "cancelled"
                continue
            title = metadata.get("title") or video_id
            _jobs[job_id]["videos"][video_id]["title"] = title
            folder = get_video_folder(
                request.output_folder,
                metadata.get("upload_date") or "unknown-date",
                title,
            )
            write_video_files(folder, metadata, transcript)
            _jobs[job_id]["videos"][video_id]["status"] = "done"
        except Exception as exc:
            _jobs[job_id]["videos"][video_id]["status"] = "error"
            _jobs[job_id]["videos"][video_id]["error"] = str(exc)
    _jobs[job_id]["status"] = "cancelled" if _jobs[job_id]["cancelled"] else "done"


# Serve frontend — must come last so /api routes take priority
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
