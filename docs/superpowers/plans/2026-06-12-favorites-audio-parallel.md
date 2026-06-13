# Favorites, Audio Downloads & Parallel Date Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add favorite playlists (persisted in SQLite with per-favorite output folder + Finder/copy-path actions), transcript/audio download selection, and parallel per-video date extraction to the YouTube Transcript Downloader.

**Architecture:** FastAPI backend + vanilla-JS frontend, single-user local app. A new `backend/store.py` module owns all SQLite access (the DB is the sole source of truth for download status). `backend/fetcher.py` gains a thread-pooled date fetcher and download-type-aware extraction. `backend/main.py` orchestrates new favorites/open-folder endpoints and writes download results back to the store.

**Tech Stack:** Python 3.13, FastAPI, yt-dlp, stdlib `sqlite3`, pytest + `unittest.mock`, vanilla JS/HTML/CSS.

**Spec:** `docs/superpowers/specs/2026-06-12-favorites-audio-parallel-design.md`

**Deviation from spec (flagged):** The spec suggested folding the `_probe_language` extraction into the main download extraction. Doing that safely requires fragile yt-dlp-internal calls (`process_ie_result` with mutated params). This plan instead keeps `_probe_language` for the transcript path (unchanged cost vs. today) and rides the audio download along on the *same* extraction that downloads subtitles — so no extra extraction is added for audio, and audio-only downloads skip language probing entirely (single extraction). Net effect matches the spec's intent (no new round-trips) with lower risk.

---

## File Structure

**Created:**
- `backend/store.py` — all SQLite access for favorites + per-video download state.
- `tests/test_store.py` — unit tests for the store (temp DB).

**Modified:**
- `backend/fetcher.py` — parallel `iter_dates`; download-type-aware `fetch_transcript_and_metadata`; `_find_audio` helper.
- `backend/downloader.py` — `move_audio` helper; `write_video_files` skips transcript when `None`.
- `backend/models.py` — favorites models, `OpenFolderRequest`, extend `DownloadRequest`, add download flags to `VideoInfo`-style favorite rows.
- `backend/main.py` — favorites endpoints, `/api/open-folder`, download write-back, parallel-dates unchanged contract.
- `frontend/index.html` — favorites dropdown + save field, download-type checkboxes, Open-in-Finder / Copy-path buttons.
- `frontend/app.js` — favorites state + wiring, badges, output-folder autofill, folder actions.
- `frontend/style.css` — styling for new controls + T/A badges.
- `tests/test_fetcher.py`, `tests/test_downloader.py`, `tests/test_api.py` — new/updated tests.
- `.gitignore` — add `data/`.

---

## Task 1: Parallel date extraction

**Files:**
- Modify: `backend/fetcher.py` (`iter_dates`, add `_fetch_one_date`, add `DATE_FETCH_WORKERS`)
- Test: `tests/test_fetcher.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_fetcher.py`:

```python
from backend.fetcher import iter_dates


def test_iter_dates_returns_all_results_parallel():
    infos = {
        "https://youtube.com/watch?v=v1": {"upload_date": "20240101"},
        "https://youtube.com/watch?v=v2": {"upload_date": "20240202"},
        "https://youtube.com/watch?v=v3": {"upload_date": None},
    }

    def fake_extract(url, download=False):
        return infos[url]

    with patch("yt_dlp.YoutubeDL") as mock_cls:
        inst = mock_cls.return_value.__enter__.return_value
        inst.extract_info.side_effect = fake_extract
        videos = [("v1", "https://youtube.com/watch?v=v1"),
                  ("v2", "https://youtube.com/watch?v=v2"),
                  ("v3", "https://youtube.com/watch?v=v3")]
        results = dict(iter_dates(videos))

    assert results == {"v1": "2024-01-01", "v2": "2024-02-02", "v3": None}


def test_iter_dates_failure_yields_none():
    def boom(url, download=False):
        raise RuntimeError("network down")

    with patch("yt_dlp.YoutubeDL") as mock_cls:
        inst = mock_cls.return_value.__enter__.return_value
        inst.extract_info.side_effect = boom
        results = dict(iter_dates([("v1", "https://youtube.com/watch?v=v1")]))

    assert results == {"v1": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_fetcher.py::test_iter_dates_returns_all_results_parallel -v`
Expected: FAIL — current `iter_dates` shares one instance; test patches per-instance but still passes? It will pass on output but we are replacing the implementation. If it already passes, that's fine — proceed; the new impl must keep it passing. (The failure-mode test asserts the new contract regardless.)

- [ ] **Step 3: Replace `iter_dates` with a thread-pooled implementation**

In `backend/fetcher.py`, add the import at the top with the other imports:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

Add a module-level constant near `AVAILABLE_FIELDS`:

```python
# Number of concurrent workers for per-video date extraction.
DATE_FETCH_WORKERS = 8
```

Replace the existing `iter_dates` function (currently `backend/fetcher.py:49-62`) with:

```python
def _fetch_one_date(vid_id: str, url: str, browser: str | None):
    """Extract a single video's upload date in its own YoutubeDL instance."""
    opts = {"logger": _SilentLogger(), "quiet": True, "skip_download": True, "ignore_no_formats_error": True}
    _add_cookies(opts, browser)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return vid_id, _format_date(info.get("upload_date"))
    except Exception:
        return vid_id, None


def iter_dates(
    videos: list[tuple[str, str]], browser: str | None = None
):
    """Yield (video_id, date) for each video, extracting concurrently.

    A separate YoutubeDL instance is used per video (the instance is not
    safe to share across threads). Results are yielded as they complete,
    so order is not guaranteed; callers key results by video_id.
    """
    with ThreadPoolExecutor(max_workers=DATE_FETCH_WORKERS) as executor:
        futures = [executor.submit(_fetch_one_date, vid_id, url, browser) for vid_id, url in videos]
        for future in as_completed(futures):
            yield future.result()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_fetcher.py -v`
Expected: PASS (all fetcher tests, including the two new ones).

- [ ] **Step 5: Commit**

