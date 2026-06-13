# Design: Favorites, Audio Downloads & Parallel Date Extraction

**Date:** 2026-06-12
**Status:** Approved (pending spec review)

## Summary

Three related improvements to the YouTube Transcript Downloader:

1. **Parallel date extraction** — speed up the slow per-video date fetch (`/api/dates`) by running extractions concurrently.
2. **Favorite playlists** — save playlists/channels to a persistent SQLite store, re-open them instantly with their saved state, and incrementally re-fetch new videos.
3. **Download type selection** — choose Transcript and/or original Audio per download; persist what's been downloaded and show it as status badges.

The app is a single-user local tool (FastAPI + vanilla JS, run via `run.sh`). These features stay within that footprint and add no third-party dependencies (SQLite via stdlib `sqlite3`).

## Goals

- Browsing a large playlist no longer blocks on serial per-video network calls.
- Users can name and revisit favorite playlists without re-fetching everything.
- Users can download original audio alongside (or instead of) transcripts.
- The video list shows, per video, what has already been downloaded (transcript / audio).

## Non-Goals

- Favoriting single videos (only playlist/channel URLs are favoritable).
- Verifying downloads against the filesystem — the database is the source of truth.
- Re-encoding/transcoding audio (original stream only; no ffmpeg requirement).
- Saving transcript text into the database (only metadata is saved).

---

## 1. Parallel Date Extraction

### Current behavior
`backend/fetcher.py:iter_dates` loops over videos serially, reusing one `YoutubeDL` instance, doing a full `extract_info` per video. `/api/dates` streams results over SSE to the frontend ("Dates X/N" progress). For an N-video channel this is N sequential network round-trips.

### Change
Replace the serial loop with a `concurrent.futures.ThreadPoolExecutor`.

- Default **8 workers**, defined as a module-level constant (`DATE_FETCH_WORKERS = 8`).
- Each task creates its **own** `YoutubeDL` instance (the instance is not safe to share across threads). Cookie options are applied per instance as today.
- Results are pushed to the existing `asyncio.Queue` in `/api/dates` as each task completes, via `loop.call_soon_threadsafe`. The SSE contract is unchanged.
- Arrival order is irrelevant: the frontend already updates cells by `video_id`.
- Only videos **without a known `upload_date`** are queued. When a favorite is re-opened, already-saved videos are skipped, so only genuinely new videos hit the network.

### Notes
- Exceptions per video are swallowed and yield `date = None` (current behavior preserved).
- Cancellation: the existing client-side `AbortController` aborts the SSE stream; the executor's in-flight tasks are allowed to finish (best effort). No new cancellation API required.

---

## 2. SQLite Persistence

### Store
A single SQLite file at `data/favorites.db` (repo-relative), independent of the user's chosen output folder. Managed by a new module `backend/store.py` using stdlib `sqlite3` — no ORM, no new dependencies. The module exposes a thin data-access API (functions, not classes), creates the `data/` directory if missing, and ensures the schema exists on first use.

**Implementation step:** add `data/` to `.gitignore` (it is not currently ignored).

### Schema

```sql
CREATE TABLE IF NOT EXISTS favorite (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,            -- user-supplied label
    source_type   TEXT,                     -- 'playlist' | 'channel'
    output_folder TEXT,                     -- remembered download folder for this favorite
    added_at      TEXT,                     -- ISO timestamp
    last_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS video (
    favorite_id    INTEGER NOT NULL REFERENCES favorite(id) ON DELETE CASCADE,
    video_id       TEXT NOT NULL,
    title          TEXT,
    upload_date    TEXT,                    -- YYYY-MM-DD
    channel        TEXT,
    duration       INTEGER,                 -- seconds
    url            TEXT,
    has_transcript INTEGER NOT NULL DEFAULT 0,
    has_audio      INTEGER NOT NULL DEFAULT 0,
    metadata_json  TEXT,                    -- downloaded metadata fields, JSON; NULL until downloaded
    PRIMARY KEY (favorite_id, video_id)
);
```

### Source of truth
Download status (`has_transcript`, `has_audio`) and saved `metadata_json` come **only** from this database. The app does not scan the output folder. Consequence: if a user manually deletes files on disk, the badges still show "downloaded" until the favorite is cleared or re-downloaded. This is an accepted trade-off (chosen for instant, network-free re-open).

