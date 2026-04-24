from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from app.domain.track import LikedTrackIds, LikedTrackSnapshot, Track
from app.infrastructure.persistence.sqlite_library_cache_repo import SQLiteLibraryCacheRepo


def test_sqlite_library_cache_repo_round_trips_recent_searches(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")

    repo.save_recent_searches(("ambient", "jazz"))

    assert repo.load_recent_searches() == ("ambient", "jazz")


def test_sqlite_library_cache_repo_round_trips_track_metadata_and_artwork(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")
    track = Track(
        id="track-1",
        title="Signal",
        artists=("Artist",),
        album_title="Album",
        album_year=2024,
        duration_ms=123_000,
        stream_ref="stream",
        artwork_ref="covers/track.jpg",
        is_liked=True,
    )

    repo.save_track_metadata(track)
    repo.save_artwork_ref(track.id, "covers/track.jpg")

    assert repo.load_track_metadata("track-1") == track
    assert repo.load_artwork_ref("track-1") == "covers/track.jpg"


def test_sqlite_library_cache_repo_round_trips_liked_track_ids(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")
    liked_tracks = LikedTrackIds(
        user_id="user-1",
        revision=42,
        track_ids=frozenset({"track-1", "track-2"}),
    )

    repo.save_liked_track_ids(liked_tracks)
    repo.mark_track_liked("user-1", "track-3:album-1")
    repo.mark_track_unliked("user-1", "track-2")

    loaded = repo.load_liked_track_ids("user-1")

    assert loaded is not None
    assert loaded.user_id == "user-1"
    assert loaded.revision == 42
    assert loaded.track_ids == frozenset({"track-1", "track-3:album-1"})


def test_sqlite_library_cache_repo_round_trips_liked_track_snapshot(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")
    snapshot = LikedTrackSnapshot(
        user_id="user-1",
        revision=42,
        tracks=(
            Track(id="track-1", title="Signal", artists=("Artist",), is_liked=True),
            Track(id="track-2", title="Pulse", artists=("Artist",), is_liked=True),
        ),
    )

    repo.save_liked_track_snapshot(snapshot)

    assert repo.load_liked_track_snapshot("user-1") == snapshot


def test_sqlite_library_cache_repo_returns_empty_when_missing(tmp_path) -> None:
    repo = SQLiteLibraryCacheRepo(db_path=tmp_path / "library.sqlite3")

    assert repo.load_recent_searches() == ()
    assert repo.load_track_metadata("missing") is None
    assert repo.load_liked_track_ids("user-1") is None
    assert repo.load_liked_track_snapshot("user-1") is None
    assert repo.load_artwork_ref("missing") is None


def test_sqlite_library_cache_repo_expires_track_metadata_and_artwork_refs(tmp_path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = SQLiteLibraryCacheRepo(db_path=path)
    expired_at = (datetime.now(tz=UTC) - timedelta(days=8)).isoformat()
    with sqlite3.connect(path) as connection:
        connection.execute(
            (
                "insert into tracks("
                "id, title, artists_json, available, is_liked, cached_at"
                ") values (?, ?, ?, ?, ?, ?)"
            ),
            ("track-1", "Signal", '["Artist"]', 1, 0, expired_at),
        )
        connection.execute(
            "insert into artwork(item_id, artwork_ref, cached_at) values (?, ?, ?)",
            ("track-1", "covers/track.jpg", expired_at),
        )

    assert repo.load_track_metadata("track-1") is None
    assert repo.load_artwork_ref("track-1") is None
