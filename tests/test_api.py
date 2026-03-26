# tests/test_api.py
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def _mock_fetch_result(source_type="video", playlist_title=None):
    return {
        "videos": [{
            "video_id": "v1",
            "title": "Test Video",
            "upload_date": "2024-01-15",
            "channel": "Test Channel",
            "duration": 300,
            "url": "https://youtube.com/watch?v=v1",
            "playlist_title": playlist_title,
        }],
        "source_type": source_type,
        "channel": "Test Channel",
        "playlist_title": playlist_title,
    }


def test_fetch_returns_video_list():
    with patch("backend.main.list_videos", return_value=_mock_fetch_result()):
        response = client.post("/api/fetch", json={"url": "https://youtube.com/watch?v=v1"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["videos"]) == 1
    assert data["videos"][0]["video_id"] == "v1"
    assert data["source_type"] == "video"


def test_fetch_playlist_includes_playlist_title():
    with patch("backend.main.list_videos",
               return_value=_mock_fetch_result("playlist", "My Playlist")):
        response = client.post("/api/fetch", json={"url": "https://youtube.com/playlist?list=x"})
    assert response.status_code == 200
    assert response.json()["playlist_title"] == "My Playlist"


def test_get_fields_returns_list():
    response = client.get("/api/fields")
    assert response.status_code == 200
    fields = response.json()
    assert isinstance(fields, list)
    assert "title" in fields
    assert "upload_date" in fields
    assert "view_count" in fields
