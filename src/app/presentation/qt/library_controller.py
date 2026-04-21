from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from app.application.library_service import LibraryService
from app.application.search_service import SearchService
from app.domain import Album, Artist, CatalogSearchResults, Logger, Playlist, Station, Track
from app.domain.errors import DomainError


@dataclass(frozen=True, slots=True)
class BrowserItem:
    kind: str
    title: str
    subtitle: str | None
    payload: object
    source_type: str | None = None
    source_id: str | None = None
    source_tracks: tuple[Track, ...] = ()
    source_index: int | None = None


@dataclass(frozen=True, slots=True)
class BrowserContent:
    title: str
    items: tuple[BrowserItem, ...]
    recent_searches: tuple[str, ...] = ()
    source_type: str | None = None
    source_id: str | None = None
    source_owner_id: str | None = None
    source_tracks: tuple[Track, ...] = ()


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
        self._last_search_query: str | None = None
        self._last_search_results: CatalogSearchResults | None = None
        self._active_search_tab = "tracks"

    def initialize(self) -> None:
        self._emit_content(
            BrowserContent(title="Search", items=(), recent_searches=self.recent_searches())
        )

    def recent_searches(self) -> tuple[str, ...]:
        return self._search_service.load_recent_searches()

    def search_tracks(self, query: str) -> None:
        self._execute(
            lambda: self._search_content(query, tab=self._active_search_tab, refresh=True)
        )

    def show_search_tab(self, tab: str) -> None:
        self._active_search_tab = tab
        if self._last_search_results is None or self._last_search_query is None:
            return
        self._execute(
            lambda: self._search_content(
                self._last_search_query or "",
                tab=tab,
                refresh=False,
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
                items=(
                    *self._playlist_items(
                        self._library_service.load_generated_playlists(),
                        kind="generated_playlist",
                    ),
                    *self._playlist_items(
                        self._library_service.load_user_playlists(),
                        kind="playlist",
                    ),
                ),
                recent_searches=self.recent_searches(),
            )
        )

    def load_my_wave(self) -> None:
        self.open_station(Station(id="user:onyourwave", title="My Wave"))

    def open_playlist(self, playlist: Playlist) -> None:
        self._execute(
            lambda: self._source_content(
                title=playlist.title,
                source_type="generated_playlist" if playlist.is_generated else "playlist",
                source_id=playlist.id,
                source_owner_id=playlist.owner_id,
                tracks=self._library_service.load_playlist_tracks(
                    playlist.id,
                    owner_id=playlist.owner_id,
                ),
            )
        )

    def open_album(self, album: Album) -> None:
        self._execute(
            lambda: self._source_content(
                title=album.title,
                source_type="album",
                source_id=album.id,
                tracks=self._library_service.load_album_tracks(album.id),
            )
        )

    def open_station(self, station: Station) -> None:
        self._execute(
            lambda: self._source_content(
                title=station.title,
                source_type="station",
                source_id=station.id,
                tracks=self._library_service.load_station_tracks(station.id),
            )
        )

    def open_artist(self, artist: Artist) -> None:
        self._execute(
            lambda: self._source_content(
                title=f"{artist.name} | Top Tracks",
                source_type="artist",
                source_id=artist.id,
                tracks=self._library_service.load_artist_tracks(artist.id),
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

    def _search_content(self, query: str, *, tab: str, refresh: bool) -> BrowserContent:
        normalized_query = query.strip()
        if refresh or self._last_search_results is None:
            self._last_search_query = normalized_query
            self._last_search_results = self._search_service.search_catalog(normalized_query)

        results = self._last_search_results or CatalogSearchResults()
        title = f"Search: {normalized_query}" if normalized_query else "Search"
        return BrowserContent(
            title=f"{title} | {self._search_tab_title(tab)}",
            items=self._search_tab_items(results, tab=tab, query=normalized_query),
            recent_searches=self.recent_searches(),
        )

    def _source_content(
        self,
        *,
        title: str,
        source_type: str,
        source_id: str,
        tracks: tuple[Track, ...],
        source_owner_id: str | None = None,
    ) -> BrowserContent:
        return BrowserContent(
            title=title,
            items=self._track_items(
                tracks,
                source_type=source_type,
                source_id=source_id,
                source_tracks=tracks,
            ),
            recent_searches=self.recent_searches(),
            source_type=source_type,
            source_id=source_id,
            source_owner_id=source_owner_id,
            source_tracks=tracks,
        )

    def _track_items(
        self,
        tracks: tuple[Track, ...],
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        source_tracks: tuple[Track, ...] = (),
    ) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="track",
                title=f"{'❤️ ' if track.is_liked else ''}{track.title}",
                subtitle=self._track_subtitle(track, source_type=source_type),
                payload=track,
                source_type=source_type,
                source_id=source_id,
                source_tracks=source_tracks,
                source_index=index if source_tracks else None,
            )
            for index, track in enumerate(tracks)
        )

    def _search_tab_items(
        self,
        results: CatalogSearchResults,
        *,
        tab: str,
        query: str,
    ) -> tuple[BrowserItem, ...]:
        if tab == "albums":
            return self._album_items(results.albums)
        if tab == "singles":
            return self._album_items(results.singles)
        if tab == "compilations":
            return self._album_items(results.compilations)
        if tab == "playlists":
            return self._playlist_items(results.playlists, kind="playlist")
        if tab == "artists":
            return self._artist_items(results.artists)
        if tab == "artist_radio":
            return self._artist_radio_items(results.artists)
        return self._track_items(results.tracks)

    def _search_tab_title(self, tab: str) -> str:
        return {
            "albums": "Albums",
            "singles": "Singles",
            "compilations": "Compilations",
            "playlists": "Playlists",
            "artists": "Artists",
            "artist_radio": "Artist Radio",
            "tracks": "Tracks",
        }.get(tab, "Tracks")

    def _album_items(self, albums: tuple[Album, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="album",
                title=album.title,
                subtitle=self._album_subtitle(album),
                payload=album,
            )
            for album in albums
        )

    def _artist_items(self, artists: tuple[Artist, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="artist",
                title=artist.name,
                subtitle="Artist",
                payload=artist,
            )
            for artist in artists
        )

    def _artist_radio_items(self, artists: tuple[Artist, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="artist_radio",
                title=f"{artist.name} Radio",
                subtitle="Artist radio",
                payload=Station(id=f"artist:{artist.id}", title=f"{artist.name} Radio"),
            )
            for artist in artists
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

    def _track_subtitle(self, track: Track, *, source_type: str | None) -> str:
        artists = ", ".join(track.artists)
        if source_type is None:
            return artists
        context = source_type.title()
        return f"{artists} | {context}" if artists else context

    def _album_subtitle(self, album: Album) -> str | None:
        parts = [", ".join(album.artists)]
        if album.year is not None:
            parts.append(str(album.year))
        if album.track_count is not None:
            parts.append(f"{album.track_count} tracks")
        return " | ".join(part for part in parts if part) or None
