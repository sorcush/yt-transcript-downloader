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


import time
from pathlib import Path


def _download_payload(video_ids=None, fields=None):
    return {
        "video_ids": video_ids or ["v1"],
        "video_urls": {"v1": "https://youtube.com/watch?v=v1"},
        "fields": fields or ["title", "upload_date"],
        "output_folder": "/tmp/test-output",
        "channel_name": "Test Channel",
        "playlist_title": None,
    }


def test_start_download_returns_job_id():
    with patch("backend.main.fetch_transcript_and_metadata",
               return_value=({"title": "T", "upload_date": "2024-01-15"}, "text")):
        with patch("backend.main.get_video_folder", return_value=Path("/tmp/x")):
            with patch("backend.main.write_video_files"):
                response = client.post("/api/download", json=_download_payload())
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_progress_returns_video_statuses():
    with patch("backend.main.fetch_transcript_and_metadata",
               return_value=({"title": "T", "upload_date": "2024-01-15"}, "text")):
        with patch("backend.main.get_video_folder", return_value=Path("/tmp/x")):
            with patch("backend.main.write_video_files"):
                post_resp = client.post("/api/download", json=_download_payload())
    job_id = post_resp.json()["job_id"]

    # Poll until done (background task runs in-process for TestClient)
    for _ in range(10):
        resp = client.get(f"/api/progress/{job_id}")
        if resp.json()["status"] == "done":
            break
        time.sleep(0.1)

    data = resp.json()
    assert data["status"] == "done"
    assert data["videos"][0]["video_id"] == "v1"
    assert data["videos"][0]["status"] == "done"


def test_progress_unknown_job_returns_unknown():
    response = client.get("/api/progress/nonexistent-job-id")
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"
