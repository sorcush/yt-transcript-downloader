# YouTube Transcript Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web app that fetches YouTube video lists from a URL and downloads selected transcripts + metadata into a structured folder hierarchy.

**Architecture:** FastAPI Python backend uses yt-dlp to list videos (flat, no download) and fetch transcripts/metadata per video. Vanilla JS single-page frontend renders a table with checkboxes and a metadata field side panel. Downloads run as background jobs with progress polling.

**Tech Stack:** Python 3.11+, FastAPI, yt-dlp, uvicorn, pytest, vanilla JS (no build step)

---

## File Map

| File | Responsibility |
|------|---------------|
| `backend/__init__.py` | Package marker |
| `backend/models.py` | Pydantic request/response models |
| `backend/fetcher.py` | yt-dlp wrapper: list videos, fetch transcript + metadata |
| `backend/downloader.py` | Write metadata.json + transcript.txt to folder structure |
| `backend/main.py` | FastAPI app, all route definitions, background job runner |
| `frontend/index.html` | Single-page app shell |
| `frontend/style.css` | All styles |
| `frontend/app.js` | All UI logic: fetch, table, selection, download, polling |
| `requirements.txt` | Python dependencies |
| `run.sh` | Start server and open browser |
| `tests/__init__.py` | Package marker |
| `tests/test_fetcher.py` | Unit tests for fetcher |
| `tests/test_downloader.py` | Unit tests for downloader |
| `tests/test_api.py` | Integration tests for API endpoints |

---

### Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `run.sh`
- Create: `backend/__init__.py`
- Create: `tests/__init__.py`
- Create: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend frontend tests
touch backend/__init__.py tests/__init__.py
```

- [ ] **Step 2: Create requirements.txt**

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
yt-dlp>=2024.1.0
pytest>=8.0.0
httpx>=0.27.0
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 4: Create run.sh**

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")"
uvicorn backend.main:app --reload --port 8000 &
SERVER_PID=$!
sleep 1
echo "Server running at http://localhost:8000"
if command -v open &>/dev/null; then
    open http://localhost:8000
elif command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:8000
fi
wait $SERVER_PID
```

```bash
chmod +x run.sh
```

- [ ] **Step 5: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
.env
.superpowers/
```

- [ ] **Step 6: Commit**

```bash
git init
git add requirements.txt run.sh backend/__init__.py tests/__init__.py .gitignore
git commit -m "chore: project setup"
```

---

### Task 2: Pydantic Models

**Files:**
- Create: `backend/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.models'`

- [ ] **Step 3: Create backend/models.py**

```python
# backend/models.py
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


class FetchResponse(BaseModel):
    videos: list[VideoInfo]
    source_type: str           # 'video', 'playlist', 'channel'
    channel: Optional[str] = None
    playlist_title: Optional[str] = None


class DownloadRequest(BaseModel):
    video_ids: list[str]
    video_urls: dict[str, str]  # video_id -> url
    fields: list[str]
    output_folder: str
    channel_name: Optional[str] = None
    playlist_title: Optional[str] = None


class DownloadResponse(BaseModel):
    job_id: str


class VideoProgress(BaseModel):
    video_id: str
    title: str
    status: str                 # 'pending', 'downloading', 'done', 'error'
    error: Optional[str] = None


class ProgressResponse(BaseModel):
    job_id: str
    status: str                 # 'running', 'done', 'error'
    videos: list[VideoProgress]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/models.py tests/test_models.py
git commit -m "feat: add pydantic models"
```

---

### Task 3: Video Listing (fetcher)

**Files:**
- Create: `backend/fetcher.py` (partial — list_videos + _format_date)
- Create: `tests/test_fetcher.py` (partial)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fetcher.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fetcher.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.fetcher'`

- [ ] **Step 3: Create backend/fetcher.py with list_videos**

