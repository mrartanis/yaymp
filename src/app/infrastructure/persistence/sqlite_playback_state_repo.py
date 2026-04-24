from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.domain import PlaybackStateRepo, QueueItem, SavedPlaybackQueue, Track
from app.domain.errors import StorageError


class SQLitePlaybackStateRepo(PlaybackStateRepo):
    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._initialize()

    def load_playback_queue(self) -> SavedPlaybackQueue | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    (
                        "select queue_json, active_index, position_ms "
                        "from playback_queue where id = 1"
                    )
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load playback queue") from exc

        if row is None:
            return None
        try:
            payload = json.loads(row["queue_json"])
            if not isinstance(payload, list):
                raise TypeError("queue_json must be a list")
            queue = tuple(self._decode_queue_item(item) for item in payload)
            active_index = row["active_index"]
            if active_index is not None:
                active_index = int(active_index)
            return SavedPlaybackQueue(
                queue=queue,
                active_index=active_index,
                position_ms=max(0, int(row["position_ms"] or 0)),
            )
        except (TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
            raise StorageError("Saved playback queue is invalid") from exc

    def save_playback_queue(
        self,
        queue: Sequence[QueueItem],
        *,
        active_index: int | None,
        position_ms: int = 0,
    ) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into playback_queue("
                        "id, queue_json, active_index, position_ms, updated_at"
                        ") "
                        "values (1, ?, ?, ?, ?) "
                        "on conflict(id) do update set "
                        "queue_json = excluded.queue_json, "
                        "active_index = excluded.active_index, "
                        "position_ms = excluded.position_ms, "
                        "updated_at = excluded.updated_at"
                    ),
                    (
                        json.dumps(
                            [self._encode_queue_item(item) for item in queue],
                            ensure_ascii=True,
                        ),
                        active_index,
                        max(0, position_ms),
                        datetime.now(tz=UTC).isoformat(),
                    ),
                )
        except (sqlite3.Error, TypeError) as exc:
            raise StorageError("Failed to save playback queue") from exc

    def clear_playback_queue(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("delete from playback_queue where id = 1")
        except sqlite3.Error as exc:
            raise StorageError("Failed to clear playback queue") from exc

    def _initialize(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(
                    """
                    create table if not exists playback_queue (
                        id integer primary key check (id = 1),
                        queue_json text not null,
                        active_index integer,
                        position_ms integer not null default 0,
                        updated_at text not null
                    );
                    """
                )
                self._ensure_column(
                    connection,
                    table="playback_queue",
                    column="position_ms",
                    definition="integer not null default 0",
                )
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("Failed to initialize playback state database") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute(f"pragma table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"alter table {table} add column {column} {definition}")

    def _encode_queue_item(self, item: QueueItem) -> dict[str, object]:
        return {
            "track": {
                "id": item.track.id,
                "title": item.track.title,
                "artists": list(item.track.artists),
                "artist_ids": list(item.track.artist_ids),
                "album_id": item.track.album_id,
                "album_title": item.track.album_title,
                "album_year": item.track.album_year,
                "duration_ms": item.track.duration_ms,
                "artwork_ref": item.track.artwork_ref,
                "available": item.track.available,
                "is_liked": item.track.is_liked,
            },
            "source_type": item.source_type,
            "source_id": item.source_id,
            "source_index": item.source_index,
        }

    def _decode_queue_item(self, payload: object) -> QueueItem:
        if not isinstance(payload, dict):
            raise TypeError("queue item must be a dict")
        raw_track = payload["track"]
        if not isinstance(raw_track, dict):
            raise TypeError("track must be a dict")
        raw_artists = raw_track["artists"]
        if not isinstance(raw_artists, list):
            raise TypeError("artists must be a list")
        return QueueItem(
            track=Track(
                id=str(raw_track["id"]),
                title=str(raw_track["title"]),
                artists=tuple(str(artist) for artist in raw_artists),
                artist_ids=tuple(
                    str(artist_id) for artist_id in raw_track.get("artist_ids", ())
                ),
                album_id=(
                    str(raw_track["album_id"]) if raw_track.get("album_id") is not None else None
                ),
                album_title=raw_track.get("album_title"),
                album_year=raw_track.get("album_year"),
                duration_ms=raw_track.get("duration_ms"),
                stream_ref=None,
                artwork_ref=raw_track.get("artwork_ref"),
                available=bool(raw_track.get("available", True)),
                is_liked=bool(raw_track.get("is_liked", False)),
            ),
            source_type=payload.get("source_type"),
            source_id=payload.get("source_id"),
            source_index=payload.get("source_index"),
        )
