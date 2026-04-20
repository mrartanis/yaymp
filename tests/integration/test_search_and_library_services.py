from __future__ import annotations

from app.application.library_service import LibraryService
from app.application.search_service import SearchService
from app.domain import Playlist, Station, Track


class TestLogger:
    def debug(self, message: str, *args: object) -> None:
        del message, args

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        del message, args

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


class InMemoryLibraryCacheRepo:
    def __init__(self) -> None:
        self.searches: tuple[str, ...] = ()

    def load_recent_searches(self):
        return self.searches

    def save_recent_searches(self, searches):
        self.searches = tuple(searches)


class FakeMusicService:
    def get_auth_session(self):
        return None

    def set_auth_session(self, session):
        self.session = session

    def build_auth_session(self, token: str, *, expires_at=None):
        from app.domain import AuthSession

        return AuthSession(user_id="user-1", token=token, expires_at=expires_at)

    def get_track(self, track_id: str):
        return Track(id=track_id, title=f"Track {track_id}", artists=("Artist",), stream_ref=f"s://{track_id}")

    def search_tracks(self, query: str, *, limit: int = 25):
        return (Track(id=f"{query}-{limit}", title=query, artists=("Artist",)),)

    def get_liked_tracks(self, *, limit: int = 100):
        return (Track(id=f"liked-{limit}", title="Liked", artists=("Artist",)),)

    def get_user_playlists(self):
        return (Playlist(id="playlist-1", title="Playlist 1"),)

    def get_generated_playlists(self):
        return (Playlist(id="generated-1", title="Playlist of the Day"),)

    def get_stations(self):
        return (Station(id="user:onyourwave", title="My Wave"),)

    def get_station_tracks(self, station_id: str, *, limit: int = 25):
        return (Track(id=f"{station_id}-{limit}", title="Wave", artists=("Artist",)),)

    def get_playlist(self, playlist_id: str):
        return Playlist(id=playlist_id, title=f"Playlist {playlist_id}")

    def get_playlist_tracks(self, playlist_id: str):
        return (Track(id=f"{playlist_id}-track", title="Playlist Track", artists=("Artist",)),)

    def resolve_stream_ref(self, track: Track) -> str:
        return track.stream_ref or f"stream:{track.id}"


def test_search_service_updates_recent_searches() -> None:
    cache_repo = InMemoryLibraryCacheRepo()
    service = SearchService(
        music_service=FakeMusicService(),
        library_cache_repo=cache_repo,
        logger=TestLogger(),
    )

    tracks = service.search_tracks("ambient")
    service.search_tracks("jazz")
    service.search_tracks("ambient")

    assert [track.id for track in tracks] == ["ambient-25"]
    assert service.load_recent_searches() == ("ambient", "jazz")


def test_library_service_exposes_playlists_and_stations() -> None:
    service = LibraryService(music_service=FakeMusicService(), logger=TestLogger())

    assert [item.id for item in service.load_liked_tracks()] == ["liked-100"]
    assert [item.id for item in service.load_user_playlists()] == ["playlist-1"]
    assert [item.id for item in service.load_generated_playlists()] == ["generated-1"]
    assert [item.id for item in service.load_stations()] == ["user:onyourwave"]
    assert [item.id for item in service.load_station_tracks("user:onyourwave")] == [
        "user:onyourwave-25"
    ]