### Data-access API (illustrative)
- `list_favorites() -> list[dict]`
- `get_favorite(fav_id) -> dict | None` (with its videos)
- `save_favorite(url, name, source_type, output_folder, videos) -> int` (upsert by `url`; inserts new videos, preserves existing rows' flags/metadata)
- `set_output_folder(fav_id, output_folder)` (called when the favorite's folder changes / on download)
- `rename_favorite(fav_id, name)`
- `delete_favorite(fav_id)`
- `upsert_videos(fav_id, videos)` (used by incremental fetch)
- `mark_downloaded(fav_id, video_id, has_transcript, has_audio, metadata)` (called after each download)

---

## 3. Favorites Flow

### Saving (☆ button + inline name field)
- The ☆ button sits next to **Fetch** in the command bar. It is enabled only when a playlist/channel is currently loaded.
- Clicking ☆ reveals a small **inline text input** in the command bar, pre-filled with the auto-detected playlist/channel title (from `list_videos`), plus a confirm button. The user edits the name and confirms.
- On confirm, `POST /api/favorites` saves the URL, name, source_type, the current **output folder** value, and the current video rows (title, date, channel, duration, url). `has_transcript`/`has_audio` default to 0; `metadata_json` NULL.
- `favorite.url` is `UNIQUE`: re-saving the same URL updates the existing favorite (incl. name) rather than duplicating.
- Single-video URLs are not saveable (☆ disabled / hidden for `source_type == 'video'`).
- After save, the ☆ reflects saved state (★) and the favorite appears in the dropdown.

### Re-opening (★ dropdown)
- The ★ dropdown lists saved favorites by name. Each entry has a rename (✎) and delete affordance.
- Selecting a favorite calls `GET /api/favorites/{id}` and renders the saved video table **instantly, with no network** — including saved dates and T/A badges. The favorite's URL populates the URL input, and its saved **output folder autofills** the output-folder field.
- Rename: inline edit → `PATCH`/`POST /api/favorites/{id}` updating `name`.
- Delete: `DELETE /api/favorites/{id}` (cascades to its videos).

### Incremental fetch (Fetch with a favorite active)
- Clicking Fetch while a favorite is active calls `POST /api/fetch` (`list_videos`) for the favorite's URL.
- Results are reconciled into the saved set via `upsert_videos`:
  - **New** `video_id`s are inserted.
  - **Existing** rows keep their saved data and download flags (`has_transcript`, `has_audio`, `metadata_json`).
  - **Videos removed** from the playlist are **kept** in the favorite (they may have been downloaded).
- `last_fetched_at` is updated.
- Parallel date extraction then runs for **new videos only** (those without a date).

### Output folder + actions
- A favorite remembers an `output_folder`. Picking the favorite autofills the output-folder field; saving captures the current value; downloading with the favorite active updates it to the folder used.
- Two buttons sit next to the output-folder field (next to the existing **Browse** button):
  - **Open in Finder** → `POST /api/open-folder` with the current output-folder value; the backend runs `open <expanded-path>` (macOS) to reveal it in Finder. The path is `expanduser`-expanded; if it doesn't exist, the endpoint returns an error shown in the status chip.
  - **Copy path** → client-side only; copies the current output-folder value to the clipboard via `navigator.clipboard.writeText`.
- Both buttons operate on the **current value of the output-folder field** (which autofills from the favorite but can be edited), not a separate stored value — so they work whether or not a favorite is active, as long as the field is non-empty.

---

## 4. Download Types (Transcript / Audio)

### UI
Two checkboxes in the right panel, above **Metadata Fields**:
- ☑ **Transcript** (default on)
- ☐ **Audio** (default off)

At least one must be checked for the Download button to be enabled.

### Behavior
Per selected video, in its per-video output folder (`output_folder/<date>-<title>/`):
- **Transcript** → `transcript.txt` (current behavior).
- **Audio** → yt-dlp `format: "bestaudio"`, **no re-encoding**, written as `audio.<ext>` using the stream's native container (e.g. `audio.m4a`, `audio.webm`).
- **metadata.json** → always written (carries the selected metadata fields).

### Backend extraction
`fetch_transcript_and_metadata` is generalized to honor the requested types in a **single** `extract_info` pass where possible:
- The redundant separate `_probe_language` extraction is folded into the main extraction (language is detected from the same `info`), removing the current double-extraction.
- When audio is requested, `format`/postprocessor options download the audio file alongside subtitle files into the per-video output (audio goes to the final folder, not a temp dir).
- Returns metadata + transcript (if requested) + audio file info (if requested).

### Persistence write-back
After each video finishes, the backend calls `store.mark_downloaded(...)` updating `has_transcript`/`has_audio` and storing `metadata_json` — **only when a favorite is active** (`favorite_id` present in the download request). When a favorite is active, the request's `output_folder` is also persisted to the favorite (`set_output_folder`), so the remembered folder tracks the last folder actually used. Downloads without an active favorite behave as today (no DB write).

---

## 5. API & UI Changes

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/favorites` | List favorites (id, name, url, source_type) |
| POST | `/api/favorites` | Save current URL + videos as a favorite (upsert by url) |
| GET | `/api/favorites/{id}` | Saved videos for instant render |
| POST | `/api/favorites/{id}` | Rename a favorite |
| DELETE | `/api/favorites/{id}` | Delete a favorite (cascade) |
| POST | `/api/open-folder` | Reveal a folder path in Finder (`open`), expanduser-expanded |
| POST | `/api/fetch` | Unchanged; frontend reconciles into saved set when a favorite is active |
| POST | `/api/dates` | Unchanged contract; now parallel internally |
| POST | `/api/download` | Adds `download_transcript: bool`, `download_audio: bool`, optional `favorite_id` |

### Models (`backend/models.py`)
- New: `FavoriteSummary` (incl. `output_folder`), `FavoriteDetail` (favorite + `list[VideoInfo]`-like rows with `has_transcript`/`has_audio`), `SaveFavoriteRequest` (incl. `output_folder`), `RenameFavoriteRequest`, `OpenFolderRequest` (`folder: str`).
- `DownloadRequest` gains `download_transcript: bool = True`, `download_audio: bool = False`, `favorite_id: Optional[int] = None`.
- `VideoInfo` (or a derived model for favorites) carries `has_transcript`/`has_audio` for badge rendering.

### Frontend (`frontend/`)
- Command bar: add ★ Favorites dropdown + ☆ save button + inline name field (Layout Option A). Add **Open in Finder** and **Copy path** buttons next to the output-folder field.
- Right panel: add Transcript/Audio checkboxes above Metadata Fields; wire into `state` and the download request.
- Status column: render T / A badges from `has_transcript`/`has_audio` (saved or freshly downloaded). Live download progress still flows through `/api/progress` polling; on completion, badges update for the downloaded types.
- `state` additions: `activeFavoriteId`, `downloadTranscript`, `downloadAudio`, `favorites` list. Output folder autofills from the active favorite on pick.

---

## Architecture & Module Boundaries

- **`backend/store.py`** (new): all SQLite access. One clear purpose: persist/read favorites and per-video download state. Pure functions over a connection; schema bootstrap on import/first call. Testable in isolation with a temp DB path.
- **`backend/fetcher.py`**: gains parallel `iter_dates`; `fetch_transcript_and_metadata` generalized for download types and de-duplicated extraction. No DB knowledge.
- **`backend/main.py`**: new favorites endpoints; download endpoint writes back to `store` when a favorite is active. Orchestration only.
- **`frontend/app.js`**: favorites UI + download-type state. No backend logic leaks.

---

## Error Handling

- DB unavailable / write failure: favorites endpoints return 500 with a message; the core fetch/download flow (no favorite) is unaffected.
- Audio download failure for a video: that video's row marks `status = error` (existing per-video error handling in `_run_download`); `has_audio` is not set. Transcript may still succeed independently.
- Saving a favorite for a single-video URL: rejected client-side (button disabled) and defensively server-side (reject `source_type == 'video'`).
- Re-saving an existing URL: upsert, not error.
- Open in Finder on a missing/empty path: endpoint returns an error surfaced in the status chip; follows the existing `/api/pick-folder` subprocess pattern (run in executor, expanduser the path).

---

## Testing

- **`store.py`**: unit tests against a temp SQLite file — save/upsert (new + existing video preservation), rename, delete cascade, `mark_downloaded`, source-of-truth flags.
- **Parallel `iter_dates`**: test that all videos yield a result, that failures yield `None`, and that only date-less videos are processed (mock `YoutubeDL`).
- **Download types**: test that transcript-only, audio-only, and both produce the expected files; metadata.json always written; DB write-back occurs only with a `favorite_id`.
- **Incremental fetch**: existing rows retain download flags; new videos inserted; removed videos retained.
- Existing tests under `tests/` updated for the new `DownloadRequest` fields.

---

## Assumptions

- Only playlists/channels are favoritable; single videos are not.
- Videos removed from a playlist remain in the saved favorite.
- The DB lives in the repo's `data/` dir, independent of the output folder, gitignored.
- The DB is the sole source of truth for download status (no filesystem reconciliation).
- Original audio only (no transcoding, no ffmpeg dependency).
