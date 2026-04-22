from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.domain import LibraryCacheRepo, LikedTrackIds, Track
from app.domain.errors import StorageError


class FileLibraryCacheRepo(LibraryCacheRepo):
    _CACHE_TTL = timedelta(days=7)

    def __init__(self, *, file_path: Path) -> None:
        self._file_path = file_path

    def load_recent_searches(self) -> tuple[str, ...]:
        payload = self._load_payload()
        searches = payload.get("recent_searches", ())
        if not isinstance(searches, list) or not all(isinstance(item, str) for item in searches):
            raise StorageError("Library cache recent searches are invalid")
        return tuple(searches)

    def save_recent_searches(self, searches: tuple[str, ...] | list[str]) -> None:
        payload = self._load_payload()
        payload["recent_searches"] = list(searches)
        self._save_payload(payload)

    def load_track_metadata(self, track_id: str) -> Track | None:
        payload = self._load_payload()
        tracks = payload.get("tracks", {})
        if not isinstance(tracks, dict):
            raise StorageError("Library cache track metadata is invalid")
        raw_track = tracks.get(track_id)
        if raw_track is None:
            return None
        if not isinstance(raw_track, dict):
            raise StorageError("Library cache track entry is invalid")
        if self._is_expired(raw_track.get("cached_at")):
            return None
        try:
            return Track(
                id=str(raw_track["id"]),
                title=str(raw_track["title"]),
                artists=tuple(str(artist) for artist in raw_track.get("artists", ())),
                album_title=self._optional_str(raw_track.get("album_title")),
                album_year=self._optional_int(raw_track.get("album_year")),
                duration_ms=self._optional_int(raw_track.get("duration_ms")),
                stream_ref=self._optional_str(raw_track.get("stream_ref")),
                artwork_ref=self._optional_str(raw_track.get("artwork_ref")),
                available=bool(raw_track.get("available", True)),
                is_liked=bool(raw_track.get("is_liked", False)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageError("Library cache track entry is invalid") from exc

    def save_track_metadata(self, track: Track) -> None:
        payload = self._load_payload()
        tracks = payload.setdefault("tracks", {})
        if not isinstance(tracks, dict):
            raise StorageError("Library cache track metadata is invalid")
        tracks[track.id] = {
            "id": track.id,
            "title": track.title,
            "artists": list(track.artists),
            "album_title": track.album_title,
            "album_year": track.album_year,
            "duration_ms": track.duration_ms,
            "stream_ref": track.stream_ref,
            "artwork_ref": track.artwork_ref,
            "available": track.available,
            "is_liked": track.is_liked,
            "cached_at": self._now_iso(),
        }
        self._save_payload(payload)

    def load_liked_track_ids(self, user_id: str) -> LikedTrackIds | None:
        payload = self._load_payload()
        liked_tracks = payload.get("liked_tracks", {})
        if not isinstance(liked_tracks, dict):
            raise StorageError("Library cache liked tracks are invalid")
        raw_state = liked_tracks.get(user_id)
        if raw_state is None:
            return None
        if not isinstance(raw_state, dict):
            raise StorageError("Library cache liked track entry is invalid")
        raw_ids = raw_state.get("track_ids", ())
        if not isinstance(raw_ids, list):
            raise StorageError("Library cache liked track ids are invalid")
        return LikedTrackIds(
            user_id=user_id,
            revision=int(raw_state.get("revision", 0) or 0),
            track_ids=frozenset(self._normalize_track_id(str(track_id)) for track_id in raw_ids),
        )

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds) -> None:
        payload = self._load_payload()
        raw_liked_tracks = payload.setdefault("liked_tracks", {})
        if not isinstance(raw_liked_tracks, dict):
            raise StorageError("Library cache liked tracks are invalid")
        raw_liked_tracks[liked_tracks.user_id] = {
            "revision": liked_tracks.revision,
            "track_ids": sorted(liked_tracks.track_ids),
            "synced_at": self._now_iso(),
        }
        self._save_payload(payload)

    def mark_track_liked(self, user_id: str, track_id: str) -> None:
        state = self.load_liked_track_ids(user_id)
        track_ids = set(state.track_ids if state is not None else ())
        track_ids.add(self._normalize_track_id(track_id))
        self.save_liked_track_ids(
            LikedTrackIds(
                user_id=user_id,
                revision=state.revision if state is not None else 0,
                track_ids=frozenset(track_ids),
            )
        )

    def mark_track_unliked(self, user_id: str, track_id: str) -> None:
        state = self.load_liked_track_ids(user_id)
        if state is None:
            return
        track_ids = set(state.track_ids)
        track_ids.discard(self._normalize_track_id(track_id))
        self.save_liked_track_ids(
            LikedTrackIds(
                user_id=user_id,
                revision=state.revision,
                track_ids=frozenset(track_ids),
            )
        )

    def load_artwork_ref(self, item_id: str) -> str | None:
        payload = self._load_payload()
        artwork = payload.get("artwork", {})
        if not isinstance(artwork, dict):
            raise StorageError("Library cache artwork map is invalid")
        value = artwork.get(item_id)
        if isinstance(value, str):
            return value
        if not isinstance(value, dict):
            return None
        if self._is_expired(value.get("cached_at")):
            return None
        artwork_ref = value.get("ref")
        return artwork_ref if isinstance(artwork_ref, str) else None

    def save_artwork_ref(self, item_id: str, artwork_ref: str) -> None:
        payload = self._load_payload()
        artwork = payload.setdefault("artwork", {})
        if not isinstance(artwork, dict):
            raise StorageError("Library cache artwork map is invalid")
        artwork[item_id] = {"ref": artwork_ref, "cached_at": self._now_iso()}
        self._save_payload(payload)

    def _load_payload(self) -> dict[str, Any]:
        if not self._file_path.exists():
            return {"recent_searches": [], "tracks": {}, "artwork": {}, "liked_tracks": {}}
        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError("Failed to load library cache") from exc

        if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
            return {"recent_searches": payload, "tracks": {}, "artwork": {}}
        if not isinstance(payload, dict):
            raise StorageError("Library cache file is invalid")
        known_keys = {"recent_searches", "tracks", "artwork", "liked_tracks"}
        if not any(key in payload for key in known_keys):
            raise StorageError("Library cache file is invalid")
        payload.setdefault("recent_searches", [])
        payload.setdefault("tracks", {})
        payload.setdefault("artwork", {})
        payload.setdefault("liked_tracks", {})
        return payload

    def _save_payload(self, payload: dict[str, Any]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
        except OSError as exc:
            raise StorageError("Failed to save library cache") from exc

    def _optional_str(self, value: object) -> str | None:
        if value is None:
            return None
        return str(value)

    def _optional_int(self, value: object) -> int | None:
        if value is None:
            return None
        return int(value)

    def _now_iso(self) -> str:
        return datetime.now(tz=UTC).isoformat()

    def _is_expired(self, raw_value: object) -> bool:
        if not isinstance(raw_value, str):
            return False
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
