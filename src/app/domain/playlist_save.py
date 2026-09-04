from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.errors import DomainError
from app.domain.playlist import Playlist
from app.domain.track import Track


class PlaylistSaveMode(str, Enum):
    CREATE = "create"
    APPEND = "append"
    REPLACE = "replace"


class PlaylistVisibility(str, Enum):
    PRIVATE = "private"
    PUBLIC = "public"


@dataclass(frozen=True, slots=True)
class PlaylistSaveRequest:
    tracks: tuple[Track, ...]
    mode: PlaylistSaveMode
    title: str | None = None
    visibility: PlaylistVisibility = PlaylistVisibility.PRIVATE
    target: Playlist | None = None


@dataclass(frozen=True, slots=True)
class PlaylistSaveResult:
    playlist: Playlist
    saved_count: int
    skipped_count: int
    user_playlists: tuple[Playlist, ...]


class PlaylistSaveValidationError(DomainError):
    pass


class PlaylistNameConflictError(PlaylistSaveValidationError):
    def __init__(self, title: str) -> None:
        super().__init__(title)
        self.title = title


class PlaylistTargetNotFoundError(PlaylistSaveValidationError):
    pass


class NoSaveableTracksError(PlaylistSaveValidationError):
    pass
