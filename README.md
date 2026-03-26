# YouTube Automation

A local web app for downloading YouTube video transcripts and metadata. Paste a URL (video, playlist, or channel), select videos, choose metadata fields, and download organized transcripts and metadata to your local filesystem.

No YouTube API key required — uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for all YouTube access.

## Features

- **Fetch videos** from any YouTube URL (single video, playlist, or channel)
- **Select specific videos** from an interactive table with sortable columns
- **Choose metadata fields** to include (title, date, channel, duration, tags, and more)
- **Download transcripts** as plain text and metadata as JSON
- **Organized output** in a `Channel/Playlist/Date-Title/` folder structure
- **Browser cookie support** for age-restricted content (Chrome, Firefox, Safari, Edge, Brave)
- **Real-time progress** tracking per video during downloads

## Quick Start

```bash
pip install -r requirements.txt
./run.sh
```

This starts the server at `http://localhost:8000` and opens your browser.

## Tech Stack

- **Backend:** Python, FastAPI, yt-dlp, Uvicorn
- **Frontend:** Vanilla HTML/CSS/JS (no build step)
- **Testing:** pytest, httpx

## Project Structure

```
backend/
  main.py           # FastAPI app and API routes
  fetcher.py        # yt-dlp wrapper for listing videos and fetching transcripts
  downloader.py     # File I/O and folder organization
  models.py         # Pydantic request/response models
frontend/
  index.html        # Single-page app
  app.js            # UI logic and API interactions
  style.css         # Dark theme (Catppuccin)
tests/              # pytest unit tests
run.sh              # Startup script
requirements.txt    # Python dependencies
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/fetch` | List videos from a YouTube URL |
| `GET` | `/api/fields` | Get available metadata fields |
| `POST` | `/api/download` | Start a background download job |
| `GET` | `/api/progress/{job_id}` | Poll download job status |
| `POST` | `/api/dates` | Stream upload dates via Server-Sent Events |

## Output Structure

```
output_folder/
  Channel Name/
    Playlist Name/              # only for playlists
      2024-01-15-Video-Title/
        metadata.json           # selected fields only
        transcript.txt          # plain text, no timestamps
```

## Testing

```bash
pytest tests/
```
