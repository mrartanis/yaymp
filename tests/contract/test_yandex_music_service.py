from __future__ import annotations

import pytest

from app.domain import AuthError, AuthSession, NetworkError, Track, TrackUnavailableError
from app.domain.playlist import Playlist
from app.infrastructure.yandex.yandex_music_service import YandexMusicService


class ArtistStub:
    def __init__(self, name: str) -> None:
        self.name = name


class AlbumStub:
    def __init__(self, title: str) -> None:
        self.title = title


class TrackStub:
    def __init__(
        self,
        *,
        track_id: str,
        title: str = "Track",
        available: bool = True,
        duration_ms: int = 180_000,
    ) -> None:
        self.id = track_id
        self.title = title
        self.available = available
        self.duration_ms = duration_ms
        self.artists = [ArtistStub("Artist")]
        self.albums = [AlbumStub("Album")]
        self.cover_uri = "covers/track.jpg"


class PlaylistEntryStub:
    def __init__(self, track: TrackStub) -> None:
        self.track = track


class PlaylistStub:
    def __init__(self, playlist_id: str, tracks: list[TrackStub]) -> None:
        self.kind = playlist_id
        self.title = f"Playlist {playlist_id}"
        self.tracks = [PlaylistEntryStub(track) for track in tracks]


class SearchTracksStub:
    def __init__(self, results: list[TrackStub]) -> None:
        self.results = results


class SearchResultStub:
    def __init__(self, results: list[TrackStub]) -> None:
        self.tracks = SearchTracksStub(results)


class DownloadInfoStub:
    def __init__(self, direct_link: str | None = None) -> None:
        self.direct_link = direct_link


class LikesStub:
    def __init__(self, tracks: list[TrackStub]) -> None:
        self._tracks = tracks

    def fetch_tracks(self):
        return self._tracks


class FakeYandexClient:
    def __init__(self) -> None:
        self.track = TrackStub(track_id="track-1", title="Remote")
        self.playlist = PlaylistStub("playlist-1", [self.track])
        self.search_result = SearchResultStub([self.track])
        self.likes = LikesStub([self.track])
        self.download_infos = [DownloadInfoStub("https://stream.example/track-1")]

    def tracks(self, track_ids):
        if track_ids == ["missing"]:
            return []
        return [self.track]

    def search(self, query: str, *, type_: str):
        del query, type_
        return self.search_result

    def users_likes_tracks(self):
        return self.likes

    def users_playlists(self, playlist_id: str):
        del playlist_id
        return self.playlist

    def tracks_download_info(self, track_id: str, get_direct_links: bool = True):
        del track_id, get_direct_links
        return self.download_infos


def test_yandex_music_service_requires_session_before_use() -> None:
    service = YandexMusicService()

    with pytest.raises(AuthError):
        service.get_track("track-1")


def test_yandex_music_service_maps_track_and_playlist_data() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    track = service.get_track("track-1")
    playlist = service.get_playlist("playlist-1")
    playlist_tracks = service.get_playlist_tracks("playlist-1")
    search_tracks = service.search_tracks("remote")
    liked_tracks = service.get_liked_tracks()

    assert track.id == "track-1"
    assert track.album_title == "Album"
    assert playlist == Playlist(id="playlist-1", title="Playlist playlist-1", track_count=1)
    assert [item.id for item in playlist_tracks] == ["track-1"]
    assert [item.id for item in search_tracks] == ["track-1"]
    assert [item.id for item in liked_tracks] == ["track-1"]


def test_yandex_music_service_resolves_playable_stream() -> None:
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=FakeYandexClient(),
    )

    stream_ref = service.resolve_stream_ref(
        Track(id="track-1", title="Remote", artists=("Artist",), available=True)
    )

    assert stream_ref == "https://stream.example/track-1"


def test_yandex_music_service_rejects_unavailable_tracks() -> None:
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=FakeYandexClient(),
    )

    with pytest.raises(TrackUnavailableError):
        service.resolve_stream_ref(
            Track(id="track-2", title="Blocked", artists=("Artist",), available=False)
        )


def test_yandex_music_service_maps_network_failures() -> None:
    class BrokenClient(FakeYandexClient):
        def tracks(self, track_ids):
            del track_ids
            raise RuntimeError("boom")

    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=BrokenClient(),
    )

    with pytest.raises(NetworkError):
        service.get_track("track-1")
