from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import backend.fetcher as fetcher
from backend.fetcher import list_videos, _format_date, iter_dates


def test_format_date_converts_yyyymmdd():
    assert _format_date("20240115") == "2024-01-15"


def test_format_date_handles_none():
    assert _format_date(None) is None


def test_format_date_handles_short_string():
    assert _format_date("bad") is None


def test_iter_dates_returns_all_results_parallel():
    infos = {
        "https://youtube.com/watch?v=v1": {"upload_date": "20240101"},
        "https://youtube.com/watch?v=v2": {"upload_date": "20240202"},
        "https://youtube.com/watch?v=v3": {"upload_date": None},
    }

    def fake_extract(url, download=False):
        return infos[url]

    with patch("yt_dlp.YoutubeDL") as mock_cls:
        mock_cls.return_value.extract_info.side_effect = fake_extract
        videos = [("v1", "https://youtube.com/watch?v=v1"),
                  ("v2", "https://youtube.com/watch?v=v2"),
                  ("v3", "https://youtube.com/watch?v=v3")]
        results = dict(iter_dates(videos))

    assert results == {"v1": "2024-01-01", "v2": "2024-02-02", "v3": None}


def test_iter_dates_failure_yields_none():
    def boom(url, download=False):
        raise RuntimeError("network down")

    with patch("yt_dlp.YoutubeDL") as mock_cls:
        mock_cls.return_value.extract_info.side_effect = boom
        results = dict(iter_dates([("v1", "https://youtube.com/watch?v=v1")]))

    assert results == {"v1": None}


def test_iter_dates_decrypts_cookies_once_and_shares_via_cookiefile():
    """Browser cookies are decrypted ONCE (no per-worker decrypt storm) and shared
    with workers via cookiefile — never cookiesfrombrowser on each worker."""
    with patch("backend.fetcher._export_browser_cookies", return_value="/tmp/c.txt") as mock_export:
        with patch("yt_dlp.YoutubeDL") as mock_cls:
            mock_cls.return_value.extract_info.return_value = {"upload_date": "20240101"}
            videos = [(f"v{i}", f"u{i}") for i in range(40)]
            results = dict(iter_dates(videos, browser="chrome"))

    assert len(results) == 40
    assert all(d == "2024-01-01" for d in results.values())
    mock_export.assert_called_once_with("chrome")        # decrypted exactly once
    # At most one instance per worker thread, each reading the shared cookie file.
    assert mock_cls.call_count <= fetcher._worker_count(40)
    for call in mock_cls.call_args_list:
        opts = call.args[0]
        assert opts.get("cookiefile") == "/tmp/c.txt"
        assert "cookiesfrombrowser" not in opts


def test_worker_count_scales_with_videos():
    assert fetcher._worker_count(0) == 1       # empty -> still valid pool size
    assert fetcher._worker_count(1) == 1
    assert fetcher._worker_count(4) == 1       # only a few new videos -> 1 worker
    assert fetcher._worker_count(10) == 1      # 10 per worker
    assert fetcher._worker_count(11) == 2
    assert fetcher._worker_count(95) == 10
    assert fetcher._worker_count(415) == 42    # ~10 videos per worker
    # Only pathologically large channels hit the cap.
    assert fetcher._worker_count(100000) == fetcher.MAX_DATE_FETCH_WORKERS


def test_iter_dates_sizes_pool_to_videos_received_not_total():
    """The pool is sized from the videos passed in. Callers only pass unfetched
    videos, so a 400-video channel with 4 new videos uses a single worker."""
    with patch("yt_dlp.YoutubeDL") as mock_cls:
        mock_cls.return_value.extract_info.return_value = {"upload_date": "20240101"}
        four_new = [(f"v{i}", f"u{i}") for i in range(4)]
        results = dict(iter_dates(four_new))

    assert len(results) == 4
    # ceil(4 / 10) == 1 worker, so at most one YoutubeDL instance is built.
    assert mock_cls.call_count == 1


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


import json
import shutil
import tempfile
from backend.fetcher import _find_audio, _read_transcript, fetch_transcript_and_metadata


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


def test_find_audio_ignores_subtitle_files(tmp_path):
    (tmp_path / "vid.en.json3").write_text("{}")
    (tmp_path / "vid.m4a").write_bytes(b"a")
    assert _find_audio(str(tmp_path), "vid") == str(tmp_path / "vid.m4a")


def test_find_audio_returns_none_when_absent(tmp_path):
    (tmp_path / "vid.en.json3").write_text("{}")
    assert _find_audio(str(tmp_path), "vid") is None


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

        metadata, transcript, audio_path, tmpdir = fetch_transcript_and_metadata(
            "https://youtube.com/watch?v=abc123",
            ["title", "upload_date", "channel"]
        )

    try:
        assert metadata["title"] == "My Video"
        assert metadata["upload_date"] == "2024-01-15"
        assert metadata["channel"] == "Test Channel"
        assert transcript == "No transcript available"   # no subtitle file in mock
        assert audio_path is None
    finally:
        shutil.rmtree(tmpdir)


def test_fetch_retries_without_cookies_when_cookies_break_formats():
    """Browser cookies can make YouTube withhold formats for public videos. The
    first (cookied) extraction failing should trigger an anonymous retry."""
    seen_opts = []

    def make_instance(opts):
        seen_opts.append(opts)
        inst = MagicMock()
        ydl = inst.__enter__.return_value
        if "cookiesfrombrowser" in opts:
            ydl.extract_info.side_effect = Exception("Requested format is not available")
        else:
            ydl.extract_info.return_value = {"id": "vid", "title": "T", "upload_date": "20240101"}
        return inst

    with patch("yt_dlp.YoutubeDL", side_effect=make_instance):
        metadata, transcript, audio_path, tmpdir = fetch_transcript_and_metadata(
            "https://youtube.com/watch?v=vid", ["title"],
            browser="chrome", want_transcript=False, want_audio=True,
        )

    try:
        assert metadata["title"] == "T"
        # Tried with cookies, then retried without.
        assert any("cookiesfrombrowser" in o for o in seen_opts)
        assert any("cookiesfrombrowser" not in o for o in seen_opts)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_fetch_does_not_retry_without_browser():
    """With no browser cookies configured, a failure should propagate (no retry)."""
    with patch("yt_dlp.YoutubeDL") as mock_cls:
        mock_cls.return_value.__enter__.return_value.extract_info.side_effect = Exception("boom")
        try:
            with pytest.raises(Exception):
                fetch_transcript_and_metadata(
                    "https://youtube.com/watch?v=vid", ["title"],
                    want_transcript=False, want_audio=True,
                )
        finally:
            pass
    # Exactly one construction attempt (no anonymous retry).
    assert mock_cls.call_count == 1