```bash
cd /Users/sandrey/Dev/yt-transcript-downloader
git add backend/fetcher.py tests/test_fetcher.py
git commit -m "perf: parallelize per-video date extraction"
```

---

## Task 2: SQLite store module

**Files:**
- Create: `backend/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_store.py`:

```python
import importlib
from pathlib import Path

import pytest

import backend.store as store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "favorites.db")
    return store


def _videos():
    return [
        {"video_id": "v1", "title": "One", "upload_date": "2024-01-01",
         "channel": "Chan", "duration": 100, "url": "u1"},
        {"video_id": "v2", "title": "Two", "upload_date": "2024-02-02",
         "channel": "Chan", "duration": 200, "url": "u2"},
    ]


def test_save_and_get_roundtrip(db):
    fav_id = db.save_favorite("http://list", "My List", "playlist", "/out", _videos())
    fav = db.get_favorite(fav_id)
    assert fav["name"] == "My List"
    assert fav["url"] == "http://list"
    assert fav["output_folder"] == "/out"
    assert len(fav["videos"]) == 2
    assert fav["videos"][0]["has_transcript"] is False
    assert fav["videos"][0]["has_audio"] is False


def test_list_favorites(db):
    db.save_favorite("http://a", "A", "playlist", None, [])
    db.save_favorite("http://b", "B", "channel", None, [])
    names = {f["name"] for f in db.list_favorites()}
    assert names == {"A", "B"}


def test_resaving_same_url_updates_not_duplicates(db):
    db.save_favorite("http://list", "Old Name", "playlist", "/out1", _videos())
    db.save_favorite("http://list", "New Name", "playlist", "/out2", _videos())
    favs = db.list_favorites()
    assert len(favs) == 1
    assert favs[0]["name"] == "New Name"
    assert favs[0]["output_folder"] == "/out2"


def test_mark_downloaded_sets_flags_and_metadata(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.mark_downloaded(fav_id, "v1", has_transcript=True, has_audio=False,
                       metadata={"title": "One"})
    fav = db.get_favorite(fav_id)
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["has_transcript"] is True
    assert v1["has_audio"] is False
    assert v1["metadata"] == {"title": "One"}


def test_mark_downloaded_does_not_unset_existing_flag(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.mark_downloaded(fav_id, "v1", has_transcript=True, has_audio=False, metadata={})
    db.mark_downloaded(fav_id, "v1", has_transcript=False, has_audio=True, metadata={})
    fav = db.get_favorite(fav_id)
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["has_transcript"] is True
    assert v1["has_audio"] is True


def test_upsert_videos_preserves_download_flags(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.mark_downloaded(fav_id, "v1", has_transcript=True, has_audio=True, metadata={"a": 1})
    new_videos = _videos() + [{"video_id": "v3", "title": "Three", "upload_date": "2024-03-03",
                               "channel": "Chan", "duration": 300, "url": "u3"}]
    db.upsert_videos(fav_id, new_videos)
    fav = db.get_favorite(fav_id)
    ids = {v["video_id"] for v in fav["videos"]}
    assert ids == {"v1", "v2", "v3"}
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["has_transcript"] is True and v1["has_audio"] is True


def test_upsert_does_not_overwrite_existing_date_with_none(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.upsert_videos(fav_id, [{"video_id": "v1", "title": "One", "upload_date": None,
                               "channel": "Chan", "duration": 100, "url": "u1"}])
    fav = db.get_favorite(fav_id)
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["upload_date"] == "2024-01-01"


def test_set_output_folder(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", "/a", [])
    db.set_output_folder(fav_id, "/b")
    assert db.get_favorite(fav_id)["output_folder"] == "/b"


def test_rename_favorite(db):
    fav_id = db.save_favorite("http://list", "Old", "playlist", None, [])
    db.rename_favorite(fav_id, "New")
    assert db.get_favorite(fav_id)["name"] == "New"


def test_delete_favorite_cascades(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.delete_favorite(fav_id)
    assert db.get_favorite(fav_id) is None
    assert db.list_favorites() == []


def test_get_missing_favorite_returns_none(db):
    assert db.get_favorite(999) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.store'` (or AttributeError once the file is partially present).

- [ ] **Step 3: Implement `backend/store.py`**

Create `backend/store.py`:

