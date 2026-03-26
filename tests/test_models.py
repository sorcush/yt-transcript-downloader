from backend.models import (
    VideoInfo, FetchRequest, FetchResponse,
    DownloadRequest, DownloadResponse, VideoProgress, ProgressResponse
)

def test_video_info_defaults():
    v = VideoInfo(
        video_id="abc",
        title="Test",
        upload_date="2024-01-15",
        channel="Chan",
        duration=120,
        url="https://youtube.com/watch?v=abc",
    )
    assert v.playlist_title is None

def test_download_request_requires_fields():
    req = DownloadRequest(
        video_ids=["abc"],
        video_urls={"abc": "https://youtube.com/watch?v=abc"},
        fields=["title"],
        output_folder="/tmp/out",
    )
    assert req.channel_name is None
    assert req.playlist_title is None
