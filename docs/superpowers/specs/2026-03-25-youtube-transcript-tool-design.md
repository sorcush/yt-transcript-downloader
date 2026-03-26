# YouTube Transcript Tool — Design Spec

**Date:** 2026-03-25

## Overview

A local web app for downloading transcripts and metadata from YouTube videos, playlists, or channels. The user pastes a URL, selects videos from a table, configures which metadata fields to include, sets an output folder, and downloads. Output is organized into a structured folder hierarchy per channel/playlist/video.

## Tech Stack

- **Backend:** Python, FastAPI, yt-dlp
- **Frontend:** Vanilla JS, single HTML page with CSS
- **No API key required** — yt-dlp handles all YouTube access

## Project Structure

```
youtube-automation/
├── backend/
│   ├── main.py           # FastAPI app, route definitions
│   ├── fetcher.py        # yt-dlp wrapper: list videos, fetch transcript+metadata
│   ├── downloader.py     # writes files to output folder structure
│   └── models.py         # Pydantic models for requests/responses
├── frontend/
│   ├── index.html        # single page app
│   ├── app.js            # all UI logic
│   └── style.css
├── requirements.txt
└── run.sh                # starts the server and opens the browser
```

## UI Layout

Single page with two areas:
- **Main area:** URL input, output folder input, video table with checkboxes, select-all, Download button
- **Side panel (persistent right):** list of all available yt-dlp metadata fields as checkboxes; selection is preserved across fetches

The table columns are: checkbox, Title, Date, Channel, Duration. Rows sorted oldest → newest by upload date.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/fetch` | Takes a YouTube URL, returns list of videos (title, date, channel, duration, video_id) |
| `GET` | `/api/fields` | Returns all available yt-dlp metadata field names |
| `POST` | `/api/download` | Takes selected video IDs, chosen fields, output folder path — starts background download job, returns job_id |
| `GET` | `/api/progress/{job_id}` | Returns per-video download status (pending / downloading / done / error) |

## Data Flow

1. User pastes URL → `POST /api/fetch` → backend calls `yt-dlp --flat-playlist` to list videos without downloading → returns table rows
2. User selects videos, picks metadata fields, sets output folder → clicks Download
3. `POST /api/download` starts a background job, returns `job_id`
4. Frontend polls `GET /api/progress/{job_id}` every 2s → updates per-video status in the table
5. For each video, backend fetches transcript (auto-generated captions) and selected metadata fields via yt-dlp, writes output files

## Output Folder Structure

```
{output_folder}/
  {Channel Name}/
    {Playlist Name}/          ← only present if source was a playlist
      2024-01-15-Video-Title/
        metadata.json
        transcript.txt
      2024-02-03-Another-Video/
        metadata.json
        transcript.txt
```

- Date format: `YYYY-MM-DD`
- Video folder name: `YYYY-MM-DD-Video-Title` with filesystem-unsafe characters stripped
- `metadata.json`: contains only the user-selected fields
- `transcript.txt`: plain text, no timestamps; if no transcript available, contains `No transcript available`

## Edge Cases

- **No transcript:** `transcript.txt` is created with content `No transcript available`
- **Special characters in title:** sanitized for filesystem (slashes, colons, quotes removed/replaced)
- **Large channels:** `--flat-playlist` fetches only metadata (no video download), so listing stays fast regardless of video count
- **Input types:** single video URL, playlist URL, and channel URL all handled uniformly — yt-dlp detects the type; backend uses the same code path for all three
