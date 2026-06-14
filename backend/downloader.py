import json
import re
import shutil
from pathlib import Path


def sanitize_name(name: str) -> str:
    """Remove filesystem-unsafe characters and normalize whitespace."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "-", name.strip())
    return name[:100]


def get_video_folder(
    output_folder: str,
    upload_date: str,
    title: str,
) -> Path:
    """Return the Path for a video's output folder, creating it if needed."""
    folder = Path(output_folder) / f"{upload_date}-{sanitize_name(title)}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_video_files(
    folder: Path,
    metadata: dict,
    transcript: str | None,
    download_transcript: bool = True,
) -> None:
    """Write metadata.json (always; overwrites). When the transcript was
    requested, write transcript.txt if one was produced, otherwise remove any
    stale one so the folder reflects this download. When the transcript was not
    requested, leave an existing transcript.txt from a previous download alone."""
    with open(folder / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    if not download_transcript:
        return
    transcript_path = folder / "transcript.txt"
    if transcript is not None:
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)
    elif transcript_path.exists():
        transcript_path.unlink()


def place_audio(
    folder: Path,
    audio_path: str | None,
    download_audio: bool = True,
) -> None:
    """Reconcile the folder's audio to the latest download: when audio was
    requested, remove any existing audio.* (e.g. a stale audio.webm), then move
    the new file in as audio.<native-ext> if one was downloaded. When audio was
    not requested, leave existing audio.* from a previous download alone."""
    if not download_audio:
        return
    for old in folder.glob("audio.*"):
        old.unlink()
    if audio_path:
        ext = Path(audio_path).suffix
        shutil.move(audio_path, folder / f"audio{ext}")
