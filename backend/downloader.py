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


def write_video_files(folder: Path, metadata: dict, transcript: str | None) -> None:
    """Write metadata.json (always; overwrites). Write transcript.txt if a
    transcript is given, otherwise remove any stale one so the folder reflects
    exactly the latest download."""
    with open(folder / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    transcript_path = folder / "transcript.txt"
    if transcript is not None:
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)
    elif transcript_path.exists():
        transcript_path.unlink()


def place_audio(folder: Path, audio_path: str | None) -> None:
    """Reconcile the folder's audio to the latest download: remove any existing
    audio.* (e.g. a stale audio.webm), then move the new file in as
    audio.<native-ext> if one was downloaded."""
    for old in folder.glob("audio.*"):
        old.unlink()
    if audio_path:
        ext = Path(audio_path).suffix
        shutil.move(audio_path, folder / f"audio{ext}")
