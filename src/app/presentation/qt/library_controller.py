from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from app.application.error_presenter import user_facing_error_message
from app.application.library_service import LibraryService
from app.application.search_service import SearchService
from app.domain import Album, Artist, CatalogSearchResults, Logger, Playlist, Station, Track
from app.domain.errors import DomainError
from app.presentation.qt.library_task_runner import LibraryTaskRunner
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
    append_items: bool = False


@dataclass(frozen=True, slots=True)
class BrowserHistoryEntry:
    page: str
    payload: object | None = None
    active_tab: str | None = None
    search_query: str | None = None
    liked_tracks_limit: int | None = None
    list_kind: str | None = None


class LibraryController(QObject):
    _LIKED_TRACKS_PAGE_SIZE = 500

    content_changed = Signal(object)
    content_failed = Signal(str)
    track_liked = Signal(object)
    track_unliked = Signal(object)
    track_disliked = Signal(object)
    track_undisliked = Signal(object)
    album_liked = Signal(object)
    album_unliked = Signal(object)
    artist_liked = Signal(object)
    artist_unliked = Signal(object)
    artist_disliked = Signal(object)
    artist_undisliked = Signal(object)
    playlist_liked = Signal(object)
    playlist_unliked = Signal(object)
    bulk_tracks_ready = Signal(str, object)

    def __init__(
        self,
        *,
        search_service: SearchService,
        library_service: LibraryService,
        logger: Logger,
        translate: Callable[..., str],
        task_runner: LibraryTaskRunner | None = None,
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
        self._liked_tracks_limit = self._LIKED_TRACKS_PAGE_SIZE
        self._liked_tracks_page_size = self._LIKED_TRACKS_PAGE_SIZE
        self._loaded_liked_tracks: tuple[Track, ...] = ()
        self._history: list[BrowserHistoryEntry] = []
        self._search_request_id = 0
        self._task_runner = task_runner or LibraryTaskRunner(logger=logger, parent=self)
        self._owns_task_runner = task_runner is None
        self._task_handlers: dict[
            int,
            tuple[Callable[[object], None], Callable[[object], None]],
        ] = {}
        self._content_task_id: int | None = None
        self._task_runner.completed.connect(self._handle_task_completed)
        self._task_runner.failed.connect(self._handle_task_failed)

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
        for task_id in tuple(self._task_handlers):
            self._task_runner.cancel(task_id)
        self._task_handlers.clear()
        if self._owns_task_runner:
            self._task_runner.shutdown()

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

    def request_full_current_source_tracks(self, action: str) -> None:
        task_id = self._task_runner.submit(self.load_full_current_source_tracks)
        if task_id is None:
            return
        self._task_handlers[task_id] = (
            lambda result: self.bulk_tracks_ready.emit(action, result),
            self._emit_background_error,
        )

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
        self._liked_tracks_limit = self._liked_tracks_page_size
        self._loaded_liked_tracks = ()
        cached_loader = getattr(self._library_service, "load_cached_liked_tracks", lambda **_: ())
        self._execute_cached_then_refresh(
            lambda: self._liked_tracks_content_from_tracks(
                tuple(cached_loader(limit=self._liked_tracks_limit))
            ),
            self._load_initial_liked_tracks_content,
        )

    def load_more_current_list(self) -> None:
        page, _payload = self._active_page
        if page != "list" or self._active_list_kind != "liked_tracks":
            return
        self._execute(self._load_more_liked_tracks_content)

    def load_liked_albums(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_albums"
        cached_loader = getattr(self._library_service, "load_cached_liked_albums", lambda: ())
        self._execute_cached_then_refresh(
            lambda: self._liked_albums_content(tuple(cached_loader())),
            lambda: self._liked_albums_content(
                self._library_service.load_liked_albums(force_refresh=True)
            ),
        )

    def load_liked_artists(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "liked_artists"
        cached_loader = getattr(self._library_service, "load_cached_liked_artists", lambda: ())
        self._execute_cached_then_refresh(
            lambda: self._liked_artists_content(tuple(cached_loader())),
            lambda: self._liked_artists_content(
                self._library_service.load_liked_artists(force_refresh=True)
            ),
        )

    def load_playlists(self) -> None:
        self._push_history()
        self._active_page = ("list", None)
        self._active_list_kind = "playlists"
        cached_generated = getattr(
            self._library_service, "load_cached_generated_playlists", lambda: ()
        )
        cached_liked = getattr(
            self._library_service, "load_cached_liked_playlists", lambda: ()
        )
        cached_user = getattr(self._library_service, "load_cached_user_playlists", lambda: ())
        self._execute_cached_then_refresh(
            lambda: self._playlists_content(
                tuple(cached_generated()), tuple(cached_liked()), tuple(cached_user())
            ),
            lambda: self._playlists_content(
                self._library_service.load_generated_playlists(force_refresh=True),
                self._library_service.load_liked_playlists(force_refresh=True),
                self._library_service.load_user_playlists(force_refresh=True),
            ),
        )

    def active_list_kind(self) -> str | None:
        page, _payload = self._active_page
        if page != "list":
            return None
        return self._active_list_kind

    def refresh_active_list(self) -> None:
        page, _payload = self._active_page
        if page != "list":
            return
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
        if self._content_task_id is not None:
            self._task_runner.cancel(self._content_task_id)
            self._task_handlers.pop(self._content_task_id, None)
        task_id = self._task_runner.submit(lambda: self._library_service.load_album(album_id))
        if task_id is None:
            return
        self._content_task_id = task_id
        self._task_handlers[task_id] = (
            lambda result: self.open_album(result) if isinstance(result, Album) else None,
            self._emit_background_error,
        )

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
        self._execute_mutation(lambda: self._library_service.like_track(track), self.track_liked)

    def unlike_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self._library_service.unlike_track(track), self.track_unliked
        )

    def dislike_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self._library_service.dislike_track(track), self.track_disliked
        )

    def undislike_track(self, track: Track) -> None:
        self._execute_mutation(
            lambda: self._library_service.undislike_track(track), self.track_undisliked
        )

    def like_album(self, album: Album) -> None:
        self._execute_mutation(lambda: self._library_service.like_album(album), self.album_liked)

    def unlike_album(self, album: Album) -> None:
        self._execute_mutation(
            lambda: self._library_service.unlike_album(album), self.album_unliked
        )

    def like_artist(self, artist: Artist) -> None:
        self._execute_mutation(lambda: self._library_service.like_artist(artist), self.artist_liked)

    def unlike_artist(self, artist: Artist) -> None:
        self._execute_mutation(
            lambda: self._library_service.unlike_artist(artist), self.artist_unliked
        )

    def dislike_artist(self, artist: Artist) -> None:
        self._execute_mutation(
            lambda: self._library_service.dislike_artist(artist), self.artist_disliked
        )

    def undislike_artist(self, artist: Artist) -> None:
        self._execute_mutation(
            lambda: self._library_service.undislike_artist(artist), self.artist_undisliked
        )

    def like_playlist(self, playlist: Playlist) -> None:
        self._execute_mutation(
            lambda: self._library_service.like_playlist(playlist), self.playlist_liked
        )

    def unlike_playlist(self, playlist: Playlist) -> None:
        self._execute_mutation(
            lambda: self._library_service.unlike_playlist(playlist), self.playlist_unliked
        )

    def _execute(self, operation) -> None:
        if self._content_task_id is not None:
            self._task_runner.cancel(self._content_task_id)
            self._task_handlers.pop(self._content_task_id, None)
        task_id = self._task_runner.submit(operation)
        if task_id is None:
            return
        self._content_task_id = task_id
        self._task_handlers[task_id] = (
            lambda result: (
                self._emit_content(result) if isinstance(result, BrowserContent) else None
            ),
            self._emit_background_error,
        )

    def _execute_cached_then_refresh(self, cached_operation, refresh_operation) -> None:
        if self._content_task_id is not None:
            self._task_runner.cancel(self._content_task_id)
            self._task_handlers.pop(self._content_task_id, None)
        state: dict[str, BrowserContent | bool | None] = {
            "cached": None,
            "shown": False,
        }

        def start_refresh() -> None:
            task_id = self._task_runner.submit(refresh_operation)
            if task_id is None:
                return
            self._content_task_id = task_id

            def apply_refresh(result: object) -> None:
                if not isinstance(result, BrowserContent):
                    return
                if result != state["cached"]:
                    self._emit_content(result)

            def handle_refresh_error(error: object) -> None:
                if state["shown"]:
                    self._logger.warning("Background library refresh failed: %s", error)
                    return
                self._emit_background_error(error)

            self._task_handlers[task_id] = (apply_refresh, handle_refresh_error)

        task_id = self._task_runner.submit(cached_operation)
        if task_id is None:
            return
        self._content_task_id = task_id

        def apply_cached(result: object) -> None:
            if isinstance(result, BrowserContent) and result.items:
                state["cached"] = result
                state["shown"] = True
                self._emit_content(result)
            start_refresh()

        def handle_cache_error(error: object) -> None:
            self._logger.warning("Library cache read failed: %s", error)
            start_refresh()

        self._task_handlers[task_id] = (apply_cached, handle_cache_error)

    def _execute_mutation(self, operation, result_signal) -> None:
        task_id = self._task_runner.submit(operation)
        if task_id is None:
            return
        self._task_handlers[task_id] = (result_signal.emit, self._emit_background_error)

    def _emit_background_error(self, error: object) -> None:
        if isinstance(error, DomainError):
            message = user_facing_error_message(error)
        else:
            message = str(error)
        self.content_failed.emit(message)

    def _handle_task_completed(self, task_id: int, result: object) -> None:
        handlers = self._task_handlers.pop(task_id, None)
        if handlers is None:
            return
        if task_id == self._content_task_id:
            self._content_task_id = None
        handlers[0](result)

    def _handle_task_failed(self, task_id: int, error: object) -> None:
        handlers = self._task_handlers.pop(task_id, None)
        if handlers is None:
            return
        if task_id == self._content_task_id:
            self._content_task_id = None
        handlers[1](error)

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
                self._liked_tracks_limit = (
                    entry.liked_tracks_limit or self._LIKED_TRACKS_PAGE_SIZE
                )
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
        del tab
        return BrowserContent(
            title=self._t("library.search"),
            items=(),
            recent_searches=self.recent_searches(),
            tabs=(),
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
        if self._content_task_id is not None:
            self._task_runner.cancel(self._content_task_id)
            self._task_handlers.pop(self._content_task_id, None)
        task_id = self._task_runner.submit(
            lambda: self._search_service.search_catalog(normalized_query)
        )
        if task_id is None:
            return
        self._content_task_id = task_id
        self._task_handlers[task_id] = (
            lambda results: self._handle_search_ready(request_id, normalized_query, results),
            lambda error: self._handle_search_failed(request_id, error),
        )

    def _handle_search_ready(
        self,
        request_id: int,
        query: str,
        results: object,
    ) -> None:
        if request_id != self._search_request_id:
            return
        if not isinstance(results, CatalogSearchResults):
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

    def _handle_search_failed(self, request_id: int, error: object) -> None:
        if request_id != self._search_request_id:
            return
        self._emit_background_error(error)

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
        return self._liked_tracks_browser_content(
            tracks=tracks,
            source_tracks=tracks,
            has_more=len(tracks) >= limit,
        )

    def _liked_tracks_content_from_tracks(self, tracks: tuple[Track, ...]) -> BrowserContent:
        self._loaded_liked_tracks = tracks
        return self._liked_tracks_browser_content(
            tracks=tracks,
            source_tracks=tracks,
            has_more=bool(tracks) and len(tracks) >= self._liked_tracks_limit,
        )

    def _liked_albums_content(self, albums: tuple[Album, ...]) -> BrowserContent:
        return BrowserContent(
            title=self._t("library.list.my_albums"),
            items=self._album_items(albums),
            recent_searches=self.recent_searches(),
        )

    def _liked_artists_content(self, artists: tuple[Artist, ...]) -> BrowserContent:
        return BrowserContent(
            title=self._t("library.list.my_artists"),
            items=self._artist_items(artists),
            recent_searches=self.recent_searches(),
        )

    def _playlists_content(
        self,
        generated: tuple[Playlist, ...],
        liked: tuple[Playlist, ...],
        user: tuple[Playlist, ...],
    ) -> BrowserContent:
        return BrowserContent(
            title=self._t("library.list.playlists"),
            items=(
                *self._playlist_items(generated, kind="generated_playlist"),
                *self._playlist_items(
                    self._unique_playlists(liked, user),
                    kind="playlist",
                ),
            ),
            recent_searches=self.recent_searches(),
        )

    def _load_initial_liked_tracks_content(self) -> BrowserContent:
        tracks = self._library_service.load_liked_tracks(limit=self._liked_tracks_limit)
        self._loaded_liked_tracks = tracks
        return self._liked_tracks_browser_content(
            tracks=tracks,
            source_tracks=tracks,
            has_more=len(tracks) >= self._liked_tracks_limit,
        )

    def _load_more_liked_tracks_content(self) -> BrowserContent:
        page_tracks = self._library_service.load_liked_tracks_page(
            offset=len(self._loaded_liked_tracks),
            limit=self._liked_tracks_page_size,
        )
        if not page_tracks:
            return BrowserContent(
                title=self._t("library.list.my_tracks"),
                items=(),
                recent_searches=self.recent_searches(),
                source_type="collection",
                source_id="liked_tracks",
                source_tracks=self._loaded_liked_tracks,
                bulk_mode="load_all",
                list_key="liked_tracks",
                has_more=False,
                append_items=True,
            )
        self._loaded_liked_tracks = (*self._loaded_liked_tracks, *page_tracks)
        self._liked_tracks_limit = len(self._loaded_liked_tracks)
        return self._liked_tracks_browser_content(
            tracks=page_tracks,
            source_tracks=self._loaded_liked_tracks,
            has_more=len(page_tracks) >= self._liked_tracks_page_size,
            append_items=True,
        )

    def _liked_tracks_browser_content(
        self,
        *,
        tracks: tuple[Track, ...],
        source_tracks: tuple[Track, ...],
        has_more: bool,
        append_items: bool = False,
    ) -> BrowserContent:
        start_index = len(source_tracks) - len(tracks)
        return BrowserContent(
            title=self._t("library.list.my_tracks"),
            items=self._track_items(
                tracks,
                source_type="collection",
                source_id="liked_tracks",
                source_tracks=source_tracks,
                source_index_offset=start_index,
            ),
            recent_searches=self.recent_searches(),
            source_type="collection",
            source_id="liked_tracks",
            source_tracks=source_tracks,
            bulk_mode="load_all",
            list_key="liked_tracks",
            has_more=has_more,
            append_items=append_items,
        )

    def _track_items(
        self,
        tracks: tuple[Track, ...],
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        source_tracks: tuple[Track, ...] = (),
        source_index_offset: int = 0,
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
                source_index=(source_index_offset + index) if source_tracks else None,
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
        if album.year is not None:
            parts = [str(album.year)]
        else:
            parts = []
        artists = ", ".join(album.artists)
        if artists:
            parts.append(artists)
        if album.track_count is not None:
            parts.append(self._t("library.track_count", count=album.track_count))
        return " | ".join(part for part in parts if part) or None