```python
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "favorites.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS favorite (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    source_type     TEXT,
    output_folder   TEXT,
    added_at        TEXT,
    last_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS video (
    favorite_id    INTEGER NOT NULL REFERENCES favorite(id) ON DELETE CASCADE,
    video_id       TEXT NOT NULL,
    title          TEXT,
    upload_date    TEXT,
    channel        TEXT,
    duration       INTEGER,
    url            TEXT,
    has_transcript INTEGER NOT NULL DEFAULT 0,
    has_audio      INTEGER NOT NULL DEFAULT 0,
    metadata_json  TEXT,
    PRIMARY KEY (favorite_id, video_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def _upsert_videos(conn: sqlite3.Connection, fav_id: int, videos: list[dict]) -> None:
    for v in videos:
        conn.execute(
            """
            INSERT INTO video (favorite_id, video_id, title, upload_date, channel, duration, url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(favorite_id, video_id) DO UPDATE SET
                title       = excluded.title,
                upload_date = COALESCE(excluded.upload_date, video.upload_date),
                channel     = excluded.channel,
                duration    = excluded.duration,
                url         = excluded.url
            """,
            (fav_id, v["video_id"], v.get("title"), v.get("upload_date"),
             v.get("channel"), v.get("duration"), v.get("url")),
        )


def save_favorite(url: str, name: str, source_type: str | None,
                  output_folder: str | None, videos: list[dict]) -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM favorite WHERE url = ?", (url,)).fetchone()
        if row:
            fav_id = row["id"]
            conn.execute(
                "UPDATE favorite SET name = ?, source_type = ?, output_folder = ?, last_fetched_at = ? WHERE id = ?",
                (name, source_type, output_folder, _now(), fav_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO favorite (url, name, source_type, output_folder, added_at, last_fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (url, name, source_type, output_folder, _now(), _now()),
            )
            fav_id = cur.lastrowid
        _upsert_videos(conn, fav_id, videos)
        conn.commit()
        return fav_id
    finally:
        conn.close()


def upsert_videos(fav_id: int, videos: list[dict]) -> None:
    conn = _connect()
    try:
        _upsert_videos(conn, fav_id, videos)
        conn.execute("UPDATE favorite SET last_fetched_at = ? WHERE id = ?", (_now(), fav_id))
        conn.commit()
    finally:
        conn.close()


def set_output_folder(fav_id: int, output_folder: str | None) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE favorite SET output_folder = ? WHERE id = ?", (output_folder, fav_id))
        conn.commit()
    finally:
        conn.close()


def rename_favorite(fav_id: int, name: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE favorite SET name = ? WHERE id = ?", (name, fav_id))
        conn.commit()
    finally:
        conn.close()


def delete_favorite(fav_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM favorite WHERE id = ?", (fav_id,))
        conn.commit()
    finally:
        conn.close()


def mark_downloaded(fav_id: int, video_id: str, has_transcript: bool,
                    has_audio: bool, metadata: dict) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE video SET
                has_transcript = CASE WHEN ? THEN 1 ELSE has_transcript END,
                has_audio      = CASE WHEN ? THEN 1 ELSE has_audio END,
                metadata_json  = ?
            WHERE favorite_id = ? AND video_id = ?
            """,
            (1 if has_transcript else 0, 1 if has_audio else 0,
             json.dumps(metadata, ensure_ascii=False), fav_id, video_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_favorites() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name, url, source_type, output_folder FROM favorite ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _video_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "video_id": r["video_id"],
        "title": r["title"],
        "upload_date": r["upload_date"],
        "channel": r["channel"],
        "duration": r["duration"],
        "url": r["url"],
        "has_transcript": bool(r["has_transcript"]),
        "has_audio": bool(r["has_audio"]),
        "metadata": json.loads(r["metadata_json"]) if r["metadata_json"] else None,
    }


def get_favorite(fav_id: int) -> dict | None:
    conn = _connect()
    try:
        fav = conn.execute(
            "SELECT id, name, url, source_type, output_folder, added_at, last_fetched_at "
            "FROM favorite WHERE id = ?",
            (fav_id,),
        ).fetchone()
        if fav is None:
            return None
        videos = conn.execute(
            "SELECT * FROM video WHERE favorite_id = ? ORDER BY upload_date",
            (fav_id,),
        ).fetchall()
        result = dict(fav)
        result["videos"] = [_video_row_to_dict(v) for v in videos]
        return result
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_store.py -v`
Expected: PASS (all 11 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/sandrey/Dev/yt-transcript-downloader
git add backend/store.py tests/test_store.py
git commit -m "feat: add SQLite favorites store"
```

---

## Task 3: Download-type-aware extraction (transcript and/or audio)

**Files:**
- Modify: `backend/fetcher.py` (`fetch_transcript_and_metadata`, add `_find_audio`)
- Modify: `backend/downloader.py` (add `move_audio`, make `write_video_files` skip `None` transcript)
- Test: `tests/test_fetcher.py`, `tests/test_downloader.py`

- [ ] **Step 1: Write failing tests for the downloader helpers**

Add to `tests/test_downloader.py`:

```python
from backend.downloader import move_audio, write_video_files


def test_write_video_files_skips_transcript_when_none():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        write_video_files(folder, {"title": "X"}, None)
        assert (folder / "metadata.json").exists()
        assert not (folder / "transcript.txt").exists()


def test_write_video_files_writes_transcript_when_present():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        write_video_files(folder, {"title": "X"}, "hello world")
        assert (folder / "transcript.txt").read_text(encoding="utf-8") == "hello world"


def test_move_audio_renames_to_audio_with_native_ext():
    with tempfile.TemporaryDirectory() as d:
        src_dir = Path(d) / "src"
        src_dir.mkdir()
        audio_src = src_dir / "vid123.m4a"
        audio_src.write_bytes(b"fake-audio")
        dest = Path(d) / "dest"
        dest.mkdir()
        move_audio(str(audio_src), dest)
        assert (dest / "audio.m4a").read_bytes() == b"fake-audio"
        assert not audio_src.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_downloader.py -v`
Expected: FAIL — `ImportError: cannot import name 'move_audio'`.

- [ ] **Step 3: Update `backend/downloader.py`**

Add `import shutil` at the top (alongside `import json`, `import re`).

Replace `write_video_files` (currently `backend/downloader.py:24-29`) with:

```python
def write_video_files(folder: Path, metadata: dict, transcript: str | None) -> None:
    """Write metadata.json (always) and transcript.txt (only if transcript given)."""
    with open(folder / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    if transcript is not None:
        with open(folder / "transcript.txt", "w", encoding="utf-8") as f:
            f.write(transcript)
```

Add at the end of `backend/downloader.py`:

```python
def move_audio(audio_path: str, folder: Path) -> None:
    """Move a downloaded audio file into folder, renamed to audio.<native-ext>."""
    ext = Path(audio_path).suffix
    shutil.move(audio_path, folder / f"audio{ext}")
```

- [ ] **Step 4: Run downloader tests to verify they pass**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_downloader.py -v`
Expected: PASS.

- [ ] **Step 5: Write failing test for `_find_audio` and the new `fetch_transcript_and_metadata` signature**

Add to `tests/test_fetcher.py`:

```python
import os
from backend.fetcher import _find_audio


def test_find_audio_ignores_subtitle_files(tmp_path):
    (tmp_path / "vid.en.json3").write_text("{}")
    (tmp_path / "vid.m4a").write_bytes(b"a")
    assert _find_audio(str(tmp_path), "vid") == str(tmp_path / "vid.m4a")


def test_find_audio_returns_none_when_absent(tmp_path):
    (tmp_path / "vid.en.json3").write_text("{}")
    assert _find_audio(str(tmp_path), "vid") is None
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_fetcher.py::test_find_audio_ignores_subtitle_files -v`
Expected: FAIL — `ImportError: cannot import name '_find_audio'`.

- [ ] **Step 7: Update `backend/fetcher.py`**

Add `import shutil` is NOT needed here. Add the `_find_audio` helper (place it after `_read_transcript`, around `backend/fetcher.py:138`):

```python
def _find_audio(tmpdir: str, video_id: str) -> str | None:
    """Return the path to the downloaded audio file (any non-json3 file for this id)."""
    for path in Path(tmpdir).glob(f"{video_id}.*"):
        if path.suffix != ".json3":
            return str(path)
    return None
```

Replace `fetch_transcript_and_metadata` (currently `backend/fetcher.py:161-201`) with the version below. Note the new keyword args and the **4-tuple** return `(metadata, transcript, audio_path, tmpdir)`. It uses `tempfile.mkdtemp()` (caller cleans up `tmpdir`):

```python
def fetch_transcript_and_metadata(
    url: str,
    fields: list[str],
    browser: str | None = None,
    want_transcript: bool = True,
    want_audio: bool = False,
) -> tuple[dict, str | None, str | None, str]:
    """Fetch metadata, and optionally transcript text and/or original audio.

    Downloads artifacts into a temp directory the caller is responsible for
    removing. Returns (metadata, transcript_or_None, audio_path_or_None, tmpdir).
    audio_path (if present) lives inside tmpdir until the caller moves it.
    """
    tmpdir = tempfile.mkdtemp()

    sub_langs: list[str] | None = None
    if want_transcript:
        lang = _probe_language(url, browser)
        if lang.startswith("en"):
            sub_langs = ["en", "en-US", "en-GB"]
        else:
            sub_langs = [lang]

    ydl_opts: dict = {
        "logger": _SilentLogger(),
        "quiet": True,
        "ignore_no_formats_error": True,
        "skip_download": not want_audio,
        "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
    }
    if want_audio:
        ydl_opts["format"] = "bestaudio/best"
    if want_transcript:
        ydl_opts["writesubtitles"] = True
        ydl_opts["writeautomaticsub"] = True
        ydl_opts["subtitleslangs"] = sub_langs
        ydl_opts["subtitlesformat"] = "json3"
    _add_cookies(ydl_opts, browser)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    metadata: dict = {}
    for field in fields:
        value = info.get(field)
        if field == "upload_date" and value:
            value = _format_date(value)
        metadata[field] = value

    video_id = info.get("id", "")
    transcript = _read_transcript(tmpdir, video_id) if want_transcript else None
    audio_path = _find_audio(tmpdir, video_id) if want_audio else None

    return metadata, transcript, audio_path, tmpdir
```

- [ ] **Step 8: Run fetcher tests to verify they pass**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_fetcher.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/sandrey/Dev/yt-transcript-downloader
git add backend/fetcher.py backend/downloader.py tests/test_fetcher.py tests/test_downloader.py
git commit -m "feat: support transcript and/or original audio downloads"
```

---

## Task 4: Models for download flags and favorites

**Files:**
- Modify: `backend/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_models.py` (create imports as needed at top):

```python
import pytest
from pydantic import ValidationError
from backend.models import (
    DownloadRequest,
    SaveFavoriteRequest,
    RenameFavoriteRequest,
    OpenFolderRequest,
    FavoriteSummary,
)


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_models.py -v`
Expected: FAIL — `ImportError` for the new model names.

- [ ] **Step 3: Update `backend/models.py`**

Add `field_validator` to the pydantic import and `model_validator`:

```python
from typing import Optional
from pydantic import BaseModel, model_validator
```

Add `has_transcript` / `has_audio` to `VideoInfo` (so saved favorite rows carry badge state):

```python
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
```

Replace `DownloadRequest` (currently `backend/models.py:37-42`) with:

```python
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
```

Add these new models at the end of `backend/models.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/sandrey/Dev/yt-transcript-downloader
git add backend/models.py tests/test_models.py
git commit -m "feat: add favorites + download-type request models"
```

---

## Task 5: Favorites + open-folder API endpoints; download write-back

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py` (note `Path` is already imported there; if not, add `from pathlib import Path`):

```python
import backend.store as store


@pytest.fixture(autouse=True)
def temp_store(tmp_path, monkeypatch):
    # Point the store at a temp DB for every API test that touches favorites.
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "favorites.db")


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
```

Also add this polling helper near the top of `tests/test_api.py` (after `client = TestClient(app)`), if an equivalent does not already exist:

```python
import time


def _wait_for_job(job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/api/progress/{job_id}").json()
        if data["status"] in ("done", "error", "cancelled"):
            return data
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")
```

> Note: if `tests/test_api.py` already has logic that waits for job completion, reuse it instead of adding `_wait_for_job`. Check existing download tests (around `backend.main.fetch_transcript_and_metadata` patches) before adding.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_api.py -v`
Expected: FAIL — new endpoints return 404 / `fetch_transcript_and_metadata` returns wrong arity.

- [ ] **Step 3: Update imports and `_run_download` in `backend/main.py`**

Add to the imports at the top of `backend/main.py`:

```python
import os
import shutil

from backend import store
from backend.models import (
    DatesRequest,
    DownloadRequest,
    DownloadResponse,
    FavoriteDetail,
    FavoriteSummary,
    FetchRequest,
    FetchResponse,
    OpenFolderRequest,
    ProgressResponse,
    RenameFavoriteRequest,
    SaveFavoriteRequest,
    VideoInfo,
    VideoProgress,
)
from backend.downloader import get_video_folder, move_audio, write_video_files
```

(Adjust the existing `from backend.models import (...)` and `from backend.downloader import (...)` lines to the above — do not duplicate them.)

Replace `_run_download` (currently `backend/main.py:167-194`) with:

```python
async def _run_download(job_id: str, request: DownloadRequest) -> None:
    loop = asyncio.get_running_loop()
    for video_id in request.video_ids:
        if _jobs[job_id]["cancelled"]:
            _jobs[job_id]["videos"][video_id]["status"] = "cancelled"
            continue
        _jobs[job_id]["videos"][video_id]["status"] = "downloading"
        tmpdir = None
        try:
            url = request.video_urls[video_id]
            metadata, transcript, audio_path, tmpdir = await loop.run_in_executor(
                None,
                lambda u=url: fetch_transcript_and_metadata(
                    u, request.fields, request.cookies_browser,
                    request.download_transcript, request.download_audio,
                ),
            )
            if _jobs[job_id]["cancelled"]:
                _jobs[job_id]["videos"][video_id]["status"] = "cancelled"
                continue
            title = metadata.get("title") or video_id
            _jobs[job_id]["videos"][video_id]["title"] = title
            folder = get_video_folder(
                request.output_folder,
                metadata.get("upload_date") or "unknown-date",
                title,
            )
            write_video_files(folder, metadata, transcript)
            audio_written = False
            if audio_path:
                move_audio(audio_path, folder)
                audio_written = True
            if request.favorite_id is not None:
                store.mark_downloaded(
                    request.favorite_id, video_id,
                    has_transcript=request.download_transcript and transcript is not None,
                    has_audio=audio_written,
                    metadata=metadata,
                )
                store.set_output_folder(request.favorite_id, request.output_folder)
            _jobs[job_id]["videos"][video_id]["status"] = "done"
        except Exception as exc:
            _jobs[job_id]["videos"][video_id]["status"] = "error"
            _jobs[job_id]["videos"][video_id]["error"] = str(exc)
        finally:
            if tmpdir:
                shutil.rmtree(tmpdir, ignore_errors=True)
    _jobs[job_id]["status"] = "cancelled" if _jobs[job_id]["cancelled"] else "done"
```

- [ ] **Step 4: Add the favorites + open-folder endpoints to `backend/main.py`**

Insert these endpoints after the `get_fields` endpoint (around `backend/main.py:86`) and before `pick_folder`:

```python
@app.get("/api/favorites", response_model=list[FavoriteSummary])
async def list_favorites() -> list[FavoriteSummary]:
    return [FavoriteSummary(**f) for f in store.list_favorites()]


@app.post("/api/favorites")
async def save_favorite(request: SaveFavoriteRequest) -> dict:
    if request.source_type == "video":
        raise HTTPException(status_code=400, detail="Single videos cannot be saved as favorites.")
    videos = [v.model_dump() for v in request.videos]
    fav_id = store.save_favorite(
        request.url, request.name, request.source_type, request.output_folder, videos
    )
    return {"id": fav_id}


@app.get("/api/favorites/{fav_id}", response_model=FavoriteDetail)
async def get_favorite(fav_id: int) -> FavoriteDetail:
    fav = store.get_favorite(fav_id)
    if fav is None:
        raise HTTPException(status_code=404, detail="Favorite not found.")
    return FavoriteDetail(
        id=fav["id"], name=fav["name"], url=fav["url"],
        source_type=fav["source_type"], output_folder=fav["output_folder"],
        videos=[VideoInfo(**{k: v[k] for k in
                             ("video_id", "title", "upload_date", "channel",
                              "duration", "url", "has_transcript", "has_audio")})
                for v in fav["videos"]],
    )


@app.post("/api/favorites/{fav_id}")
async def rename_favorite(fav_id: int, request: RenameFavoriteRequest) -> dict:
    if store.get_favorite(fav_id) is None:
        raise HTTPException(status_code=404, detail="Favorite not found.")
    store.rename_favorite(fav_id, request.name)
    return {"id": fav_id, "name": request.name}


@app.delete("/api/favorites/{fav_id}")
async def delete_favorite(fav_id: int) -> dict:
    store.delete_favorite(fav_id)
    return {"id": fav_id, "deleted": True}


@app.post("/api/open-folder")
async def open_folder(request: OpenFolderRequest) -> dict:
    loop = asyncio.get_running_loop()
    path = os.path.expanduser(request.folder.strip())

    def _open():
        return subprocess.run(["open", path], capture_output=True, text=True, timeout=30)

    if not request.folder.strip():
        raise HTTPException(status_code=400, detail="No folder path provided.")
    result = await loop.run_in_executor(None, _open)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=(result.stderr or "Unable to open folder.").strip())
    return {"opened": path}
```

> `VideoInfo` rows from a favorite always include `has_transcript`/`has_audio` (the store returns them); the dict-comprehension picks exactly the fields `VideoInfo` expects.

- [ ] **Step 5: Run the API tests to verify they pass**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest tests/test_api.py -v`
Expected: PASS (existing download tests still pass — note they patch `fetch_transcript_and_metadata`; update those existing patches to return the **4-tuple** if they currently return a 2-tuple — see Step 6).

- [ ] **Step 6: Fix pre-existing download tests for the new 4-tuple return**

The existing `tests/test_api.py` download tests patch `fetch_transcript_and_metadata` with a 2-tuple return (e.g. `return_value=({"title": "X"}, "transcript")`). Update each to the 4-tuple form:

```python
# before: return_value=({"title": "X"}, "transcript")
# after:
return_value=({"title": "X", "upload_date": "2024-01-01"}, "transcript", None, "/tmp/x")
```

And wrap those tests' `write_video_files` patch block with `with patch("backend.main.shutil.rmtree"):` so the `finally` cleanup of the fake tmpdir is a no-op. Run the full suite:

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest -v`
Expected: PASS (entire suite).

- [ ] **Step 7: Commit**

```bash
cd /Users/sandrey/Dev/yt-transcript-downloader
git add backend/main.py tests/test_api.py
git commit -m "feat: favorites + open-folder endpoints with download write-back"
```

---

## Task 6: Frontend — favorites, download types, badges, folder actions

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/style.css`

This task has no automated tests (no JS test framework in the repo); it ends with manual verification via the running app.

- [ ] **Step 1: Add controls to `frontend/index.html`**

In the `.input-row` command bar (currently `frontend/index.html:19-41`), add the favorites dropdown + star + inline save field as the first elements, and the folder action buttons after `browse-btn`. Replace the `<div class="input-row">…</div>` block with:

```html
        <div class="input-row">
          <select id="favorites-select" aria-label="Favorites">
            <option value="">★ Favorites…</option>
          </select>
          <button id="rename-fav-btn" type="button" title="Rename favorite" disabled>✎</button>
          <button id="delete-fav-btn" type="button" title="Delete favorite" disabled>🗑</button>
          <input id="url-input" type="text"
                 placeholder="Paste YouTube URL (video, playlist, or channel)">
          <button id="fetch-btn">Fetch</button>
          <button id="save-fav-btn" type="button" title="Save to favorites" disabled>☆</button>
          <input id="fav-name-input" type="text" class="hidden"
                 placeholder="Favorite name" aria-label="Favorite name">
          <button id="fav-name-confirm" type="button" class="hidden">Save</button>
          <span id="fetched-chip" class="status-chip"></span>
          <span id="dates-chip" class="status-chip">
            <span id="dates-chip-text"></span>
            <button id="dates-stop-btn" class="chip-stop">✕</button>
          </span>
          <input id="output-folder" type="text"
                 placeholder="e.g. ~/Downloads/transcripts"
                 aria-label="Output folder">
          <button id="browse-btn" type="button">Browse</button>
          <button id="open-folder-btn" type="button" title="Open in Finder">Open in Finder</button>
          <button id="copy-path-btn" type="button" title="Copy path">Copy path</button>
          <select id="browser-select" aria-label="Cookies from browser">
            <option value="">None</option>
            <option value="chrome" selected>Chrome</option>
            <option value="firefox">Firefox</option>
            <option value="safari">Safari</option>
            <option value="edge">Edge</option>
            <option value="brave">Brave</option>
            <option value="chromium">Chromium</option>
          </select>
        </div>
```

In the metadata side panel (currently `frontend/index.html:72-76`), add download-type checkboxes above the fields list. Replace the `<aside id="metadata-panel">…</aside>` block with:

```html
      <aside id="metadata-panel">
        <h2>Download</h2>
        <div id="download-types">
          <label class="field-label"><input type="checkbox" id="dl-transcript" checked> Transcript</label>
          <label class="field-label"><input type="checkbox" id="dl-audio"> Audio</label>
        </div>
        <h2>Metadata Fields</h2>
        <p class="panel-subtitle">Included in metadata.json</p>
        <div id="fields-list"></div>
      </aside>
```

Bump the asset cache-busting query (so the browser reloads): change `style.css?v=2` → `style.css?v=3` and `app.js?v=2` → `app.js?v=3` in `frontend/index.html`.

- [ ] **Step 2: Add DOM refs + state in `frontend/app.js`**

In the `state` object (currently `frontend/app.js:4-14`), add:

```javascript
  activeFavoriteId: null,
  favorites: [],
  downloadTranscript: true,
  downloadAudio: false,
```

In the DOM refs block (currently `frontend/app.js:17-33`), add:

```javascript
const favoritesSelect = document.getElementById('favorites-select');
const renameFavBtn   = document.getElementById('rename-fav-btn');
const deleteFavBtn   = document.getElementById('delete-fav-btn');
const saveFavBtn     = document.getElementById('save-fav-btn');
const favNameInput   = document.getElementById('fav-name-input');
const favNameConfirm = document.getElementById('fav-name-confirm');
const openFolderBtn  = document.getElementById('open-folder-btn');
const copyPathBtn    = document.getElementById('copy-path-btn');
const dlTranscript   = document.getElementById('dl-transcript');
const dlAudio        = document.getElementById('dl-audio');
```

- [ ] **Step 3: Wire listeners in `init()`**

In `init()` (currently `frontend/app.js:36-50`), add before `await loadFields();`:

```javascript
  favoritesSelect.addEventListener('change', handleFavoritePick);
  saveFavBtn.addEventListener('click', showSaveFavField);
  favNameConfirm.addEventListener('click', handleSaveFavorite);
  favNameInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleSaveFavorite(); });
  renameFavBtn.addEventListener('click', handleRenameFavorite);
  deleteFavBtn.addEventListener('click', handleDeleteFavorite);
  urlInput.addEventListener('input', () => {
    // Manually editing the URL detaches from the active favorite.
    if (state.activeFavoriteId != null) { state.activeFavoriteId = null; renderFavoritesDropdown(); }
  });
  openFolderBtn.addEventListener('click', handleOpenFolder);
  copyPathBtn.addEventListener('click', handleCopyPath);
  dlTranscript.addEventListener('change', () => { state.downloadTranscript = dlTranscript.checked; updateSelectionUI(); });
  dlAudio.addEventListener('change', () => { state.downloadAudio = dlAudio.checked; updateSelectionUI(); });
  await loadFavorites();
```

- [ ] **Step 4: Add favorites functions to `frontend/app.js`**

Append this block to the end of `frontend/app.js`:

```javascript
// ── Favorites ────────────────────────────────────────────────────────────────
async function loadFavorites() {
  try {
    const res = await fetch('/api/favorites');
    state.favorites = await res.json();
    renderFavoritesDropdown();
  } catch (err) {
    console.error('Failed to load favorites:', err);
  }
}

function renderFavoritesDropdown() {
  favoritesSelect.innerHTML = '<option value="">★ Favorites…</option>';
  for (const fav of state.favorites) {
    const opt = document.createElement('option');
    opt.value = String(fav.id);
    opt.textContent = fav.name;
    favoritesSelect.appendChild(opt);
  }
  favoritesSelect.value = state.activeFavoriteId ? String(state.activeFavoriteId) : '';
  const hasActive = state.activeFavoriteId != null;
  renameFavBtn.disabled = !hasActive;
  deleteFavBtn.disabled = !hasActive;
}

async function handleFavoritePick() {
  const id = favoritesSelect.value;
  if (!id) {
    state.activeFavoriteId = null;
    renderFavoritesDropdown();
    return;
  }
  state.activeFavoriteId = Number(id);
  const res = await fetch(`/api/favorites/${id}`);
  if (!res.ok) { setStatus('Failed to load favorite.', true); return; }
  const fav = await res.json();
  state.videos = fav.videos;
  state.selectedIds.clear();
  urlInput.value = fav.url;
  if (fav.output_folder) outputFolder.value = fav.output_folder;
  renderTable();
  renderFavoritesDropdown();
  setStatus(`Loaded "${fav.name}" (${fav.videos.length} videos)`);
}

function showSaveFavField() {
  favNameInput.value = state.playlistTitle || state.channel || '';
  favNameInput.classList.remove('hidden');
  favNameConfirm.classList.remove('hidden');
  favNameInput.focus();
}

function hideSaveFavField() {
  favNameInput.classList.add('hidden');
  favNameConfirm.classList.add('hidden');
}

async function handleSaveFavorite() {
  const name = favNameInput.value.trim();
  if (!name) { setStatus('Enter a name for the favorite.', true); return; }
  const payload = {
    url: urlInput.value.trim(),
    name,
    source_type: state.playlistTitle ? 'playlist' : 'channel',
    output_folder: outputFolder.value.trim() || null,
    videos: state.videos,
  };
  try {
    const res = await fetch('/api/favorites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Server error: ${res.status}`);
    }
    const { id } = await res.json();
    state.activeFavoriteId = id;
    hideSaveFavField();
    await loadFavorites();
    setStatus(`Saved "${name}" to favorites.`);
  } catch (err) {
    setStatus(`Save failed: ${err.message}`, true);
  }
}

