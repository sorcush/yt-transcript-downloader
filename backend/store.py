import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "favorites.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS favorite (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    source_type     TEXT,
    output_folder   TEXT,
    added_at        TEXT,
    last_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS video (
    favorite_id    INTEGER NOT NULL REFERENCES favorite(id) ON DELETE CASCADE,
    video_id       TEXT NOT NULL,
    title          TEXT,
    upload_date    TEXT,
    channel        TEXT,
    duration       INTEGER,
    url            TEXT,
    has_transcript INTEGER NOT NULL DEFAULT 0,
    has_audio      INTEGER NOT NULL DEFAULT 0,
    metadata_json  TEXT,
    PRIMARY KEY (favorite_id, video_id)
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def _upsert_videos(conn: sqlite3.Connection, fav_id: int, videos: list[dict]) -> None:
    for v in videos:
        conn.execute(
            """
            INSERT INTO video (favorite_id, video_id, title, upload_date, channel, duration, url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(favorite_id, video_id) DO UPDATE SET
                title       = excluded.title,
                upload_date = COALESCE(excluded.upload_date, video.upload_date),
                channel     = excluded.channel,
                duration    = excluded.duration,
                url         = excluded.url
            """,
            (fav_id, v["video_id"], v.get("title"), v.get("upload_date"),
             v.get("channel"), v.get("duration"), v.get("url")),
        )


def save_favorite(url: str, name: str, source_type: str | None,
                  output_folder: str | None, videos: list[dict]) -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT id FROM favorite WHERE url = ?", (url,)).fetchone()
        if row:
            fav_id = row["id"]
            conn.execute(
                "UPDATE favorite SET name = ?, source_type = ?, output_folder = ?, last_fetched_at = ? WHERE id = ?",
                (name, source_type, output_folder, _now(), fav_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO favorite (url, name, source_type, output_folder, added_at, last_fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (url, name, source_type, output_folder, _now(), _now()),
            )
            fav_id = cur.lastrowid
        _upsert_videos(conn, fav_id, videos)
        conn.commit()
        return fav_id
    finally:
        conn.close()


def upsert_videos(fav_id: int, videos: list[dict]) -> None:
    conn = _connect()
    try:
        _upsert_videos(conn, fav_id, videos)
        conn.execute("UPDATE favorite SET last_fetched_at = ? WHERE id = ?", (_now(), fav_id))
        conn.commit()
    finally:
        conn.close()


def set_output_folder(fav_id: int, output_folder: str | None) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE favorite SET output_folder = ? WHERE id = ?", (output_folder, fav_id))
        conn.commit()
    finally:
        conn.close()


def rename_favorite(fav_id: int, name: str) -> None:
    conn = _connect()
    try:
        conn.execute("UPDATE favorite SET name = ? WHERE id = ?", (name, fav_id))
        conn.commit()
    finally:
        conn.close()


def delete_favorite(fav_id: int) -> None:
    conn = _connect()
    try:
        conn.execute("DELETE FROM favorite WHERE id = ?", (fav_id,))
        conn.commit()
    finally:
        conn.close()


def mark_downloaded(fav_id: int, video_id: str, has_transcript: bool | None,
                    has_audio: bool | None, metadata: dict,
                    url: str | None = None, title: str | None = None) -> None:
    """Record the result of a download. For each file type that was part of this
    download, set its flag to the download's outcome (so re-downloading
    reconciles the badge to the current selection rather than accumulating).
    Pass None for a type that was NOT requested this run to leave its existing
    flag untouched, so an audio-only download won't clear the transcript badge
    (or vice versa).

    The video row is created if it does not exist yet, so a download always
    persists to the favorite even for a video that wasn't part of its saved list
    (otherwise the bare UPDATE would silently affect 0 rows and the result would
    be lost)."""
    conn = _connect()
    try:
        # Ensure the row exists; never overwrites an existing row's list fields.
        conn.execute(
            "INSERT OR IGNORE INTO video (favorite_id, video_id, title, url) "
            "VALUES (?, ?, ?, ?)",
            (fav_id, video_id, title or metadata.get("title") or video_id, url),
        )
        sets = ["metadata_json = ?"]
        params: list = [json.dumps(metadata, ensure_ascii=False)]
        if has_transcript is not None:
            sets.append("has_transcript = ?")
            params.append(1 if has_transcript else 0)
        if has_audio is not None:
            sets.append("has_audio = ?")
            params.append(1 if has_audio else 0)
        params.extend([fav_id, video_id])
        conn.execute(
            f"UPDATE video SET {', '.join(sets)} "
            "WHERE favorite_id = ? AND video_id = ?",
            params,
        )
        conn.commit()
    finally:
        conn.close()


def list_favorites() -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, name, url, source_type, output_folder FROM favorite ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _video_row_to_dict(r: sqlite3.Row) -> dict:
    return {
        "video_id": r["video_id"],
        "title": r["title"],
        "upload_date": r["upload_date"],
        "channel": r["channel"],
        "duration": r["duration"],
        "url": r["url"],
        "has_transcript": bool(r["has_transcript"]),
        "has_audio": bool(r["has_audio"]),
        "metadata": json.loads(r["metadata_json"]) if r["metadata_json"] else None,
    }


def get_favorite(fav_id: int) -> dict | None:
    conn = _connect()
    try:
        fav = conn.execute(
            "SELECT id, name, url, source_type, output_folder, added_at, last_fetched_at "
            "FROM favorite WHERE id = ?",
            (fav_id,),
        ).fetchone()
        if fav is None:
            return None
        videos = conn.execute(
            "SELECT * FROM video WHERE favorite_id = ? ORDER BY upload_date",
            (fav_id,),
        ).fetchall()
        result = dict(fav)
        result["videos"] = [_video_row_to_dict(v) for v in videos]
        return result
    finally:
        conn.close()
