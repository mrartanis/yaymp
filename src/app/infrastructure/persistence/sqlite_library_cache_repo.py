from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.domain import LibraryCacheRepo, LikedTrackIds, Track
from app.domain.errors import StorageError


class SQLiteLibraryCacheRepo(LibraryCacheRepo):
    _CACHE_TTL = timedelta(days=7)

    def __init__(self, *, db_path: Path) -> None:
        self._db_path = db_path
        self._initialize()

    def load_recent_searches(self) -> tuple[str, ...]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "select query from recent_searches order by position asc"
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load recent searches") from exc
        return tuple(str(row["query"]) for row in rows)

    def save_recent_searches(self, searches: Sequence[str]) -> None:
        try:
            with self._connect() as connection:
                connection.execute("delete from recent_searches")
                connection.executemany(
                    (
                        "insert into recent_searches(query, position, updated_at) "
                        "values (?, ?, ?)"
                    ),
                    [
                        (query, position, self._now_iso())
                        for position, query in enumerate(searches)
                    ],
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save recent searches") from exc

    def load_track_metadata(self, track_id: str) -> Track | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "select * from tracks where id = ?",
                    (track_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load cached track metadata") from exc

        if row is None:
            return None
        if self._is_expired(row["cached_at"]):
            return None
        try:
            artists = json.loads(row["artists_json"])
            if not isinstance(artists, list):
                raise TypeError("artists_json must be a list")
            return Track(
                id=str(row["id"]),
                title=str(row["title"]),
                artists=tuple(str(artist) for artist in artists),
                album_title=row["album_title"],
                album_year=row["album_year"],
                duration_ms=row["duration_ms"],
                stream_ref=row["stream_ref"],
                artwork_ref=row["artwork_ref"],
                available=bool(row["available"]),
                is_liked=bool(row["is_liked"]),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise StorageError("Cached track metadata is invalid") from exc

    def save_track_metadata(self, track: Track) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into tracks("
                        "id, title, artists_json, album_title, album_year, duration_ms, "
                        "stream_ref, artwork_ref, available, is_liked, cached_at"
                        ") values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "on conflict(id) do update set "
                        "title = excluded.title, "
                        "artists_json = excluded.artists_json, "
                        "album_title = excluded.album_title, "
                        "album_year = excluded.album_year, "
                        "duration_ms = excluded.duration_ms, "
                        "stream_ref = excluded.stream_ref, "
                        "artwork_ref = excluded.artwork_ref, "
                        "available = excluded.available, "
                        "is_liked = excluded.is_liked, "
                        "cached_at = excluded.cached_at"
                    ),
                    (
                        track.id,
                        track.title,
                        json.dumps(list(track.artists), ensure_ascii=True),
                        track.album_title,
                        track.album_year,
                        track.duration_ms,
                        track.stream_ref,
                        track.artwork_ref,
                        int(track.available),
                        int(track.is_liked),
                        self._now_iso(),
                    ),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save cached track metadata") from exc

    def load_liked_track_ids(self, user_id: str) -> LikedTrackIds | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "select revision from liked_track_sync where user_id = ?",
                    (user_id,),
                ).fetchone()
                if row is None:
                    return None
                rows = connection.execute(
                    "select track_id from liked_tracks where user_id = ?",
                    (user_id,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load liked track ids") from exc
        return LikedTrackIds(
            user_id=user_id,
            revision=int(row["revision"]),
            track_ids=frozenset(str(item["track_id"]) for item in rows),
        )

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds) -> None:
        try:
            with self._connect() as connection:
                now = self._now_iso()
                connection.execute("begin")
                connection.execute(
                    "delete from liked_tracks where user_id = ?",
                    (liked_tracks.user_id,),
                )
                connection.executemany(
                    (
                        "insert into liked_tracks(user_id, track_id, updated_at) "
                        "values (?, ?, ?)"
                    ),
                    [
                        (liked_tracks.user_id, track_id, now)
                        for track_id in sorted(liked_tracks.track_ids)
                    ],
                )
                connection.execute(
                    (
                        "insert into liked_track_sync(user_id, revision, synced_at) "
                        "values (?, ?, ?) "
                        "on conflict(user_id) do update set "
                        "revision = excluded.revision, "
                        "synced_at = excluded.synced_at"
                    ),
                    (liked_tracks.user_id, liked_tracks.revision, now),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save liked track ids") from exc

    def mark_track_liked(self, user_id: str, track_id: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into liked_tracks(user_id, track_id, updated_at) "
                        "values (?, ?, ?) "
                        "on conflict(user_id, track_id) do update set "
                        "updated_at = excluded.updated_at"
                    ),
                    (user_id, self._normalize_track_id(track_id), self._now_iso()),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to mark track liked") from exc

    def mark_track_unliked(self, user_id: str, track_id: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    "delete from liked_tracks where user_id = ? and track_id = ?",
                    (user_id, self._normalize_track_id(track_id)),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to mark track unliked") from exc

    def load_artwork_ref(self, item_id: str) -> str | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "select artwork_ref, cached_at from artwork where item_id = ?",
                    (item_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError("Failed to load cached artwork reference") from exc

        if row is None or self._is_expired(row["cached_at"]):
            return None
        return str(row["artwork_ref"])

    def save_artwork_ref(self, item_id: str, artwork_ref: str) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    (
                        "insert into artwork(item_id, artwork_ref, cached_at) "
                        "values (?, ?, ?) "
                        "on conflict(item_id) do update set "
                        "artwork_ref = excluded.artwork_ref, "
                        "cached_at = excluded.cached_at"
                    ),
                    (item_id, artwork_ref, self._now_iso()),
                )
        except sqlite3.Error as exc:
            raise StorageError("Failed to save cached artwork reference") from exc

    def _initialize(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.executescript(
                    """
                    create table if not exists recent_searches (
                        query text primary key,
                        position integer not null,
                        updated_at text not null
                    );

                    create table if not exists tracks (
                        id text primary key,
                        title text not null,
                        artists_json text not null,
                        album_title text,
                        album_year integer,
                        duration_ms integer,
                        stream_ref text,
                        artwork_ref text,
                        available integer not null,
                        is_liked integer not null,
                        cached_at text not null
                    );

                    create table if not exists artwork (
                        item_id text primary key,
                        artwork_ref text not null,
                        cached_at text not null
                    );

                    create table if not exists liked_track_sync (
                        user_id text primary key,
                        revision integer not null,
                        synced_at text not null
                    );

                    create table if not exists liked_tracks (
                        user_id text not null,
                        track_id text not null,
                        updated_at text not null,
                        primary key (user_id, track_id)
                    );
                    """
                )
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("Failed to initialize library cache database") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _now_iso(self) -> str:
        return datetime.now(tz=UTC).isoformat()

    def _is_expired(self, raw_value: Any) -> bool:
        if not isinstance(raw_value, str):
            return True
        try:
            cached_at = datetime.fromisoformat(raw_value)
        except ValueError:
            return True
        if cached_at.tzinfo is None:
            cached_at = cached_at.replace(tzinfo=UTC)
        return datetime.now(tz=UTC) - cached_at > self._CACHE_TTL

    def _normalize_track_id(self, track_id: str) -> str:
        raw_track_id = str(track_id)
        base_id, separator, album_id = raw_track_id.partition(":")
        if separator and base_id.isdigit() and album_id.isdigit():
            return base_id
        return raw_track_id
