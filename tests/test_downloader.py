import json
import tempfile
from pathlib import Path
from backend.downloader import place_audio, sanitize_name, get_video_folder, write_video_files


def test_sanitize_name_removes_unsafe_chars():
    assert sanitize_name("Video: My/File") == "Video-MyFile"


def test_sanitize_name_collapses_whitespace():
    assert sanitize_name("  Hello   World  ") == "Hello-World"


def test_sanitize_name_truncates_to_100_chars():
    long_name = "A" * 150
    assert len(sanitize_name(long_name)) == 100


def test_get_video_folder_with_playlist():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = get_video_folder(tmpdir, "2024-01-15", "My Video")
        assert folder.exists()
        assert folder == Path(tmpdir) / "2024-01-15-My-Video"


def test_get_video_folder_without_playlist():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = get_video_folder(tmpdir, "2024-01-15", "My Video")
        assert folder == Path(tmpdir) / "2024-01-15-My-Video"


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


def test_write_video_files_removes_stale_transcript_when_requested_but_empty():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        (folder / "transcript.txt").write_text("old transcript")
        # transcript requested this run but none was produced -> reconcile
        write_video_files(folder, {"title": "X"}, None, download_transcript=True)
        assert not (folder / "transcript.txt").exists()
        assert (folder / "metadata.json").exists()


def test_write_video_files_keeps_transcript_when_not_requested():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        (folder / "transcript.txt").write_text("from a prior download")
        # audio-only run: transcript not requested -> leave existing one alone
        write_video_files(folder, {"title": "X"}, None, download_transcript=False)
        assert (folder / "transcript.txt").read_text() == "from a prior download"
        assert (folder / "metadata.json").exists()


def test_place_audio_renames_to_audio_with_native_ext():
    with tempfile.TemporaryDirectory() as d:
        src_dir = Path(d) / "src"
        src_dir.mkdir()
        audio_src = src_dir / "vid123.m4a"
        audio_src.write_bytes(b"fake-audio")
        dest = Path(d) / "dest"
        dest.mkdir()
        place_audio(dest, str(audio_src))
        assert (dest / "audio.m4a").read_bytes() == b"fake-audio"
        assert not audio_src.exists()


def test_place_audio_replaces_stale_audio_of_other_ext():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        (folder / "audio.webm").write_bytes(b"old")   # leftover from a prior download
        src = folder / "vid.m4a"
        src.write_bytes(b"new")
        place_audio(folder, str(src))
        assert not (folder / "audio.webm").exists()    # stale removed
        assert (folder / "audio.m4a").read_bytes() == b"new"


def test_place_audio_removes_existing_when_requested_but_no_new_audio():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        (folder / "audio.m4a").write_bytes(b"old")
        # audio requested this run but none was produced -> reconcile
        place_audio(folder, None, download_audio=True)
        assert not (folder / "audio.m4a").exists()


def test_place_audio_keeps_existing_when_not_requested():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        (folder / "audio.m4a").write_bytes(b"from a prior download")
        # transcript-only run: audio not requested -> leave existing one alone
        place_audio(folder, None, download_audio=False)
        assert (folder / "audio.m4a").read_bytes() == b"from a prior download"
