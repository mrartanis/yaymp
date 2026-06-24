from __future__ import annotations

from app.domain import Album, Artist, CatalogSearchResults, Playlist, Track
from app.presentation.qt.library_controller import LibraryController


class StubLogger:
    def debug(self, message: str, *args: object) -> None:
        return None

    def info(self, message: str, *args: object) -> None:
        return None

    def warning(self, message: str, *args: object) -> None:
        return None

    def error(self, message: str, *args: object) -> None:
        return None

    def exception(self, message: str, *args: object) -> None:
        return None


class StubSearchService:
    def load_recent_searches(self) -> tuple[str, ...]:
        return ()

    def search_catalog(self, query: str) -> CatalogSearchResults:
        return CatalogSearchResults()


class StubLibraryService:
    def __init__(self) -> None:
        self.all_liked_tracks = (
            Track(id="liked-1", title="Liked 1", artists=()),
            Track(id="liked-2", title="Liked 2", artists=()),
        )
        self.liked_artists = (Artist(id="artist-1", name="Artist 1"),)
        self.full_playlist_tracks = (Track(id="playlist-1", title="Playlist 1", artists=()),)
        self.full_album_tracks = (Track(id="album-1", title="Album 1", artists=()),)
        self.full_artist_tracks = (Track(id="artist-1", title="Artist 1", artists=()),)

    def load_liked_tracks(self, *, limit: int = 100) -> tuple[Track, ...]:
        return self.all_liked_tracks[:limit]

    def load_all_liked_tracks(self) -> tuple[Track, ...]:
        return self.all_liked_tracks

    def load_liked_artists(self) -> tuple[Artist, ...]:
        return self.liked_artists

    def load_all_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> tuple[Track, ...]:
        return self.full_playlist_tracks

    def load_all_album_tracks(self, album_id: str) -> tuple[Track, ...]:
        return self.full_album_tracks

    def load_all_artist_tracks(self, artist_id: str) -> tuple[Track, ...]:
        return self.full_artist_tracks

    def load_artist_tracks(self, artist_id: str, *, limit: int = 50) -> tuple[Track, ...]:
        return self.full_artist_tracks[:limit]


def _translate(key: str, **params: object) -> str:
    return key.format(**params) if params else key


def test_liked_tracks_content_uses_load_all_bulk_mode() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    try:
        content = controller._liked_tracks_content(limit=1)
    finally:
        controller.shutdown()

    assert content.bulk_mode == "load_all"
    assert content.source_type == "collection"
    assert content.source_id == "liked_tracks"
    assert len(content.source_tracks) == 1


def test_search_tracks_content_uses_loaded_only_bulk_mode() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    controller._last_search_results = CatalogSearchResults(
        tracks=(Track(id="search-1", title="Search 1", artists=()),),
    )
    try:
        content = controller._search_content("query", tab="tracks", refresh=False)
    finally:
        controller.shutdown()

    assert content.bulk_mode == "loaded_only"
    assert content.source_type == "search"
    assert content.source_id == "query"
    assert len(content.source_tracks) == 1


def test_source_content_marks_station_as_loaded_only() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    tracks = (Track(id="station-1", title="Station 1", artists=()),)
    try:
        content = controller._source_content(
            title="Station",
            source_type="station",
            source_id="station-id",
            tracks=tracks,
        )
    finally:
        controller.shutdown()

    assert content.bulk_mode == "loaded_only"
    assert content.source_tracks == tracks


def test_load_full_current_source_tracks_for_liked_tracks() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    controller._active_page = ("list", None)
    controller._active_list_kind = "liked_tracks"
    try:
        request = controller.load_full_current_source_tracks()
    finally:
        controller.shutdown()

    assert request == (
        (
            Track(id="liked-1", title="Liked 1", artists=()),
            Track(id="liked-2", title="Liked 2", artists=()),
        ),
        "collection",
        "liked_tracks",
    )


def test_load_full_current_source_tracks_for_playlist_and_artist() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    playlist = Playlist(id="playlist-id", title="Playlist", owner_id="owner")
    artist = Artist(id="artist-id", name="Artist")
    try:
        controller._active_page = ("source", playlist)
        playlist_request = controller.load_full_current_source_tracks()
        controller._active_page = ("artist", artist)
        controller._active_artist_tab = "top_tracks"
        artist_request = controller.load_full_current_source_tracks()
    finally:
        controller.shutdown()

    assert playlist_request == (
        (Track(id="playlist-1", title="Playlist 1", artists=()),),
        "playlist",
        "playlist-id",
    )
    assert artist_request == (
        (Track(id="artist-1", title="Artist 1", artists=()),),
        "artist",
        "artist-id",
    )


def test_album_subtitle_orders_year_before_artists_and_track_count() -> None:
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=StubLibraryService(),
        logger=StubLogger(),
        translate=_translate,
    )
    album = Album(
        id="album-id",
        title="Album",
        artists=("Artist One", "Artist Two"),
        year=1999,
        track_count=12,
    )
    try:
        subtitle = controller._album_subtitle(album)
    finally:
        controller.shutdown()

    assert subtitle == "1999 | Artist One, Artist Two | library.track_count"


def test_refresh_active_list_reloads_liked_artists_without_history_push() -> None:
    library_service = StubLibraryService()
    controller = LibraryController(
        search_service=StubSearchService(),
        library_service=library_service,
        logger=StubLogger(),
        translate=_translate,
    )
    rendered: list[object] = []
    controller.content_changed.connect(rendered.append)
    controller._active_page = ("list", None)
    controller._active_list_kind = "liked_artists"
    library_service.liked_artists = (
        Artist(id="artist-1", name="Artist 1"),
        Artist(id="artist-2", name="Artist 2"),
    )
    try:
        controller.refresh_active_list()
    finally:
        controller.shutdown()

    assert len(controller._history) == 0
    assert len(rendered) == 1
    content = rendered[0]
    assert content.title == "library.list.my_artists"
    assert [item.payload.id for item in content.items] == ["artist-1", "artist-2"]
