import json
import re
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


def write_video_files(folder: Path, metadata: dict, transcript: str) -> None:
    """Write metadata.json and transcript.txt into folder."""
    with open(folder / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    with open(folder / "transcript.txt", "w", encoding="utf-8") as f:
        f.write(transcript)