async function handleRenameFavorite() {
  if (state.activeFavoriteId == null) return;
  const current = state.favorites.find(f => f.id === state.activeFavoriteId);
  const name = prompt('Rename favorite:', current ? current.name : '');
  if (!name || !name.trim()) return;
  await fetch(`/api/favorites/${state.activeFavoriteId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name.trim() }),
  });
  await loadFavorites();
  setStatus(`Renamed to "${name.trim()}".`);
}

async function handleDeleteFavorite() {
  if (state.activeFavoriteId == null) return;
  const current = state.favorites.find(f => f.id === state.activeFavoriteId);
  if (!confirm(`Delete favorite "${current ? current.name : ''}"?`)) return;
  await fetch(`/api/favorites/${state.activeFavoriteId}`, { method: 'DELETE' });
  state.activeFavoriteId = null;
  await loadFavorites();
  setStatus('Favorite deleted.');
}

// Merge a fresh fetch into the active favorite's saved videos: preserve
// download badges + known dates for existing videos, and keep videos that
// dropped out of the playlist.
function mergeFavoriteVideos(fetched) {
  const existing = new Map(state.videos.map(v => [v.video_id, v]));
  const seen = new Set();
  const merged = [];
  for (const f of fetched) {
    const prev = existing.get(f.video_id);
    merged.push({
      ...f,
      upload_date: f.upload_date || (prev && prev.upload_date) || null,
      has_transcript: prev ? prev.has_transcript : false,
      has_audio: prev ? prev.has_audio : false,
    });
    seen.add(f.video_id);
  }
  for (const v of state.videos) {
    if (!seen.has(v.video_id)) merged.push(v);  // kept: removed from playlist
  }
  return merged;
}

// Upsert the current video list into the active favorite (preserves flags
// server-side; updates dates as they fill in).
async function persistActiveFavorite() {
  if (state.activeFavoriteId == null) return;
  const fav = state.favorites.find(f => f.id === state.activeFavoriteId);
  if (!fav) return;
  try {
    await fetch('/api/favorites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: fav.url,
        name: fav.name,
        source_type: fav.source_type,
        output_folder: outputFolder.value.trim() || null,
        videos: state.videos,
      }),
    });
  } catch (err) {
    console.error('Failed to persist favorite:', err);
  }
}

// ── Output folder actions ────────────────────────────────────────────────────
async function handleOpenFolder() {
  const folder = outputFolder.value.trim();
  if (!folder) { setStatus('No output folder to open.', true); return; }
  try {
    const res = await fetch('/api/open-folder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Server error: ${res.status}`);
    }
  } catch (err) {
    setStatus(`Open failed: ${err.message}`, true);
  }
}

