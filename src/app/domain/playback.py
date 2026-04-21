from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.track import Track


class PlaybackStatus(str, Enum):
    STOPPED = "stopped"
    PAUSED = "paused"
    PLAYING = "playing"
    BUFFERING = "buffering"


class RepeatMode(str, Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class QueueItem:
    track: Track
    source_type: str | None = None
    source_id: str | None = None
    source_index: int | None = None


@dataclass(frozen=True, slots=True)
class PlaybackState:
    status: PlaybackStatus = PlaybackStatus.STOPPED
    active_index: int | None = None
    position_ms: int = 0
    duration_ms: int | None = None
    volume: int = 100
    shuffle_enabled: bool = False
    repeat_mode: RepeatMode = RepeatMode.OFF
    audio_codec: str | None = None
    audio_bitrate: int | None = None
