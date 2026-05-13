from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from app.application.error_presenter import user_facing_error_message
from app.application.library_service import LibraryService
from app.application.search_service import SearchService
from app.domain import Album, Artist, CatalogSearchResults, Logger, Playlist, Station, Track
from app.domain.errors import DomainError
from app.presentation.qt.track_display import display_track_title


@dataclass(frozen=True, slots=True)
class BrowserTab:
    id: str
    title: str


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
    tabs: tuple[BrowserTab, ...] = ()
    active_tab: str | None = None
    search_query: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    source_tracks: tuple[Track, ...] = ()
    bulk_mode: str = "loaded_only"
    list_key: str | None = None
    has_more: bool = False
    is_loading: bool = False


@dataclass(frozen=True, slots=True)
class BrowserHistoryEntry:
    page: str
    payload: object | None = None
    active_tab: str | None = None
    search_query: str | None = None
    liked_tracks_limit: int | None = None
    list_kind: str | None = None


class _SearchWorker(QObject):
    search_ready = Signal(int, str, object)
    search_failed = Signal(int, str)

    def __init__(self, *, search_service: SearchService, logger: Logger) -> None:
        super().__init__()
        self._search_service = search_service
        self._logger = logger

    @Slot(int, str)
    def run_search(self, request_id: int, query: str) -> None:
        try:
            results = self._search_service.search_catalog(query)
        except DomainError as exc:
            self._logger.warning("Library search failed: %s", exc)
            self.search_failed.emit(request_id, user_facing_error_message(exc))
            return
        self.search_ready.emit(request_id, query, results)


