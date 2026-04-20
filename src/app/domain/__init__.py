"""Domain layer exports."""

from app.domain.auth import AuthSession
from app.domain.errors import (
    AuthError,
    NetworkError,
    PlaybackBackendError,
    StorageError,
    StreamResolveError,
    TrackUnavailableError,
)
from app.domain.playback import PlaybackState, PlaybackStatus, QueueItem, RepeatMode
from app.domain.playlist import Playlist
from app.domain.protocols import (
    AuthRepo,
    Clock,
    LibraryCacheRepo,
    Logger,
    MusicService,
    PlaybackEngine,
    SettingsRepo,
)
from app.domain.station import Station
from app.domain.track import Track

__all__ = [
    "AuthError",
    "AuthRepo",
    "AuthSession",
    "Clock",
    "LibraryCacheRepo",
    "Logger",
    "MusicService",
    "NetworkError",
    "PlaybackBackendError",
    "PlaybackEngine",
    "PlaybackState",
    "PlaybackStatus",
    "Playlist",
    "QueueItem",
    "RepeatMode",
    "SettingsRepo",
    "Station",
    "StorageError",
    "StreamResolveError",
    "Track",
    "TrackUnavailableError",
]
