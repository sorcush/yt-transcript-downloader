# tests/test_api.py
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import backend.store as store
from backend.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    # Point the store at a temp DB for every API test that touches favorites.
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "favorites.db")


def _wait_for_job(job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/progress/{job_id}").json()
        if data["status"] in ("done", "error", "cancelled"):
            return data
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def _save_payload():
    return {
        "url": "http://list",
        "name": "My List",
        "source_type": "playlist",
        "output_folder": "/out",
        "videos": [
            {"video_id": "v1", "title": "One", "upload_date": "2024-01-01",
             "channel": "Chan", "duration": 100, "url": "u1"},
        ],
    }


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


def test_pick_folder_returns_selected_path():
    with patch("backend.main.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "/tmp/output\n"
        run_mock.return_value.stderr = ""
        response = client.get("/api/pick-folder")

    assert response.status_code == 200
    assert response.json() == {"folder": "/tmp/output", "cancelled": False}


def test_pick_folder_marks_user_cancel_as_cancelled():
    with patch("backend.main.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 1
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = "execution error: User canceled. (-128)"
        response = client.get("/api/pick-folder")

    assert response.status_code == 200
    assert response.json() == {"folder": "", "cancelled": True}


def test_pick_folder_returns_error_details():
    with patch("backend.main.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 1
        run_mock.return_value.stdout = ""
        run_mock.return_value.stderr = "Not authorized to send Apple events"
        response = client.get("/api/pick-folder")

    assert response.status_code == 500
    assert "Not authorized to send Apple events" in response.json()["detail"]


def test_pick_folder_timeout_returns_server_error():
    with patch(
        "backend.main.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=120),
    ):
        response = client.get("/api/pick-folder")

    assert response.status_code == 500
    assert response.json()["detail"] == "Folder picker timed out."


def test_save_and_list_favorites():
    resp = client.post("/api/favorites", json=_save_payload())
    assert resp.status_code == 200
    fav_id = resp.json()["id"]

    listed = client.get("/api/favorites").json()
    assert len(listed) == 1
    assert listed[0]["name"] == "My List"
    assert listed[0]["output_folder"] == "/out"

    detail = client.get(f"/api/favorites/{fav_id}").json()
    assert detail["videos"][0]["video_id"] == "v1"
    assert detail["videos"][0]["has_transcript"] is False


def test_rename_and_delete_favorite():
    fav_id = client.post("/api/favorites", json=_save_payload()).json()["id"]
    assert client.post(f"/api/favorites/{fav_id}", json={"name": "Renamed"}).status_code == 200
    assert client.get(f"/api/favorites/{fav_id}").json()["name"] == "Renamed"
    assert client.delete(f"/api/favorites/{fav_id}").status_code == 200
    assert client.get(f"/api/favorites/{fav_id}").status_code == 404


def test_get_missing_favorite_404():
    assert client.get("/api/favorites/999").status_code == 404


def test_open_folder_invokes_open():
    with patch("backend.main.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 0
        resp = client.post("/api/open-folder", json={"folder": "~/Downloads"})
    assert resp.status_code == 200
    called_args = run_mock.call_args[0][0]
    assert called_args[0] == "open"
    assert called_args[1].endswith("/Downloads")  # expanduser applied


def test_open_folder_missing_path_errors():
    with patch("backend.main.subprocess.run") as run_mock:
        run_mock.return_value.returncode = 1
        run_mock.return_value.stderr = "No such file"
        resp = client.post("/api/open-folder", json={"folder": "/nope"})
    assert resp.status_code == 500


def test_download_with_favorite_writes_back():
    fav_id = client.post("/api/favorites", json=_save_payload()).json()["id"]
    payload = {
        "video_ids": ["v1"],
        "video_urls": {"v1": "u1"},
        "fields": ["title"],
        "output_folder": "/out",
        "download_transcript": True,
        "download_audio": False,
        "favorite_id": fav_id,
    }
    fake_return = ({"title": "One", "upload_date": "2024-01-01"}, "transcript text", None, "/tmp/xyz")
    with patch("backend.main.fetch_transcript_and_metadata", return_value=fake_return):
        with patch("backend.main.get_video_folder", return_value=Path("/tmp/x")):
            with patch("backend.main.write_video_files"):
                with patch("backend.main.shutil.rmtree"):
                    job_id = client.post("/api/download", json=payload).json()["job_id"]
                    _wait_for_job(job_id)

    detail = client.get(f"/api/favorites/{fav_id}").json()
    v1 = detail["videos"][0]
    assert v1["has_transcript"] is True
    assert v1["has_audio"] is False


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
               return_value=({"title": "T", "upload_date": "2024-01-15"}, "text", None, "/tmp/x")):
        with patch("backend.main.get_video_folder", return_value=Path("/tmp/x")):
            with patch("backend.main.write_video_files"):
                with patch("backend.main.shutil.rmtree"):
                    response = client.post("/api/download", json=_download_payload())
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_progress_returns_video_statuses():
    with patch("backend.main.fetch_transcript_and_metadata",
               return_value=({"title": "T", "upload_date": "2024-01-15"}, "text", None, "/tmp/x")):
        with patch("backend.main.get_video_folder", return_value=Path("/tmp/x")):
            with patch("backend.main.write_video_files"):
                with patch("backend.main.shutil.rmtree"):
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


def test_cancel_unknown_job_returns_unknown():
    response = client.post("/api/cancel/nonexistent-job-id")
    assert response.status_code == 200
    assert response.json()["status"] == "unknown"


def test_cancel_marks_pending_videos_as_cancelled():
    """Cancel a job by setting the flag directly, then verify pending videos become cancelled."""
    from backend.main import _jobs

    payload = {
        "video_ids": ["v1", "v2"],
        "video_urls": {
            "v1": "https://youtube.com/watch?v=v1",
            "v2": "https://youtube.com/watch?v=v2",
        },
        "fields": ["title"],
        "output_folder": "/tmp/test-output",
        "channel_name": "Test Channel",
    }

    call_count = 0

    def _fetch_and_cancel_after_first(url, fields, cookies=None, want_transcript=True, want_audio=False):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            for job in _jobs.values():
                if job["status"] == "running":
                    job["cancelled"] = True
            return ({"title": "V1", "upload_date": "2024-01-15"}, "text", None, "/tmp/x")
        return ({"title": "V2", "upload_date": "2024-01-16"}, "text", None, "/tmp/x")

    with patch("backend.main.fetch_transcript_and_metadata",
               side_effect=_fetch_and_cancel_after_first):
        with patch("backend.main.get_video_folder", return_value=Path("/tmp/x")):
            with patch("backend.main.write_video_files"):
                with patch("backend.main.shutil.rmtree"):
                    post_resp = client.post("/api/download", json=payload)
                    job_id = post_resp.json()["job_id"]

    resp = client.get(f"/api/progress/{job_id}")
    data = resp.json()
    assert data["status"] == "cancelled"
    statuses = {v["video_id"]: v["status"] for v in data["videos"]}
    # v1 cancelled after fetch (before file write); v2 cancelled before fetch
    assert statuses["v1"] == "cancelled"
    assert statuses["v2"] == "cancelled"