```python
# backend/fetcher.py
import json
import os
import tempfile
from pathlib import Path

import yt_dlp


# Curated list of common yt-dlp metadata fields shown in the UI panel
AVAILABLE_FIELDS: list[str] = [
    "id", "title", "description", "upload_date",
    "uploader", "channel", "channel_id", "channel_url",
    "duration", "view_count", "like_count", "comment_count",
    "tags", "categories", "thumbnail", "webpage_url",
    "playlist", "playlist_id", "playlist_title", "playlist_uploader",
    "is_live", "was_live", "age_limit",
]


def _format_date(date_str: str | None) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD. Returns '0000-00-00' for None."""
    if date_str and len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str or "0000-00-00"


def get_available_fields() -> list[str]:
    return AVAILABLE_FIELDS


def list_videos(url: str) -> dict:
    """Return video list and source info from a YouTube URL (no download)."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        playlist_title = info.get("playlist_title") or info.get("title")
        channel = info.get("channel") or info.get("uploader")
        source_type = "playlist" if info.get("playlist_title") else "channel"
    else:
        entries = [info]
        playlist_title = None
        channel = info.get("channel") or info.get("uploader")
        source_type = "video"

    videos = []
    for entry in entries:
        vid_id = entry.get("id", "")
        videos.append({
            "video_id": vid_id,
            "title": entry.get("title", "Unknown"),
            "upload_date": _format_date(entry.get("upload_date")),
            "channel": entry.get("channel") or entry.get("uploader") or channel,
            "duration": entry.get("duration"),
            "url": (
                entry.get("url")
                or entry.get("webpage_url")
                or f"https://www.youtube.com/watch?v={vid_id}"
            ),
            "playlist_title": playlist_title,
        })

    videos.sort(key=lambda v: v.get("upload_date") or "")
    return {
        "videos": videos,
        "source_type": source_type,
        "channel": channel,
        "playlist_title": playlist_title,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_fetcher.py -v
```

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/fetcher.py tests/test_fetcher.py
git commit -m "feat: add video listing via yt-dlp"
```

---

### Task 4: Transcript and Metadata Fetching

**Files:**
- Modify: `backend/fetcher.py` (add _read_transcript, fetch_transcript_and_metadata)
- Modify: `tests/test_fetcher.py` (add transcript tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fetcher.py`:

```python
import json
import tempfile
from backend.fetcher import _read_transcript, fetch_transcript_and_metadata


def test_read_transcript_parses_json3():
    json3_data = {
        "events": [
            {"tStartMs": 0, "dDurationMs": 2000,
             "segs": [{"utf8": "Hello world"}]},
            {"tStartMs": 2000, "dDurationMs": 2000,
             "segs": [{"utf8": " this is a test"}]},
        ]
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_file = Path(tmpdir) / "abc123.en.json3"
        sub_file.write_text(json.dumps(json3_data))
        result = _read_transcript(tmpdir, "abc123")

    assert result == "Hello world this is a test"


def test_read_transcript_returns_fallback_when_no_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = _read_transcript(tmpdir, "abc123")
    assert result == "No transcript available"


def test_read_transcript_skips_empty_segments():
    json3_data = {
        "events": [
            {"tStartMs": 0, "segs": [{"utf8": "Hello"}]},
            {"tStartMs": 500, "segs": [{"utf8": "\n"}]},   # newline-only, skip
            {"tStartMs": 1000, "segs": [{"utf8": "World"}]},
        ]
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        sub_file = Path(tmpdir) / "abc123.en.json3"
        sub_file.write_text(json.dumps(json3_data))
        result = _read_transcript(tmpdir, "abc123")

    assert result == "Hello World"


def test_fetch_transcript_and_metadata_formats_date():
    mock_info = {
        "id": "abc123",
        "title": "My Video",
        "upload_date": "20240115",
        "channel": "Test Channel",
        "duration": 300,
    }
    with patch("yt_dlp.YoutubeDL") as mock_cls:
        mock_ydl = MagicMock()
        mock_ydl.extract_info.return_value = mock_info
        mock_cls.return_value.__enter__.return_value = mock_ydl

        with tempfile.TemporaryDirectory():
            metadata, transcript = fetch_transcript_and_metadata(
                "https://youtube.com/watch?v=abc123",
                ["title", "upload_date", "channel"]
            )

    assert metadata["title"] == "My Video"
    assert metadata["upload_date"] == "2024-01-15"
    assert metadata["channel"] == "Test Channel"
    assert transcript == "No transcript available"   # no subtitle file in mock
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_fetcher.py::test_read_transcript_parses_json3 -v
```

