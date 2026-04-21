from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    title: str
    artists: tuple[str, ...]
    album_title: str | None = None
    album_year: int | None = None
    duration_ms: int | None = None
    stream_ref: str | None = None
    artwork_ref: str | None = None
    available: bool = True
    is_liked: bool = False
