from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    title: str
    artists: tuple[str, ...]
    artist_ids: tuple[str, ...] = ()
    album_id: str | None = None
    album_title: str | None = None
    album_year: int | None = None
    duration_ms: int | None = None
    stream_ref: str | None = None
    artwork_ref: str | None = None
    available: bool = True
    is_liked: bool = False


@dataclass(frozen=True, slots=True)
class LikedTrackIds:
    user_id: str
    revision: int
    track_ids: frozenset[str]
