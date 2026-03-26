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