async function handleCopyPath() {
  const folder = outputFolder.value.trim();
  if (!folder) { setStatus('No output folder to copy.', true); return; }
  try {
    await navigator.clipboard.writeText(folder);
    setStatus('Path copied to clipboard.');
  } catch {
    setStatus('Copy failed (clipboard unavailable).', true);
  }
}
```

- [ ] **Step 5: Render T/A badges + enable save button + send download types**

In `renderTable()` (the per-row loop, currently around `frontend/app.js:225-233`), after creating `statusTd`, render saved badges from the video's flags. Replace:

```javascript
    const statusTd  = document.createElement('td');
    statusTd.className = 'col-status';
```

with:

```javascript
    const statusTd  = document.createElement('td');
    statusTd.className = 'col-status';
    renderBadges(statusTd, video.has_transcript, video.has_audio);
```

Add this helper near `setRowStatus` (end of file area):

```javascript
function renderBadges(td, hasTranscript, hasAudio) {
  td.innerHTML = '';
  if (hasTranscript) td.appendChild(makeBadge('T', 'badge-transcript'));
  if (hasAudio) td.appendChild(makeBadge('A', 'badge-audio'));
}

function makeBadge(text, cls) {
  const span = document.createElement('span');
  span.className = `dl-badge ${cls}`;
  span.textContent = text;
  return span;
}
```

In `renderTable()`, at the top after the empty-state check, enable the save button when a playlist/channel is loaded. After `bottomBar.classList.remove('hidden');` add:

```javascript
  saveFavBtn.disabled = !(state.playlistTitle || state.channel);
