from typing import Optional
from pydantic import BaseModel, model_validator


class VideoInfo(BaseModel):
    video_id: str
    title: str
    upload_date: Optional[str] = None  # YYYY-MM-DD
    channel: Optional[str] = None
    duration: Optional[int] = None     # seconds
    url: str
    playlist_title: Optional[str] = None
    has_transcript: bool = False
    has_audio: bool = False


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
    cookies_browser: Optional[str] = None
    download_transcript: bool = True
    download_audio: bool = False
    favorite_id: Optional[int] = None

    @model_validator(mode="after")
    def _at_least_one_type(self):
        if not self.download_transcript and not self.download_audio:
            raise ValueError("At least one of download_transcript or download_audio must be true.")
        return self


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


class SaveFavoriteRequest(BaseModel):
    url: str
    name: str
    source_type: Optional[str] = None
    output_folder: Optional[str] = None
    videos: list[VideoInfo]


class RenameFavoriteRequest(BaseModel):
    name: str


class OpenFolderRequest(BaseModel):
    folder: str


class FavoriteSummary(BaseModel):
    id: int
    name: str
    url: str
    source_type: Optional[str] = None
    output_folder: Optional[str] = None


class FavoriteDetail(BaseModel):
    id: int
    name: str
    url: str
    source_type: Optional[str] = None
    output_folder: Optional[str] = None
    videos: list[VideoInfo]