Expected: `ImportError: cannot import name '_read_transcript'`

- [ ] **Step 3: Add _read_transcript and fetch_transcript_and_metadata to backend/fetcher.py**

Append to `backend/fetcher.py`:

```python
def _read_transcript(tmpdir: str, video_id: str) -> str:
    """Parse a yt-dlp json3 subtitle file into plain text (no timestamps)."""
    sub_files = list(Path(tmpdir).glob(f"{video_id}.*.json3"))
    if not sub_files:
        return "No transcript available"

    with open(sub_files[0], encoding="utf-8") as f:
        data = json.load(f)

    parts = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs)
        text = text.replace("\n", " ").strip()
        if text:
            parts.append(text)

    return " ".join(parts)


def fetch_transcript_and_metadata(url: str, fields: list[str]) -> tuple[dict, str]:
    """Fetch metadata and plain-text transcript for a single video URL.

    Downloads subtitle files to a temp directory (video itself is skipped).
    Returns (metadata_dict, transcript_text).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en-GB"],
            "subtitlesformat": "json3",
            "skip_download": True,
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        metadata: dict = {}
        for field in fields:
            value = info.get(field)
            if field == "upload_date" and value:
                value = _format_date(value)
            metadata[field] = value

        video_id = info.get("id", "")
        transcript = _read_transcript(tmpdir, video_id)

    return metadata, transcript
```

- [ ] **Step 4: Run all fetcher tests**

```bash
pytest tests/test_fetcher.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/fetcher.py tests/test_fetcher.py
git commit -m "feat: add transcript and metadata fetching"
```

---

### Task 5: File Output (downloader)

**Files:**
- Create: `backend/downloader.py`
- Create: `tests/test_downloader.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_downloader.py
import json
import tempfile
from pathlib import Path
from backend.downloader import sanitize_name, get_video_folder, write_video_files


def test_sanitize_name_removes_unsafe_chars():
    assert sanitize_name("Video: My/File") == "Video-MyFile"


def test_sanitize_name_collapses_whitespace():
    assert sanitize_name("  Hello   World  ") == "Hello-World"


def test_sanitize_name_truncates_to_100_chars():
    long_name = "A" * 150
    assert len(sanitize_name(long_name)) == 100


def test_get_video_folder_with_playlist():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = get_video_folder(tmpdir, "My Channel", "My Playlist", "2024-01-15", "My Video")
        assert folder.exists()
        assert folder == Path(tmpdir) / "My-Channel" / "My-Playlist" / "2024-01-15-My-Video"


def test_get_video_folder_without_playlist():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = get_video_folder(tmpdir, "My Channel", None, "2024-01-15", "My Video")
        assert folder == Path(tmpdir) / "My-Channel" / "2024-01-15-My-Video"


def test_write_video_files_creates_both_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        write_video_files(folder, {"title": "Test", "duration": 120}, "Hello transcript")
        assert (folder / "metadata.json").exists()
        assert (folder / "transcript.txt").exists()


def test_write_video_files_content():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = Path(tmpdir)
        write_video_files(folder, {"title": "Test"}, "Hello transcript")
        metadata = json.loads((folder / "metadata.json").read_text())
        assert metadata == {"title": "Test"}
        assert (folder / "transcript.txt").read_text() == "Hello transcript"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_downloader.py -v
```

