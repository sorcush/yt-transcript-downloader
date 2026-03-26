# backend/main.py
import asyncio
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI

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
    loop = asyncio.get_event_loop()
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
