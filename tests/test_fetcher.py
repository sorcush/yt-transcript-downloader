from unittest.mock import patch, MagicMock
from backend.fetcher import list_videos, _format_date


def test_format_date_converts_yyyymmdd():
    assert _format_date("20240115") == "2024-01-15"


def test_format_date_handles_none():
    assert _format_date(None) == "0000-00-00"


def test_format_date_handles_short_string():
    assert _format_date("bad") == "bad"


def _make_ydl_mock(info):
    mock_ydl = MagicMock()
    mock_ydl.extract_info.return_value = info
    return mock_ydl


def test_list_videos_single_video():
    mock_info = {
        "id": "abc123",
        "title": "Test Video",
        "upload_date": "20240115",
        "channel": "Test Channel",
        "duration": 742,
        "webpage_url": "https://www.youtube.com/watch?v=abc123",
    }
    with patch("yt_dlp.YoutubeDL") as mock_cls:
        mock_cls.return_value.__enter__.return_value = _make_ydl_mock(mock_info)
        result = list_videos("https://www.youtube.com/watch?v=abc123")

    assert result["source_type"] == "video"
    assert len(result["videos"]) == 1
    v = result["videos"][0]
    assert v["video_id"] == "abc123"
    assert v["upload_date"] == "2024-01-15"
    assert v["channel"] == "Test Channel"


def test_list_videos_playlist_sorted_oldest_first():
    mock_info = {
        "_type": "playlist",
        "playlist_title": "My Playlist",
        "channel": "Test Channel",
        "entries": [
            {"id": "v2", "title": "Video 2", "upload_date": "20240201",
             "channel": "Test Channel", "duration": 600,
             "url": "https://youtube.com/watch?v=v2"},
            {"id": "v1", "title": "Video 1", "upload_date": "20240101",
             "channel": "Test Channel", "duration": 300,
             "url": "https://youtube.com/watch?v=v1"},
        ],
    }
    with patch("yt_dlp.YoutubeDL") as mock_cls:
        mock_cls.return_value.__enter__.return_value = _make_ydl_mock(mock_info)
        result = list_videos("https://www.youtube.com/playlist?list=PLxxx")

    assert result["source_type"] == "playlist"
    assert result["playlist_title"] == "My Playlist"
    assert len(result["videos"]) == 2
    assert result["videos"][0]["video_id"] == "v1"   # oldest first
    assert result["videos"][1]["video_id"] == "v2"