```

In `handleDownload()` (currently around `frontend/app.js:319-325`), add the download-type flags and favorite id to the POST body. Replace the `body: JSON.stringify({...})` for `/api/download` with:

```javascript
      body: JSON.stringify({
        video_ids: [...state.selectedIds],
        video_urls: videoUrls,
        fields: [...state.selectedFields],
        output_folder: folder,
        cookies_browser: browserSelect.value || null,
        download_transcript: state.downloadTranscript,
        download_audio: state.downloadAudio,
        favorite_id: state.activeFavoriteId,
      }),
```

In `updateSelectionUI()` (currently `frontend/app.js:275-281`), guard the download button so at least one type is selected. Replace:

```javascript
  downloadBtn.disabled = count === 0;
```

with:

```javascript
  downloadBtn.disabled = count === 0 || (!state.downloadTranscript && !state.downloadAudio);
```

In `pollProgress` / `setRowStatus`, when a video reaches `done`, refresh its badges from the corresponding type flags. In `pollProgress` (currently around `frontend/app.js:347-349`), replace the loop:

```javascript
    for (const v of data.videos) {
      setRowStatus(v.video_id, v.status, v.error);
    }
```

with:

```javascript
    for (const v of data.videos) {
      setRowStatus(v.video_id, v.status, v.error);
      if (v.status === 'done') {
        const video = state.videos.find(x => x.video_id === v.video_id);
        if (video) {
          if (state.downloadTranscript) video.has_transcript = true;
          if (state.downloadAudio) video.has_audio = true;
        }
      }
    }