Expected: `ModuleNotFoundError: No module named 'backend.downloader'`

- [ ] **Step 3: Create backend/downloader.py**

```python
# backend/downloader.py
import json
import re
from pathlib import Path


def sanitize_name(name: str) -> str:
    """Remove filesystem-unsafe characters and normalize whitespace."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "-", name.strip())
    return name[:100]


def get_video_folder(
    output_folder: str,
    channel: str,
    playlist_title: str | None,
    upload_date: str,
    title: str,
) -> Path:
    """Return the Path for a video's output folder, creating it if needed."""
    parts: list[str] = [output_folder, sanitize_name(channel)]
    if playlist_title:
        parts.append(sanitize_name(playlist_title))
    parts.append(f"{upload_date}-{sanitize_name(title)}")
    folder = Path(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_video_files(folder: Path, metadata: dict, transcript: str) -> None:
    """Write metadata.json and transcript.txt into folder."""
    with open(folder / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    with open(folder / "transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_downloader.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/downloader.py tests/test_downloader.py
git commit -m "feat: add file output (downloader)"
```

---

### Task 6: FastAPI App — Fetch and Fields Endpoints

**Files:**
- Create: `backend/main.py`
- Create: `tests/test_api.py` (partial)

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py::test_fetch_returns_video_list -v
```

Expected: `ModuleNotFoundError: No module named 'backend.main'`

- [ ] **Step 3: Create backend/main.py with fetch + fields endpoints**

```python
# backend/main.py
import asyncio
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_api.py::test_fetch_returns_video_list tests/test_api.py::test_fetch_playlist_includes_playlist_title tests/test_api.py::test_get_fields_returns_list -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat: add fetch and fields API endpoints"
```

---

### Task 7: Download and Progress Endpoints

**Files:**
- Modify: `backend/main.py` (add download, progress, run_download)
- Modify: `tests/test_api.py` (add download + progress tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`:

```python
import time
from unittest.mock import MagicMock


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api.py::test_start_download_returns_job_id -v
```

Expected: `AttributeError` or 404 — download endpoint not yet defined

- [ ] **Step 3: Add download/progress endpoints and background runner to backend/main.py**

Append to `backend/main.py` (after the `get_fields` function):

```python
@app.post("/api/download", response_model=DownloadResponse)
async def start_download(
    request: DownloadRequest, background_tasks: BackgroundTasks
) -> DownloadResponse:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "running",
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


async def _run_download(job_id: str, request: DownloadRequest) -> None:
    loop = asyncio.get_event_loop()
    for video_id in request.video_ids:
        _jobs[job_id]["videos"][video_id]["status"] = "downloading"
        try:
            url = request.video_urls[video_id]
            metadata, transcript = await loop.run_in_executor(
                None, fetch_transcript_and_metadata, url, request.fields
            )
            title = metadata.get("title") or video_id
            _jobs[job_id]["videos"][video_id]["title"] = title
            folder = get_video_folder(
                request.output_folder,
                request.channel_name or metadata.get("channel") or "Unknown",
                request.playlist_title,
                metadata.get("upload_date") or "0000-00-00",
                title,
            )
            write_video_files(folder, metadata, transcript)
            _jobs[job_id]["videos"][video_id]["status"] = "done"
        except Exception as exc:
            _jobs[job_id]["videos"][video_id]["status"] = "error"
            _jobs[job_id]["videos"][video_id]["error"] = str(exc)
    _jobs[job_id]["status"] = "done"


# Serve frontend — must come last so /api routes take priority
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
```

- [ ] **Step 4: Run all API tests**

```bash
pytest tests/test_api.py -v
```

Expected: all tests pass

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_api.py
git commit -m "feat: add download and progress API endpoints"
```

---

### Task 8: Frontend HTML and CSS

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/style.css`

