import json
import math
import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Date extraction scales the worker pool with the number of videos: roughly one
# worker per VIDEOS_PER_WORKER videos, capped at MAX_DATE_FETCH_WORKERS. Cookies
# are decrypted only once (see _export_browser_cookies), so workers only do
# network I/O — the cap exists only to bound thread/connection count for huge
# channels. Lower it if YouTube starts throttling many concurrent requests.
VIDEOS_PER_WORKER = 10
MAX_DATE_FETCH_WORKERS = 50


def _worker_count(num_videos: int) -> int:
    """Workers needed so each handles about VIDEOS_PER_WORKER videos (>=1, capped)."""
    if num_videos <= 0:
        return 1
    return max(1, min(MAX_DATE_FETCH_WORKERS, math.ceil(num_videos / VIDEOS_PER_WORKER)))


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


def _export_browser_cookies(browser: str) -> str | None:
    """Decrypt the browser's cookies ONCE and write them to a temp Netscape
    cookie file, returning its path (or None on failure).

    Workers then read this cheap file via `cookiefile` instead of each
    decrypting the browser store — decrypting per worker caused a long startup
    stall. yt-dlp only writes a cookiejar back to `cookiefile` from
    close()/__exit__ (there is no __del__), so as long as workers never use a
    `with` block, the shared file is read-only in practice and cannot be
    corrupted by concurrent writers.
    """
    try:
        ydl = yt_dlp.YoutubeDL({
            "logger": _SilentLogger(),
            "quiet": True,
            "cookiesfrombrowser": (browser,),
        })
        fd, path = tempfile.mkstemp(suffix=".cookies.txt")
        os.close(fd)
        ydl.cookiejar.save(path, ignore_discard=True, ignore_expires=True)
        return path
    except Exception:
        return None


def iter_dates(
    videos: list[tuple[str, str]], browser: str | None = None
):
    """Yield (video_id, date) for each video, extracting concurrently.

    The worker pool scales with the number of videos (~one worker per
    VIDEOS_PER_WORKER videos, capped at MAX_DATE_FETCH_WORKERS). Browser cookies
    are decrypted ONCE up front (not per worker) and shared with workers through
    a temp cookie file, so worker count drives only network concurrency — no
    cookie-decrypt storm on startup. Each worker thread builds one YoutubeDL
    instance and reuses it; instances are never used as context managers, so
    yt-dlp never writes the cookiejar back to the shared file (no corruption).
    Results are yielded as they complete, so order is not guaranteed; callers
    key results by video_id.
    """
    videos = list(videos)
    cookiefile = _export_browser_cookies(browser) if browser else None
    local = threading.local()

    def _thread_ydl() -> "yt_dlp.YoutubeDL":
        ydl = getattr(local, "ydl", None)
        if ydl is None:
            opts = {"logger": _SilentLogger(), "quiet": True, "skip_download": True, "ignore_no_formats_error": True}
            if cookiefile:
                opts["cookiefile"] = cookiefile
            # No `with`: the instance is never closed, so yt-dlp never saves the
            # cookiejar back to cookiefile — concurrent workers only read it.
            ydl = yt_dlp.YoutubeDL(opts)
            local.ydl = ydl
        return ydl

    def _fetch_one(vid_id: str, url: str):
        try:
            info = _thread_ydl().extract_info(url, download=False)
            return vid_id, _format_date(info.get("upload_date"))
        except Exception:
            return vid_id, None

    try:
        with ThreadPoolExecutor(max_workers=_worker_count(len(videos))) as executor:
            futures = [executor.submit(_fetch_one, vid_id, url) for vid_id, url in videos]
            for future in as_completed(futures):
                yield future.result()
    finally:
        if cookiefile:
            try:
                os.remove(cookiefile)
            except OSError:
                pass


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


def _find_audio(tmpdir: str, video_id: str) -> str | None:
    """Return the path to the downloaded audio file (any non-json3 file for this id)."""
    for path in Path(tmpdir).glob(f"{video_id}.*"):
        if path.suffix != ".json3":
            return str(path)
    return None


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

    def _build_opts(use_browser: bool) -> dict:
        opts: dict = {
            "logger": _SilentLogger(),
            "quiet": True,
            "no_color": True,
            "ignore_no_formats_error": True,
            "skip_download": not want_audio,
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
        }
        if want_audio:
            opts["format"] = "bestaudio/best"
        if want_transcript:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = sub_langs
            opts["subtitlesformat"] = "json3"
        if use_browser:
            _add_cookies(opts, browser)
        return opts

    try:
        with yt_dlp.YoutubeDL(_build_opts(bool(browser))) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception:
        # Passing browser cookies can make YouTube withhold playable formats for
        # otherwise-public videos ("No video formats found" / "Requested format
        # is not available"). Retry once anonymously before giving up.
        if not browser:
            raise
        with yt_dlp.YoutubeDL(_build_opts(False)) as ydl:
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
