import importlib
from pathlib import Path

import pytest

import backend.store as store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "favorites.db")
    return store


def _videos():
    return [
        {"video_id": "v1", "title": "One", "upload_date": "2024-01-01",
         "channel": "Chan", "duration": 100, "url": "u1"},
        {"video_id": "v2", "title": "Two", "upload_date": "2024-02-02",
         "channel": "Chan", "duration": 200, "url": "u2"},
    ]


def test_save_and_get_roundtrip(db):
    fav_id = db.save_favorite("http://list", "My List", "playlist", "/out", _videos())
    fav = db.get_favorite(fav_id)
    assert fav["name"] == "My List"
    assert fav["url"] == "http://list"
    assert fav["output_folder"] == "/out"
    assert len(fav["videos"]) == 2
    assert fav["videos"][0]["has_transcript"] is False
    assert fav["videos"][0]["has_audio"] is False


def test_list_favorites(db):
    db.save_favorite("http://a", "A", "playlist", None, [])
    db.save_favorite("http://b", "B", "channel", None, [])
    names = {f["name"] for f in db.list_favorites()}
    assert names == {"A", "B"}


def test_resaving_same_url_updates_not_duplicates(db):
    db.save_favorite("http://list", "Old Name", "playlist", "/out1", _videos())
    db.save_favorite("http://list", "New Name", "playlist", "/out2", _videos())
    favs = db.list_favorites()
    assert len(favs) == 1
    assert favs[0]["name"] == "New Name"
    assert favs[0]["output_folder"] == "/out2"


def test_mark_downloaded_sets_flags_and_metadata(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.mark_downloaded(fav_id, "v1", has_transcript=True, has_audio=False,
                       metadata={"title": "One"})
    fav = db.get_favorite(fav_id)
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["has_transcript"] is True
    assert v1["has_audio"] is False
    assert v1["metadata"] == {"title": "One"}


def test_mark_downloaded_does_not_unset_existing_flag(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.mark_downloaded(fav_id, "v1", has_transcript=True, has_audio=False, metadata={})
    db.mark_downloaded(fav_id, "v1", has_transcript=False, has_audio=True, metadata={})
    fav = db.get_favorite(fav_id)
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["has_transcript"] is True
    assert v1["has_audio"] is True


def test_upsert_videos_preserves_download_flags(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.mark_downloaded(fav_id, "v1", has_transcript=True, has_audio=True, metadata={"a": 1})
    new_videos = _videos() + [{"video_id": "v3", "title": "Three", "upload_date": "2024-03-03",
                               "channel": "Chan", "duration": 300, "url": "u3"}]
    db.upsert_videos(fav_id, new_videos)
    fav = db.get_favorite(fav_id)
    ids = {v["video_id"] for v in fav["videos"]}
    assert ids == {"v1", "v2", "v3"}
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["has_transcript"] is True and v1["has_audio"] is True


def test_upsert_does_not_overwrite_existing_date_with_none(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.upsert_videos(fav_id, [{"video_id": "v1", "title": "One", "upload_date": None,
                               "channel": "Chan", "duration": 100, "url": "u1"}])
    fav = db.get_favorite(fav_id)
    v1 = next(v for v in fav["videos"] if v["video_id"] == "v1")
    assert v1["upload_date"] == "2024-01-01"


def test_set_output_folder(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", "/a", [])
    db.set_output_folder(fav_id, "/b")
    assert db.get_favorite(fav_id)["output_folder"] == "/b"


def test_rename_favorite(db):
    fav_id = db.save_favorite("http://list", "Old", "playlist", None, [])
    db.rename_favorite(fav_id, "New")
    assert db.get_favorite(fav_id)["name"] == "New"


def test_delete_favorite_cascades(db):
    fav_id = db.save_favorite("http://list", "L", "playlist", None, _videos())
    db.delete_favorite(fav_id)
    assert db.get_favorite(fav_id) is None
    assert db.list_favorites() == []


def test_get_missing_favorite_returns_none(db):
    assert db.get_favorite(999) is None