- [ ] **Step 1: Create frontend/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>YouTube Transcript Tool</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <div id="app">
    <header>
      <h1>YouTube Transcript Tool</h1>
    </header>

    <main>
      <div id="main-area">

        <!-- URL fetch bar -->
        <div class="input-row">
          <input id="url-input" type="text"
                 placeholder="Paste YouTube URL (video, playlist, or channel)">
          <button id="fetch-btn">Fetch</button>
        </div>

        <!-- Output folder -->
        <div class="input-row">
          <label for="output-folder">Output folder:</label>
          <input id="output-folder" type="text"
                 placeholder="e.g. /Users/you/Downloads/transcripts">
        </div>

        <!-- Status / error message -->
        <div id="status-bar" class="hidden"></div>

        <!-- Video table -->
        <div id="table-wrapper">
          <div id="empty-state">Paste a URL above and click Fetch</div>
          <table id="video-table" class="hidden">
            <thead>
              <tr>
                <th class="col-check">
                  <input type="checkbox" id="select-all" title="Select all">
                </th>
                <th class="col-title">Title</th>
                <th class="col-date">Date</th>
                <th class="col-channel">Channel</th>
                <th class="col-duration">Duration</th>
                <th class="col-status">Status</th>
              </tr>
            </thead>
            <tbody id="video-tbody"></tbody>
          </table>
        </div>

        <!-- Bottom action bar -->
        <div id="bottom-bar" class="hidden">
          <span id="selection-count">0 selected</span>
          <button id="download-btn" disabled>↓ Download Selected</button>
        </div>

      </div>

      <!-- Metadata field side panel -->
      <aside id="metadata-panel">
        <h2>Metadata Fields</h2>
        <p class="panel-subtitle">Included in metadata.json</p>
        <div id="fields-list"></div>
      </aside>
    </main>
  </div>

  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create frontend/style.css**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #0f0f1a;
  color: #cdd6f4;
  min-height: 100vh;
}

#app { display: flex; flex-direction: column; height: 100vh; }

header {
  padding: 16px 24px;
  border-bottom: 1px solid #2a2a3e;
  background: #181825;
}

