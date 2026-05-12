from __future__ import annotations

from dataclasses import dataclass

from app.domain.track import Track


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    title: str
    description: str | None = None
    icon_ref: str | None = None


@dataclass(frozen=True, slots=True)
class StationTrackBatch:
    station_id: str
    batch_id: str | None
    tracks: tuple[Track, ...]