```

And in `setRowStatus`, when status is `done`, show badges instead of a "Done" label. Replace the `labels` object and final `statusTd.innerHTML = ...` (currently `frontend/app.js:440-447`) with:

```javascript
  if (status === 'done') {
    const video = state.videos.find(x => x.video_id === videoId);
    renderBadges(statusTd, video && video.has_transcript, video && video.has_audio);
    return;
  }

  const labels = {
    pending:     'Pending',
    downloading: 'Downloading',
    error:       errorMsg ? `Error: ${errorMsg}` : 'Error',
  };

  statusTd.innerHTML = `<span class="status-badge status-${status}">${labels[status] || status}</span>`;
```

- [ ] **Step 6: Wire incremental fetch + persistence into `handleFetch` and `fetchDatesLazy`**

In `handleFetch` (currently `frontend/app.js:131-140`), replace:

```javascript
    const data = await res.json();
    state.videos = data.videos;
    state.channel = data.channel;
    state.playlistTitle = data.playlist_title;
    state.selectedIds.clear();
    renderTable();
    fetchedChip.textContent = `✓ ${data.videos.length} fetched`;
    fetchedChip.classList.remove('error');
    fetchedChip.classList.add('visible');
    fetchDatesLazy(data.videos);
```

with:

```javascript
    const data = await res.json();
    state.videos = state.activeFavoriteId != null
      ? mergeFavoriteVideos(data.videos)
      : data.videos;
    state.channel = data.channel;
    state.playlistTitle = data.playlist_title;
    state.selectedIds.clear();
    renderTable();
    fetchedChip.textContent = `✓ ${state.videos.length} fetched`;
    fetchedChip.classList.remove('error');
    fetchedChip.classList.add('visible');
    if (state.activeFavoriteId != null) await persistActiveFavorite();
    fetchDatesLazy(state.videos);