class LibraryController(QObject):
    content_changed = Signal(object)
    content_failed = Signal(str)
    track_liked = Signal(object)
    track_unliked = Signal(object)
    album_liked = Signal(object)
    album_unliked = Signal(object)
    artist_liked = Signal(object)
    artist_unliked = Signal(object)
    playlist_liked = Signal(object)
    playlist_unliked = Signal(object)
    _search_requested = Signal(int, str)

    def __init__(
        self,
        *,
        search_service: SearchService,
        library_service: LibraryService,
        logger: Logger,
        translate: Callable[..., str],
    ) -> None:
        super().__init__()
        self._search_service = search_service
        self._library_service = library_service
        self._logger = logger
        self._t = translate
        self._last_search_query: str | None = None
        self._last_search_results: CatalogSearchResults | None = None
        self._active_search_tab = "tracks"
        self._active_artist_tab = "top_tracks"
        self._active_page: tuple[str, object | None] = ("search", None)
        self._active_list_kind: str | None = None
        self._liked_tracks_limit = 100
        self._history: list[BrowserHistoryEntry] = []
        self._search_request_id = 0
        self._search_thread = QThread(self)
        self._search_worker = _SearchWorker(
            search_service=search_service,
            logger=logger,
        )
        self._search_worker.moveToThread(self._search_thread)
        self._search_requested.connect(
            self._search_worker.run_search,
            Qt.ConnectionType.QueuedConnection,
        )
        self._search_worker.search_ready.connect(self._handle_search_ready)
        self._search_worker.search_failed.connect(self._handle_search_failed)
        self._search_thread.finished.connect(self._search_worker.deleteLater)
        self._search_thread.start()

    def initialize(self) -> None:
        self._emit_content(self._empty_search_content(self._active_search_tab))

    def refresh_localized_content(self) -> None:
        page, payload = self._active_page
        if page == "search":
            if self._last_search_results is None or self._last_search_query is None:
                self._emit_content(self._empty_search_content(self._active_search_tab))
                return
            self._emit_content(
                self._search_content(
                    self._last_search_query,
                    tab=self._active_search_tab,
                    refresh=False,
                )
            )
            return
        if page == "artist" and isinstance(payload, Artist):
            self._execute(lambda: self._artist_content(payload, tab=self._active_artist_tab))
            return
        if page == "source" and isinstance(payload, Playlist):
            self._execute(
                lambda: self._source_content(
                    title=payload.title,
                    source_type="playlist",
                    source_id=payload.id,
                    tracks=self._library_service.load_playlist_tracks(
                        payload.id,
                        owner_id=payload.owner_id,
                    ),
                )
            )
            return
        if page == "source" and isinstance(payload, Album):
            self._execute(
                lambda: self._source_content(
                    title=payload.title,
                    source_type="album",
                    source_id=payload.id,
                    tracks=self._library_service.load_album_tracks(payload.id),
                )
            )
            return
        if page == "source" and isinstance(payload, Station):
            self._execute(
                lambda: self._source_content(
                    title=self._station_title(payload),
                    source_type="station",
                    source_id=payload.id,
                    tracks=self._library_service.load_station_tracks(payload.id),
                )
            )
            return
        if page == "list":
            if self._active_list_kind == "liked_tracks":
                self._execute(lambda: self._liked_tracks_content(limit=self._liked_tracks_limit))
                return
            if self._active_list_kind == "liked_albums":
                self._execute(
                    lambda: BrowserContent(
                        title=self._t("library.list.my_albums"),
                        items=self._album_items(self._library_service.load_liked_albums()),
                        recent_searches=self.recent_searches(),
                    )
                )
                return
            if self._active_list_kind == "liked_artists":
                self._execute(
                    lambda: BrowserContent(
                        title=self._t("library.list.my_artists"),
                        items=self._artist_items(self._library_service.load_liked_artists()),
                        recent_searches=self.recent_searches(),
                    )
                )
                return
            if self._active_list_kind == "playlists":
                self._execute(
                    lambda: BrowserContent(
                        title=self._t("library.list.playlists"),
                        items=(
                            *self._playlist_items(
                                self._library_service.load_generated_playlists(),
                                kind="generated_playlist",
                            ),
                            *self._playlist_items(
                                self._unique_playlists(
                                    self._library_service.load_liked_playlists(),
                                    self._library_service.load_user_playlists(),
                                ),
                                kind="playlist",
                            ),
                        ),
                        recent_searches=self.recent_searches(),
                    )
                )

    def shutdown(self) -> None:
        self._search_thread.quit()
        self._search_thread.wait(3000)

    def recent_searches(self) -> tuple[str, ...]:
        return self._search_service.load_recent_searches()

    def load_full_current_source_tracks(self) -> tuple[tuple[Track, ...], str, str] | None:
        page, payload = self._active_page
        if page == "list" and self._active_list_kind == "liked_tracks":
            return (
                self._library_service.load_all_liked_tracks(),
                "collection",
                "liked_tracks",
            )
        if page == "source" and isinstance(payload, Playlist):
            return (
                self._library_service.load_all_playlist_tracks(
                    payload.id,
                    owner_id=payload.owner_id,
                ),
                "playlist",
                payload.id,
            )
        if page == "source" and isinstance(payload, Album):
            return (
                self._library_service.load_all_album_tracks(payload.id),
                "album",
                payload.id,
            )
        if (
            page == "artist"
            and isinstance(payload, Artist)
            and self._active_artist_tab == "top_tracks"
        ):
            return (
                self._library_service.load_all_artist_tracks(payload.id),
                "artist",
                payload.id,
            )
        return None

    def show_search_page(self) -> None:
        if self._active_page != ("search", None):
            self._push_history()
        self._active_page = ("search", None)
        self._active_list_kind = None
        if self._last_search_results is None or self._last_search_query is None:
            self._emit_content(self._empty_search_content(self._active_search_tab))
            return
        self._execute(
            lambda: self._search_content(
                self._last_search_query or "",
                tab=self._active_search_tab,
                refresh=False,
            )
        )

    def search_tracks(self, query: str) -> None:
        normalized_query = query.strip()
        if self._active_page != ("search", None) or (
            self._last_search_query is not None
            and normalized_query
            and normalized_query != self._last_search_query
        ):
            self._push_history()
        self._active_page = ("search", None)
        self._active_list_kind = None
        self._dispatch_search(normalized_query)

    def show_browser_tab(self, tab: str) -> None:
        page, payload = self._active_page
        if page == "artist" and isinstance(payload, Artist):
            self._active_artist_tab = tab
            self._execute(lambda: self._artist_content(payload, tab=tab))
            return
        if page == "search":
            self._active_search_tab = tab
            if self._last_search_results is None or self._last_search_query is None:
                self._emit_content(self._empty_search_content(tab))
                return
            self._execute(
                lambda: self._search_content(
                    self._last_search_query or "",
                    tab=tab,
                    refresh=False,
                )
            )

    def load_liked_tracks(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_tracks"
        self._liked_tracks_limit = 100
        self._execute(lambda: self._liked_tracks_content(limit=self._liked_tracks_limit))

    def load_more_current_list(self) -> None:
        page, _payload = self._active_page
        if page != "list":
            return
        self._liked_tracks_limit += 100
        self._execute(lambda: self._liked_tracks_content(limit=self._liked_tracks_limit))

    def load_liked_albums(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_albums"
        self._execute(
            lambda: BrowserContent(
                title=self._t("library.list.my_albums"),
                items=self._album_items(self._library_service.load_liked_albums()),
                recent_searches=self.recent_searches(),
            )
        )

    def load_liked_artists(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_artists"
        self._execute(
            lambda: BrowserContent(
                title=self._t("library.list.my_artists"),
                items=self._artist_items(self._library_service.load_liked_artists()),
                recent_searches=self.recent_searches(),
            )
        )

    def load_playlists(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "playlists"
        self._execute(
            lambda: BrowserContent(
                title=self._t("library.list.playlists"),
                items=(
                    *self._playlist_items(
                        self._library_service.load_generated_playlists(),
                        kind="generated_playlist",
                    ),
                    *self._playlist_items(
                        self._unique_playlists(
                            self._library_service.load_liked_playlists(),
                            self._library_service.load_user_playlists(),
                        ),
                        kind="playlist",
                    ),
                ),
                recent_searches=self.recent_searches(),
            )
        )

    def load_my_wave(self) -> None:
        self.open_station(Station(id="user:onyourwave", title=self._t("nav.my_wave")))

    def open_playlist(self, playlist: Playlist) -> None:
        self._push_history()
        self._active_page = ("source", playlist)
        self._active_list_kind = None
        self._execute(
            lambda: self._source_content(
                title=playlist.title,
                source_type="playlist",
                source_id=playlist.id,
                tracks=self._library_service.load_playlist_tracks(
                    playlist.id,
                    owner_id=playlist.owner_id,
                ),
            )
        )

    def open_album(self, album: Album) -> None:
        self._push_history()
        self._active_page = ("source", album)
        self._active_list_kind = None
        self._execute(
            lambda: self._source_content(
                title=album.title,
                source_type="album",
                source_id=album.id,
                tracks=self._library_service.load_album_tracks(album.id),
            )
        )

    def open_album_by_id(self, album_id: str) -> None:
        try:
            album = self._library_service.load_album(album_id)
        except DomainError as exc:
            self._logger.warning("Library operation failed: %s", exc)
            self.content_failed.emit(user_facing_error_message(exc))
            return
        self.open_album(album)

    def open_station(self, station: Station) -> None:
        self._push_history()
        self._active_page = ("source", station)
        self._active_list_kind = None
        self._execute(
            lambda: self._source_content(
                title=station.title,
                source_type="station",
                source_id=station.id,
                tracks=self._library_service.load_station_tracks(station.id),
            )
        )

    def open_artist(self, artist: Artist) -> None:
        self._push_history()
        self._active_page = ("artist", artist)
        self._active_artist_tab = "top_tracks"
        self._active_list_kind = None
        self._execute(lambda: self._artist_content(artist, tab="top_tracks"))

    def can_go_back(self) -> bool:
        return bool(self._history)

    def go_back(self) -> None:
        if not self._history:
            return
        entry = self._history.pop()
        self._restore_history_entry(entry)

    def like_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self.track_liked.emit(self._library_service.like_track(track))
        )

    def unlike_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self.track_unliked.emit(self._library_service.unlike_track(track))
        )

    def like_album(self, album: Album) -> None:
        self._execute_mutation(
            lambda: self.album_liked.emit(self._library_service.like_album(album))
        )

    def unlike_album(self, album: Album) -> None:
        self._execute_mutation(
            lambda: self.album_unliked.emit(self._library_service.unlike_album(album))
        )

    def like_artist(self, artist: Artist) -> None:
        self._execute_mutation(
            lambda: self.artist_liked.emit(self._library_service.like_artist(artist))
        )

    def unlike_artist(self, artist: Artist) -> None:
        self._execute_mutation(
            lambda: self.artist_unliked.emit(self._library_service.unlike_artist(artist))
        )

    def like_playlist(self, playlist: Playlist) -> None:
        self._execute_mutation(
            lambda: self.playlist_liked.emit(self._library_service.like_playlist(playlist))
        )

    def unlike_playlist(self, playlist: Playlist) -> None:
        self._execute_mutation(
            lambda: self.playlist_unliked.emit(self._library_service.unlike_playlist(playlist))
        )

    def _execute(self, operation) -> None:
        try:
            self._emit_content(operation())
        except DomainError as exc:
            self._logger.warning("Library operation failed: %s", exc)
            self.content_failed.emit(user_facing_error_message(exc))

    def _execute_mutation(self, operation) -> None:
        try:
            operation()
        except DomainError as exc:
            self._logger.warning("Library mutation failed: %s", exc)
            self.content_failed.emit(user_facing_error_message(exc))

    def _emit_content(self, content: BrowserContent) -> None:
        self.content_changed.emit(content)

    def _push_history(self) -> None:
        entry = self._current_history_entry()
        if entry is None:
            return
        self._history.append(entry)

    def _current_history_entry(self) -> BrowserHistoryEntry | None:
        page, payload = self._active_page
        if page == "search":
            return BrowserHistoryEntry(
                page="search",
                active_tab=self._active_search_tab,
                search_query=self._last_search_query,
            )
        if page == "artist" and isinstance(payload, Artist):
            return BrowserHistoryEntry(
                page="artist",
                payload=payload,
                active_tab=self._active_artist_tab,
            )
        if page == "source" and isinstance(payload, (Album, Playlist, Station)):
            return BrowserHistoryEntry(page="source", payload=payload)
        if page == "list":
            return BrowserHistoryEntry(
                page="list",
                list_kind=self._active_list_kind,
                liked_tracks_limit=self._liked_tracks_limit,
            )
        return None

    def _restore_history_entry(self, entry: BrowserHistoryEntry) -> None:
        if entry.page == "search":
            self._active_page = ("search", None)
            self._active_list_kind = None
            self._active_search_tab = entry.active_tab or "tracks"
            if entry.search_query:
                self._dispatch_search(entry.search_query or "")
                return
            self._emit_content(self._empty_search_content(self._active_search_tab))
            return
        if entry.page == "artist" and isinstance(entry.payload, Artist):
            self._active_page = ("artist", entry.payload)
            self._active_list_kind = None
            self._active_artist_tab = entry.active_tab or "top_tracks"
            self._execute(
                lambda: self._artist_content(entry.payload, tab=self._active_artist_tab)
            )
            return
        if entry.page == "source" and isinstance(entry.payload, Playlist):
            self._active_list_kind = None
            self._active_page = ("source", entry.payload)
            self._execute(
                lambda: self._source_content(
                    title=entry.payload.title,
                    source_type="playlist",
                    source_id=entry.payload.id,
                    tracks=self._library_service.load_playlist_tracks(
                        entry.payload.id,
                        owner_id=entry.payload.owner_id,
                    ),
                )
            )
            return
        if entry.page == "source" and isinstance(entry.payload, Album):
            self._active_list_kind = None
            self._active_page = ("source", entry.payload)
            self._execute(
                lambda: self._source_content(
                    title=entry.payload.title,
                    source_type="album",
                    source_id=entry.payload.id,
                    tracks=self._library_service.load_album_tracks(entry.payload.id),
                )
            )
            return
        if entry.page == "source" and isinstance(entry.payload, Station):
            self._active_list_kind = None
            self._active_page = ("source", entry.payload)
            self._execute(
                lambda: self._source_content(
                    title=self._station_title(entry.payload),
                    source_type="station",
                    source_id=entry.payload.id,
                    tracks=self._library_service.load_station_tracks(entry.payload.id),
                )
            )
            return
        if entry.page == "list":
            self._active_page = ("list", None)
            self._active_list_kind = entry.list_kind
            if entry.list_kind == "liked_tracks":
                self._liked_tracks_limit = entry.liked_tracks_limit or 100
                self._execute(lambda: self._liked_tracks_content(limit=self._liked_tracks_limit))
                return
            if entry.list_kind == "liked_albums":
                self._execute(
                    lambda: BrowserContent(
                        title=self._t("library.list.my_albums"),
                        items=self._album_items(self._library_service.load_liked_albums()),
                        recent_searches=self.recent_searches(),
                    )
                )
                return
            if entry.list_kind == "liked_artists":
                self._execute(
                    lambda: BrowserContent(
                        title=self._t("library.list.my_artists"),
                        items=self._artist_items(self._library_service.load_liked_artists()),
                        recent_searches=self.recent_searches(),
                    )
                )
                return
            if entry.list_kind == "playlists":
                self._execute(
                    lambda: BrowserContent(
                        title=self._t("library.list.playlists"),
                        items=(
                            *self._playlist_items(
                                self._library_service.load_generated_playlists(),
                                kind="generated_playlist",
                            ),
                            *self._playlist_items(
                                self._unique_playlists(
                                    self._library_service.load_liked_playlists(),
                                    self._library_service.load_user_playlists(),
                                ),
                                kind="playlist",
                            ),
                        ),
                        recent_searches=self.recent_searches(),
                    )
                )

    def _search_content(self, query: str, *, tab: str, refresh: bool) -> BrowserContent:
        normalized_query = query.strip()
        if refresh or self._last_search_results is None:
            self._last_search_query = normalized_query
            self._last_search_results = self._search_service.search_catalog(normalized_query)

        results = self._last_search_results or CatalogSearchResults()
        is_track_tab = tab == "tracks"
        track_source_id = normalized_query or "search"
        title = (
            self._t("library.search_title", query=normalized_query)
            if normalized_query
            else self._t("library.search")
        )
        return BrowserContent(
            title=f"{title} | {self._search_tab_title(tab)}",
            items=self._search_tab_items(results, tab=tab, query=normalized_query),
            recent_searches=self.recent_searches(),
            tabs=self._search_tabs(),
            active_tab=tab,
            search_query=normalized_query,
            source_type="search" if is_track_tab and results.tracks else None,
            source_id=track_source_id if is_track_tab and results.tracks else None,
            source_tracks=results.tracks if is_track_tab else (),
            bulk_mode="loaded_only",
        )

    def _empty_search_content(self, tab: str) -> BrowserContent:
        return BrowserContent(
            title=f"{self._t('library.search')} | {self._search_tab_title(tab)}",
            items=(),
            recent_searches=self.recent_searches(),
            tabs=self._search_tabs(),
            active_tab=tab,
            search_query=self._last_search_query,
            bulk_mode="loaded_only",
        )

    def _loading_search_content(self, query: str, tab: str) -> BrowserContent:
        normalized_query = query.strip()
        title = (
            self._t("library.search_title", query=normalized_query)
            if normalized_query
            else self._t("library.search")
        )
        return BrowserContent(
            title=f"{title} | {self._search_tab_title(tab)}",
            items=(),
            recent_searches=self.recent_searches(),
            tabs=self._search_tabs(),
            active_tab=tab,
            search_query=normalized_query,
            bulk_mode="loaded_only",
            is_loading=True,
        )

    def _dispatch_search(self, query: str) -> None:
        normalized_query = query.strip()
        self._search_request_id += 1
        request_id = self._search_request_id
        self._emit_content(
            self._loading_search_content(normalized_query, self._active_search_tab)
        )
        self._search_requested.emit(request_id, normalized_query)

    def _handle_search_ready(
        self,
        request_id: int,
        query: str,
        results: CatalogSearchResults,
    ) -> None:
        if request_id != self._search_request_id:
            return
        self._last_search_query = query
        self._last_search_results = results
        if self._active_page != ("search", None):
            return
        self._emit_content(
            self._search_content(
                query,
                tab=self._active_search_tab,
                refresh=False,
            )
        )

    def _handle_search_failed(self, request_id: int, message: str) -> None:
        if request_id != self._search_request_id:
            return
        self.content_failed.emit(message)

    def _artist_content(self, artist: Artist, *, tab: str) -> BrowserContent:
        if tab == "playlists":
            artist_radio = self._artist_radio_items((artist,))
            return BrowserContent(
                title=self._t("library.artist_playlists_title", name=artist.name),
                items=artist_radio
                + self._playlist_items(
                    self._library_service.load_artist_playlists(artist.id),
                    kind="playlist",
                ),
                recent_searches=self.recent_searches(),
                tabs=self._artist_tabs(),
                active_tab=tab,
                bulk_mode="loaded_only",
            )
        if tab == "albums":
            return BrowserContent(
                title=self._t("library.artist_albums_title", name=artist.name),
                items=self._album_items(self._artist_albums(artist.id, release_type=None)),
                recent_searches=self.recent_searches(),
                tabs=self._artist_tabs(),
                active_tab=tab,
                bulk_mode="loaded_only",
            )
        if tab == "singles":
            return BrowserContent(
                title=self._t("library.artist_singles_title", name=artist.name),
                items=self._album_items(self._artist_albums(artist.id, release_type="single")),
                recent_searches=self.recent_searches(),
                tabs=self._artist_tabs(),
                active_tab=tab,
                bulk_mode="loaded_only",
            )
        if tab == "compilations":
            return BrowserContent(
                title=self._t("library.artist_compilations_title", name=artist.name),
                items=self._album_items(
                    self._library_service.load_artist_compilation_albums(artist.id)
                ),
                recent_searches=self.recent_searches(),
                tabs=self._artist_tabs(),
                active_tab=tab,
                bulk_mode="loaded_only",
            )
        tracks = self._library_service.load_artist_tracks(artist.id)
        return BrowserContent(
            title=self._t("library.artist_top_tracks_title", name=artist.name),
            items=self._track_items(
                tracks,
                source_type="artist",
                source_id=artist.id,
                source_tracks=tracks,
            ),
            recent_searches=self.recent_searches(),
            tabs=self._artist_tabs(),
            active_tab="top_tracks",
            source_type="artist",
            source_id=artist.id,
            source_tracks=tracks,
            bulk_mode="load_all",
        )

    def _source_content(
        self,
        *,
        title: str,
        source_type: str,
        source_id: str,
        tracks: tuple[Track, ...],
    ) -> BrowserContent:
        bulk_mode = "loaded_only" if source_type == "station" else "load_all"
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
            source_tracks=tracks,
            bulk_mode=bulk_mode,
        )

    def _liked_tracks_content(self, *, limit: int) -> BrowserContent:
        tracks = self._library_service.load_liked_tracks(limit=limit)
        return BrowserContent(
            title=self._t("library.list.my_tracks"),
            items=self._track_items(
                tracks,
                source_type="collection",
                source_id="liked_tracks",
                source_tracks=tracks,
            ),
            recent_searches=self.recent_searches(),
            source_type="collection",
            source_id="liked_tracks",
            source_tracks=tracks,
            bulk_mode="load_all",
            list_key="liked_tracks",
            has_more=len(tracks) >= limit,
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
                title=display_track_title(track),
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
        return self._track_items(
            results.tracks,
            source_type="search",
            source_id=query or "search",
            source_tracks=results.tracks,
        )

    def _search_tab_title(self, tab: str) -> str:
        return {
            "albums": self._t("library.tab.albums"),
            "singles": self._t("library.tab.singles"),
            "compilations": self._t("library.tab.compilations"),
            "playlists": self._t("library.tab.playlists"),
            "artists": self._t("library.tab.artists"),
            "artist_radio": self._t("library.tab.artist_radio"),
            "tracks": self._t("library.tab.tracks"),
        }.get(tab, self._t("library.tab.tracks"))

    def _search_tabs(self) -> tuple[BrowserTab, ...]:
        return (
            BrowserTab("tracks", self._t("library.tab.tracks")),
            BrowserTab("playlists", self._t("library.tab.playlists")),
            BrowserTab("albums", self._t("library.tab.albums")),
            BrowserTab("singles", self._t("library.tab.singles")),
            BrowserTab("compilations", self._t("library.tab.compilations")),
            BrowserTab("artists", self._t("library.tab.artists")),
            BrowserTab("artist_radio", self._t("library.tab.artist_radio")),
        )

    def _artist_tabs(self) -> tuple[BrowserTab, ...]:
        return (
            BrowserTab("top_tracks", self._t("library.tab.top_tracks")),
            BrowserTab("playlists", self._t("library.tab.playlists")),
            BrowserTab("albums", self._t("library.tab.albums")),
            BrowserTab("singles", self._t("library.tab.singles")),
            BrowserTab("compilations", self._t("library.tab.compilations")),
        )

    def _artist_albums(self, artist_id: str, *, release_type: str | None) -> tuple[Album, ...]:
        albums = self._library_service.load_artist_direct_albums(artist_id)
        if release_type is None:
            return tuple(album for album in albums if album.release_type != "single")
        return tuple(album for album in albums if album.release_type == release_type)

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
                subtitle=self._t("library.artist"),
                payload=artist,
            )
            for artist in artists
        )

    def _artist_radio_items(self, artists: tuple[Artist, ...]) -> tuple[BrowserItem, ...]:
        return tuple(
            BrowserItem(
                kind="artist_radio",
                title=self._t("library.artist_radio_item", name=artist.name),
                subtitle=self._t("library.artist_radio_subtitle"),
                payload=Station(
                    id=f"artist:{artist.id}",
                    title=self._t("library.artist_radio_item", name=artist.name),
                ),
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

    def _unique_playlists(self, *playlist_groups: tuple[Playlist, ...]) -> tuple[Playlist, ...]:
        seen: set[tuple[str | None, str]] = set()
        playlists: list[Playlist] = []
        for group in playlist_groups:
            for playlist in group:
                key = (playlist.owner_id, playlist.id)
                if key in seen:
                    continue
                seen.add(key)
                playlists.append(playlist)
        return tuple(playlists)

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

    def _station_title(self, station: Station) -> str:
        if station.id == "user:onyourwave":
            return self._t("nav.my_wave")
        return station.title

    def _track_subtitle(self, track: Track, *, source_type: str | None) -> str:
        parts: list[str] = []
        artists = ", ".join(track.artists)
        if artists:
            parts.append(artists)
        if track.album_title:
            parts.append(track.album_title)
        elif source_type == "station":
            parts.append(self._t("library.radio"))
        return " | ".join(parts) or self._t("library.track")

    def _album_subtitle(self, album: Album) -> str | None:
        parts = [", ".join(album.artists)]
        if album.year is not None:
            parts.append(str(album.year))
        if album.track_count is not None:
            parts.append(self._t("library.track_count", count=album.track_count))
        return " | ".join(part for part in parts if part) or None
