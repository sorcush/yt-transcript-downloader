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


def _format_date(date_str: str | None) -> str | None:
    """Convert YYYYMMDD to YYYY-MM-DD. Returns None if missing."""
    if date_str and len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return None


class _SilentLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _add_cookies(opts: dict, browser: str | None) -> None:
    """Mutate opts in-place to add cookie source if browser is specified."""
    if browser:
        opts["cookiesfrombrowser"] = (browser,)


def fetch_date(url: str, browser: str | None = None) -> str | None:
    """Fetch just the upload_date for a single video URL (full extraction)."""
    opts = {"logger": _SilentLogger(), "quiet": True, "skip_download": True, "ignore_no_formats_error": True}
    _add_cookies(opts, browser)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return _format_date(info.get("upload_date"))


def iter_dates(
    videos: list[tuple[str, str]], browser: str | None = None
):
    """Yield (video_id, date) reusing a single YoutubeDL instance + cookiejar."""
    opts = {"logger": _SilentLogger(), "quiet": True, "skip_download": True, "ignore_no_formats_error": True}
    _add_cookies(opts, browser)
    with yt_dlp.YoutubeDL(opts) as ydl:
        for vid_id, url in videos:
            try:
                info = ydl.extract_info(url, download=False)
                date = _format_date(info.get("upload_date"))
            except Exception:
                date = None
            yield vid_id, date


def get_available_fields() -> list[str]:
    return AVAILABLE_FIELDS


def list_videos(url: str, browser: str | None = None) -> dict:
    """Return video list and source info from a YouTube URL (no download)."""
    ydl_opts = {
        "logger": _SilentLogger(),
        "extract_flat": "in_playlist",
        "skip_download": True,
        "ignore_no_formats_error": True,
        "extractor_args": {"youtube": {"lang": [""]}},
    }
    _add_cookies(ydl_opts, browser)
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


def _original_lang_from_captions(info: dict) -> str | None:
    """Detect original language from automatic_captions by finding entries
    whose subtitle URL has no tlang= parameter (i.e. not auto-translated)."""
    for lang, formats in info.get("automatic_captions", {}).items():
        for fmt in formats:
            url = fmt.get("url", "")
            if "tlang=" not in url:
                return lang
    return None


def _probe_language(url: str, browser: str | None) -> str:
    """Return the video's original language code, defaulting to 'en'."""
    opts = {"logger": _SilentLogger(), "quiet": True, "skip_download": True, "ignore_no_formats_error": True}
    _add_cookies(opts, browser)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return _original_lang_from_captions(info) or info.get("language") or "en"


def fetch_transcript_and_metadata(
    url: str, fields: list[str], browser: str | None = None
) -> tuple[dict, str]:
    """Fetch metadata and plain-text transcript for a single video URL.

    Downloads subtitle files to a temp directory (video itself is skipped).
    Returns (metadata_dict, transcript_text).
    """
    lang = _probe_language(url, browser)
    # For English, include regional variants; for other languages, just that code.
    if lang.startswith("en"):
        sub_langs = ["en", "en-US", "en-GB"]
    else:
        sub_langs = [lang]

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "logger": _SilentLogger(), "quiet": True,
            "ignore_no_formats_error": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": sub_langs,
            "subtitlesformat": "json3",
            "skip_download": True,
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        }
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
        transcript = _read_transcript(tmpdir, video_id)

    return metadata, transcript