```

In `fetchDatesLazy`, persist freshly-fetched dates when a favorite is active. Replace the `finally` block (currently `frontend/app.js:420-422`):

```javascript
  } finally {
    datesChip.classList.remove('visible');
  }
```

with:

```javascript
  } finally {
    datesChip.classList.remove('visible');
    if (state.activeFavoriteId != null) persistActiveFavorite();
  }
```

- [ ] **Step 7: Add styles to `frontend/style.css`**

Append to `frontend/style.css`:

```css
/* Download-type badges in the status column */
.dl-badge {
  display: inline-block;
  min-width: 16px;
  padding: 1px 5px;
  margin-right: 4px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  text-align: center;
}
.badge-transcript { background: #4a9d6f; }
.badge-audio { background: #a9744a; }

/* Inline favorite-name save field */
#fav-name-input { max-width: 180px; }
#download-types { margin-bottom: 12px; }
#download-types .field-label { display: block; }
```

- [ ] **Step 8: Manual verification (run the app)**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && ./run.sh` and open http://localhost:8001.

Verify:
1. Paste a small playlist URL → Fetch → rows load, dates fill in (faster than before).
2. Check **Audio**, uncheck **Transcript** → select a video → Download Selected → confirm `audio.<ext>` appears in the per-video folder and no `transcript.txt`.
3. Click ☆ → inline name field appears prefilled → edit → Save → favorite appears in dropdown.
4. Pick the favorite from the dropdown → table renders instantly with T/A badges; URL + output folder autofill.
5. Click Fetch with the favorite active → only new videos get dates fetched; existing badges preserved.
6. Click **Open in Finder** → Finder opens the output folder. Click **Copy path** → path is in clipboard.
7. Rename (✎) and Delete (🗑) work and refresh the dropdown.

- [ ] **Step 9: Commit**

```bash
cd /Users/sandrey/Dev/yt-transcript-downloader
git add frontend/index.html frontend/app.js frontend/style.css
git commit -m "feat: favorites UI, download-type selection, badges, folder actions"
```

---

## Task 7: Gitignore the database

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `data/` to `.gitignore`**

Append a line `data/` to `.gitignore`.

- [ ] **Step 2: Verify it is ignored**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && git check-ignore data/favorites.db && echo IGNORED`
Expected: prints `data/favorites.db` then `IGNORED`.

- [ ] **Step 3: Commit**

```bash
cd /Users/sandrey/Dev/yt-transcript-downloader
git add .gitignore
git commit -m "chore: gitignore favorites database"
```

---

## Final verification

- [ ] **Run the full backend test suite**

Run: `cd /Users/sandrey/Dev/yt-transcript-downloader && python -m pytest -v`
Expected: PASS (test_fetcher, test_store, test_downloader, test_models, test_api).

- [ ] **Manual end-to-end** — repeat Task 6 Step 7 checklist once more against a real playlist, confirming favorites persist across a server restart (`./run.sh`, stop, restart, favorite still in dropdown with badges).
