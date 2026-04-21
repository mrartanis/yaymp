from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from app.application.library_service import LibraryService
from app.application.search_service import SearchService
from app.domain import Logger, Playlist, Station, Track
from app.domain.errors import DomainError


@dataclass(frozen=True, slots=True)
class BrowserItem:
    kind: str
    title: str
    subtitle: str | None
    payload: object


@dataclass(frozen=True, slots=True)
class BrowserContent:
    title: str
    items: tuple[BrowserItem, ...]
    recent_searches: tuple[str, ...] = ()


class LibraryController(QObject):
    content_changed = Signal(object)
    content_failed = Signal(str)
    track_liked = Signal(object)
    track_unliked = Signal(object)

    def __init__(
        self,
        *,
        search_service: SearchService,
        library_service: LibraryService,
        logger: Logger,
    ) -> None:
        super().__init__()
        self._search_service = search_service
        self._library_service = library_service
        self._logger = logger

    def initialize(self) -> None:
        self._emit_content(
            BrowserContent(title="Search", items=(), recent_searches=self.recent_searches())
        )

    def recent_searches(self) -> tuple[str, ...]:
        return self._search_service.load_recent_searches()

    def search_tracks(self, query: str) -> None:
        self._execute(
            lambda: BrowserContent(
                title=f"Search: {query.strip()}",
                items=tuple(
                    BrowserItem(
                        kind="track",
                        title=track.title,
                        subtitle=", ".join(track.artists),
                        payload=track,
                    )
                    for track in self._search_service.search_tracks(query)
                ),
                recent_searches=self.recent_searches(),
            )
        )

    def load_liked_tracks(self) -> None:
        self._execute(
            lambda: BrowserContent(
                title="My Tracks",
                items=self._track_items(self._library_service.load_liked_tracks()),
                recent_searches=self.recent_searches(),
            )
        )

    def load_playlists(self) -> None:
        self._execute(
            lambda: BrowserContent(
                title="Playlists",
                items=self._playlist_items(
                    self._library_service.load_user_playlists(),
                    kind="playlist",
                ),
                recent_searches=self.recent_searches(),
            )
        )

    def load_my_wave(self) -> None:
        self.open_station(Station(id="user:onyourwave", title="My Wave"))

    def open_playlist(self, playlist: Playlist) -> None:
        self._execute(
            lambda: BrowserContent(
                title=playlist.title,
                items=self._track_items(self._library_service.load_playlist_tracks(playlist.id)),
                recent_searches=self.recent_searches(),
            )
        )

    def open_station(self, station: Station) -> None:
        self._execute(
            lambda: BrowserContent(
                title=station.title,
                items=self._track_items(self._library_service.load_station_tracks(station.id)),
                recent_searches=self.recent_searches(),
            )
        )

    def like_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self.track_liked.emit(self._library_service.like_track(track))
        )

    def unlike_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self.track_unliked.emit(self._library_service.unlike_track(track))
        )

    def _execute(self, operation) -> None:
        try:
            self._emit_content(operation())
        except DomainError as exc:
            self._logger.warning("Library operation failed: %s", exc)
            self.content_failed.emit(str(exc))

    def _execute_mutation(self, operation) -> None:
        try:
            operation()
        except DomainError as exc:
            self._logger.warning("Library mutation failed: %s", exc)
            self.content_failed.emit(str(exc))

    def _emit_content(self, content: BrowserContent) -> None:
        self.content_changed.emit(content)

    def _track_items(self, tracks: tuple[Track, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="track",
                title=f"{'❤️ ' if track.is_liked else ''}{track.title}",
                subtitle=", ".join(track.artists),
                payload=track,
            )
            for track in tracks
        )

    def _playlist_items(
        self,
        playlists: tuple[Playlist, ...],
        *,
        kind: str,
    ) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind=kind,
                title=playlist.title,
                subtitle=playlist.description or playlist.owner_name,
                payload=playlist,
            )
            for playlist in playlists
        )

    def _station_items(self, stations: tuple[Station, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="station",
                title=station.title,
                subtitle=station.description,
                payload=station,
            )
            for station in stations
        )