header h1 { font-size: 18px; font-weight: 600; color: #cba6f7; }

main {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* ── Main area ─────────────────────────────── */
#main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  overflow: hidden;
  border-right: 1px solid #2a2a3e;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-row label {
  font-size: 13px;
  color: #a6adc8;
  white-space: nowrap;
}

input[type="text"] {
  flex: 1;
  background: #1e1e2e;
  border: 1px solid #313244;
  border-radius: 6px;
  color: #cdd6f4;
  padding: 8px 12px;
  font-size: 14px;
  outline: none;
}

input[type="text"]:focus { border-color: #cba6f7; }

button {
  background: #cba6f7;
  color: #1e1e2e;
  border: none;
  border-radius: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

button:hover { background: #d0b4fa; }
button:disabled { background: #45475a; color: #6c7086; cursor: not-allowed; }

#status-bar {
  font-size: 13px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #1e1e2e;
  border: 1px solid #313244;
  color: #a6adc8;
}

#status-bar.error { border-color: #f38ba8; color: #f38ba8; }

/* ── Table ─────────────────────────────────── */
#table-wrapper {
  flex: 1;
  overflow-y: auto;
  border-radius: 8px;
  border: 1px solid #313244;
  background: #1e1e2e;
}

#empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 120px;
  color: #585b70;
  font-size: 14px;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

thead { position: sticky; top: 0; background: #181825; z-index: 1; }

th {
  padding: 10px 12px;
  text-align: left;
  color: #a6adc8;
  font-weight: 600;
  border-bottom: 1px solid #313244;
}

td {
  padding: 8px 12px;
  border-bottom: 1px solid #1a1a2e;
  vertical-align: middle;
}

tbody tr:hover { background: #26263a; }

.col-check { width: 36px; }
.col-date  { width: 110px; }
.col-channel { width: 150px; }
.col-duration { width: 80px; }
.col-status { width: 100px; }

td.muted { color: #6c7086; }

.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.status-pending     { background: #313244; color: #6c7086; }
.status-downloading { background: #1e3a5f; color: #89b4fa; }
.status-done        { background: #1e3a2e; color: #a6e3a1; }
.status-error       { background: #3a1e1e; color: #f38ba8; }

/* ── Bottom bar ────────────────────────────── */
#bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 4px;
}

#selection-count { font-size: 13px; color: #a6adc8; }

/* ── Side panel ────────────────────────────── */
#metadata-panel {
  width: 220px;
  flex-shrink: 0;
  padding: 16px;
  background: #181825;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

#metadata-panel h2 { font-size: 14px; font-weight: 600; color: #cdd6f4; }

.panel-subtitle { font-size: 11px; color: #585b70; }

#fields-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #a6adc8;
  cursor: pointer;
}

.field-label input[type="checkbox"] { cursor: pointer; accent-color: #cba6f7; }

/* ── Utilities ─────────────────────────────── */
.hidden { display: none !important; }
```

- [ ] **Step 3: Verify the frontend loads (requires backend running)**

```bash
# In one terminal:
uvicorn backend.main:app --port 8000

# Open http://localhost:8000 in a browser
# Expected: page loads, shows "YouTube Transcript Tool" header and empty state
```

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/style.css
git commit -m "feat: add frontend HTML and CSS"
```

---

### Task 9: Frontend JS — Fetch and Table

**Files:**
- Create: `frontend/app.js` (partial — init, fetch, render table, select logic, fields panel)

- [ ] **Step 1: Create frontend/app.js**

```javascript
// frontend/app.js

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  videos: [],          // VideoInfo objects from last /api/fetch
  channel: null,
  playlistTitle: null,
  selectedIds: new Set(),
  selectedFields: new Set(),
  pollTimer: null,
  currentJobId: null,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const urlInput       = document.getElementById('url-input');
const fetchBtn       = document.getElementById('fetch-btn');
const outputFolder   = document.getElementById('output-folder');
const statusBar      = document.getElementById('status-bar');
const emptyState     = document.getElementById('empty-state');
const videoTable     = document.getElementById('video-table');
const videoTbody     = document.getElementById('video-tbody');
const selectAll      = document.getElementById('select-all');
const bottomBar      = document.getElementById('bottom-bar');
const selectionCount = document.getElementById('selection-count');
const downloadBtn    = document.getElementById('download-btn');
const fieldsList     = document.getElementById('fields-list');

// ── Init ───────────────────────────────────────────────────────────────────
async function init() {
  await loadFields();
  fetchBtn.addEventListener('click', handleFetch);
  urlInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleFetch(); });
  selectAll.addEventListener('change', handleSelectAll);
  downloadBtn.addEventListener('click', handleDownload);
}

// ── Fields panel ───────────────────────────────────────────────────────────
const DEFAULT_FIELDS = new Set(['title', 'upload_date', 'channel', 'duration']);

async function loadFields() {
  const res = await fetch('/api/fields');
  const fields = await res.json();
  fieldsList.innerHTML = '';
  for (const field of fields) {
    const label = document.createElement('label');
    label.className = 'field-label';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = field;
    cb.checked = DEFAULT_FIELDS.has(field);
    if (cb.checked) state.selectedFields.add(field);
    cb.addEventListener('change', () => {
      if (cb.checked) state.selectedFields.add(field);
      else state.selectedFields.delete(field);
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(field));
    fieldsList.appendChild(label);
  }
}

// ── Fetch videos ───────────────────────────────────────────────────────────
async function handleFetch() {
  const url = urlInput.value.trim();
  if (!url) return;
  setStatus('Fetching…');
  fetchBtn.disabled = true;

  try {
    const res = await fetch('/api/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();
    state.videos = data.videos;
    state.channel = data.channel;
    state.playlistTitle = data.playlist_title;
    state.selectedIds.clear();
    renderTable();
    setStatus(`Fetched ${data.videos.length} video(s)`);
  } catch (err) {
    setStatus(`Error: ${err.message}`, true);
  } finally {
    fetchBtn.disabled = false;
  }
}

// ── Table rendering ────────────────────────────────────────────────────────
function renderTable() {
  videoTbody.innerHTML = '';

  if (state.videos.length === 0) {
    emptyState.classList.remove('hidden');
    videoTable.classList.add('hidden');
    bottomBar.classList.add('hidden');
    return;
  }

  emptyState.classList.add('hidden');
  videoTable.classList.remove('hidden');
  bottomBar.classList.remove('hidden');

  for (const video of state.videos) {
    const tr = document.createElement('tr');
    tr.dataset.videoId = video.video_id;

    const checkTd = document.createElement('td');
    checkTd.className = 'col-check';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.addEventListener('change', () => toggleSelect(video.video_id, cb.checked));
    checkTd.appendChild(cb);

    const titleTd  = document.createElement('td');
    const titleLink = document.createElement('a');
    titleLink.href = video.url;
    titleLink.target = '_blank';
    titleLink.textContent = video.title;
    titleLink.style.color = '#89b4fa';
    titleLink.style.textDecoration = 'none';
    titleTd.appendChild(titleLink);

    const dateTd    = makeTd(video.upload_date || '—', 'muted');
    const channelTd = makeTd(video.channel || '—', 'muted');
    const durTd     = makeTd(formatDuration(video.duration), 'muted');
    const statusTd  = document.createElement('td');
    statusTd.className = 'col-status';

    tr.appendChild(checkTd);
    tr.appendChild(titleTd);
    tr.appendChild(dateTd);
    tr.appendChild(channelTd);
    tr.appendChild(durTd);
    tr.appendChild(statusTd);
    videoTbody.appendChild(tr);
  }

  updateSelectionUI();
}

function makeTd(text, cls) {
  const td = document.createElement('td');
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

function formatDuration(seconds) {
  if (!seconds) return '—';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// ── Selection logic ────────────────────────────────────────────────────────
function toggleSelect(videoId, checked) {
  if (checked) state.selectedIds.add(videoId);
  else state.selectedIds.delete(videoId);
  updateSelectionUI();
}

function handleSelectAll() {
  const checked = selectAll.checked;
  for (const video of state.videos) {
    if (checked) state.selectedIds.add(video.video_id);
    else state.selectedIds.delete(video.video_id);
  }
  for (const cb of videoTbody.querySelectorAll('input[type="checkbox"]')) {
    cb.checked = checked;
  }
  updateSelectionUI();
}

function updateSelectionUI() {
  const count = state.selectedIds.size;
  selectionCount.textContent = `${count} selected`;
  downloadBtn.disabled = count === 0;
  selectAll.checked = count > 0 && count === state.videos.length;
  selectAll.indeterminate = count > 0 && count < state.videos.length;
}

// ── Status bar ─────────────────────────────────────────────────────────────
function setStatus(msg, isError = false) {
  statusBar.textContent = msg;
  statusBar.classList.remove('hidden', 'error');
  if (isError) statusBar.classList.add('error');
}

init();
```

- [ ] **Step 2: Manually verify in browser**

```bash
uvicorn backend.main:app --port 8000 --reload
```

Open http://localhost:8000. Verify:
- Page loads with empty state message
- Metadata fields panel shows all fields with defaults checked
- Paste a YouTube URL and click Fetch — table populates with videos sorted oldest first
- Checkboxes work; select-all works; "N selected" count updates; Download button enables when items are selected

- [ ] **Step 3: Commit**

```bash
git add frontend/app.js
git commit -m "feat: frontend fetch, table rendering, and selection logic"
```

---

### Task 10: Frontend JS — Download and Progress Polling

**Files:**
- Modify: `frontend/app.js` (add handleDownload, pollProgress, updateVideoStatus)

- [ ] **Step 1: Append download + polling logic to frontend/app.js**

```javascript
// ── Download + progress ────────────────────────────────────────────────────
async function handleDownload() {
  const folder = outputFolder.value.trim();
  if (!folder) {
    setStatus('Please enter an output folder path.', true);
    return;
  }
  if (state.selectedIds.size === 0) return;

  const videoUrls = {};
  for (const video of state.videos) {
    if (state.selectedIds.has(video.video_id)) {
      videoUrls[video.video_id] = video.url;
    }
  }

  // Mark all selected rows as pending
  for (const videoId of state.selectedIds) {
    setRowStatus(videoId, 'pending');
  }
  downloadBtn.disabled = true;
  setStatus('Starting download…');

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_ids: [...state.selectedIds],
        video_urls: videoUrls,
        fields: [...state.selectedFields],
        output_folder: folder,
        channel_name: state.channel,
        playlist_title: state.playlistTitle,
      }),
    });
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const { job_id } = await res.json();
    state.currentJobId = job_id;
    startPolling(job_id);
  } catch (err) {
    setStatus(`Download failed: ${err.message}`, true);
    downloadBtn.disabled = false;
  }
}

function startPolling(jobId) {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => pollProgress(jobId), 2000);
}

async function pollProgress(jobId) {
  try {
    const res = await fetch(`/api/progress/${jobId}`);
    const data = await res.json();

    for (const v of data.videos) {
      setRowStatus(v.video_id, v.status, v.error);
    }

    const total    = data.videos.length;
    const done     = data.videos.filter(v => v.status === 'done').length;
    const errors   = data.videos.filter(v => v.status === 'error').length;
    const active   = data.videos.filter(v => v.status === 'downloading').length;

    if (active > 0) {
      setStatus(`Downloading… ${done}/${total} done`);
    }

    if (data.status === 'done') {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      downloadBtn.disabled = false;
      const msg = errors > 0
        ? `Done. ${done} downloaded, ${errors} failed.`
        : `Done. ${done} video(s) downloaded to ${outputFolder.value.trim()}`;
      setStatus(msg, errors > 0);
    }
  } catch (err) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
    setStatus(`Polling error: ${err.message}`, true);
    downloadBtn.disabled = false;
  }
}

function setRowStatus(videoId, status, errorMsg) {
  const tr = videoTbody.querySelector(`tr[data-video-id="${videoId}"]`);
  if (!tr) return;
  const statusTd = tr.querySelector('.col-status');
  if (!statusTd) return;

  const labels = {
    pending:     'Pending',
    downloading: 'Downloading',
    done:        'Done',
    error:       errorMsg ? `Error: ${errorMsg}` : 'Error',
  };

  statusTd.innerHTML = `<span class="status-badge status-${status}">${labels[status] || status}</span>`;
}
```

- [ ] **Step 2: Manually verify end-to-end**

```bash
uvicorn backend.main:app --port 8000 --reload
```

Open http://localhost:8000 and test:
1. Paste a real YouTube video URL, click Fetch — video appears in table
2. Check the video, set an output folder path, click Download
3. Row shows "Downloading" badge, then "Done"
4. Check the output folder — `Channel/YYYY-MM-DD-Title/metadata.json` and `transcript.txt` exist
5. Open `transcript.txt` — plain text, no timestamps
6. Open `metadata.json` — contains only the fields you selected

- [ ] **Step 3: Run full test suite one final time**

```bash
pytest -v
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add frontend/app.js
git commit -m "feat: download trigger and progress polling"
```

---

## Done

The tool is fully functional. Run it with:

```bash
./run.sh
```
