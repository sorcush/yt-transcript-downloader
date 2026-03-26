from typing import Optional
from pydantic import BaseModel


class VideoInfo(BaseModel):
    video_id: str
    title: str
    upload_date: Optional[str] = None  # YYYY-MM-DD
    channel: Optional[str] = None
    duration: Optional[int] = None     # seconds
    url: str
    playlist_title: Optional[str] = None


class FetchRequest(BaseModel):
    url: str
    cookies_browser: Optional[str] = None


class FetchResponse(BaseModel):
    videos: list[VideoInfo]
    source_type: str           # 'video', 'playlist', 'channel'
    channel: Optional[str] = None
    playlist_title: Optional[str] = None


class VideoRef(BaseModel):
    video_id: str
    url: str


class DatesRequest(BaseModel):
    videos: list[VideoRef]
    cookies_browser: Optional[str] = None


class DownloadRequest(BaseModel):
    video_ids: list[str]
    video_urls: dict[str, str]  # video_id -> url
    fields: list[str]
    output_folder: str
    channel_name: Optional[str] = None
    playlist_title: Optional[str] = None
    cookies_browser: Optional[str] = None


class DownloadResponse(BaseModel):
    job_id: str


class VideoProgress(BaseModel):
    video_id: str
    title: str
    status: str                 # 'pending', 'downloading', 'done', 'error', 'cancelled'
    error: Optional[str] = None


class ProgressResponse(BaseModel):
    job_id: str
    status: str                 # 'running', 'done', 'error', 'cancelled'
    videos: list[VideoProgress]
