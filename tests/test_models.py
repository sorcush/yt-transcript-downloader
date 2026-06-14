import pytest
from pydantic import ValidationError
from backend.models import (
    VideoInfo, FetchRequest, FetchResponse,
    DownloadRequest, DownloadResponse, VideoProgress, ProgressResponse,
    SaveFavoriteRequest,
    RenameFavoriteRequest,
    OpenFolderRequest,
    FavoriteSummary,
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


def test_video_info_coerces_null_title():
    v = VideoInfo(video_id="abc", title=None, url="https://youtube.com/watch?v=abc")
    assert v.title == "Unknown"


def test_video_info_reconstructs_missing_url_from_id():
    v = VideoInfo(video_id="abc", title="T")
    assert v.url == "https://www.youtube.com/watch?v=abc"


def test_save_favorite_survives_one_malformed_video():
    # One bad video must not 422 the whole batch (which silently wiped the list).
    req = SaveFavoriteRequest(
        url="http://list", name="L", source_type="playlist", output_folder=None,
        videos=[
            {"video_id": "v1", "title": "Good", "url": "u1"},
            {"video_id": "v2", "title": None},  # deleted/private: no title, no url
        ],
    )
    assert len(req.videos) == 2
    assert req.videos[1].title == "Unknown"
    assert req.videos[1].url == "https://www.youtube.com/watch?v=v2"


def test_download_request_defaults():
    req = DownloadRequest(
        video_ids=["v1"], video_urls={"v1": "u1"}, fields=["title"],
        output_folder="/out",
    )
    assert req.download_transcript is True
    assert req.download_audio is False
    assert req.favorite_id is None


def test_download_request_requires_at_least_one_type():
    with pytest.raises(ValidationError):
        DownloadRequest(
            video_ids=["v1"], video_urls={"v1": "u1"}, fields=["title"],
            output_folder="/out", download_transcript=False, download_audio=False,
        )


def test_save_favorite_request_fields():
    req = SaveFavoriteRequest(
        url="http://list", name="My List", source_type="playlist",
        output_folder="/out",
        videos=[{"video_id": "v1", "title": "One", "url": "u1"}],
    )
    assert req.name == "My List"
    assert req.videos[0].video_id == "v1"


def test_open_folder_request():
    assert OpenFolderRequest(folder="~/Downloads").folder == "~/Downloads"
