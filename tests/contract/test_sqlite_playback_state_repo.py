from __future__ import annotations

import sqlite3

import pytest

from app.domain import QueueItem, SavedPlaybackQueue, StorageError, Track
from app.infrastructure.persistence.sqlite_playback_state_repo import SQLitePlaybackStateRepo


def test_sqlite_playback_state_repo_round_trips_queue(tmp_path) -> None:
    repo = SQLitePlaybackStateRepo(db_path=tmp_path / "library.sqlite3")
    queue = (
        QueueItem(
            track=Track(
                id="track-1",
                title="Signal",
                artists=("Artist",),
                album_title="Album",
                album_year=2024,
                duration_ms=123_000,
                stream_ref="https://temporary-stream.example/track-1",
                artwork_ref="covers/track.jpg",
                is_liked=True,
            ),
            source_type="album",
            source_id="album-1",
            source_index=0,
        ),
    )

    repo.save_playback_queue(queue, active_index=0, position_ms=45_000)

    assert repo.load_playback_queue() == SavedPlaybackQueue(
        queue=(
            QueueItem(
                track=Track(
                    id="track-1",
                    title="Signal",
                    artists=("Artist",),
                    album_title="Album",
                    album_year=2024,
                    duration_ms=123_000,
                    stream_ref=None,
                    artwork_ref="covers/track.jpg",
                    is_liked=True,
                ),
                source_type="album",
                source_id="album-1",
                source_index=0,
            ),
        ),
        active_index=0,
        position_ms=45_000,
    )


def test_sqlite_playback_state_repo_returns_none_when_missing(tmp_path) -> None:
    repo = SQLitePlaybackStateRepo(db_path=tmp_path / "library.sqlite3")

    assert repo.load_playback_queue() is None


def test_sqlite_playback_state_repo_clears_queue(tmp_path) -> None:
    repo = SQLitePlaybackStateRepo(db_path=tmp_path / "library.sqlite3")
    repo.save_playback_queue(
        (QueueItem(track=Track(id="track-1", title="Signal", artists=("Artist",))),),
        active_index=0,
    )

    repo.clear_playback_queue()

    assert repo.load_playback_queue() is None


def test_sqlite_playback_state_repo_rejects_invalid_payload(tmp_path) -> None:
    path = tmp_path / "library.sqlite3"
    repo = SQLitePlaybackStateRepo(db_path=path)
    del repo
    with sqlite3.connect(path) as connection:
        connection.execute(
            (
                "insert into playback_queue(id, queue_json, active_index, updated_at) "
                "values (1, ?, ?, ?)"
            ),
            ("{}", 0, "2026-04-22T12:00:00+00:00"),
        )

    repo = SQLitePlaybackStateRepo(db_path=path)
    with pytest.raises(StorageError):
        repo.load_playback_queue()
