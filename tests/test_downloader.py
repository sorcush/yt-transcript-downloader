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
