from __future__ import annotations

import pytest

from app.domain import (
    AudioQuality,
    AuthError,
    AuthSession,
    NetworkError,
    Station,
    Track,
    TrackUnavailableError,
)
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
        self.description = f"Description {playlist_id}"
        self.track_count = len(tracks)
        self.owner = type("Owner", (), {"name": "listener"})()


class GeneratedPlaylistStub:
    def __init__(self, playlist: PlaylistStub) -> None:
        self.data = playlist


class FeedStub:
    def __init__(self, generated_playlists: list[GeneratedPlaylistStub]) -> None:
        self.generated_playlists = generated_playlists


class SearchTracksStub:
    def __init__(self, results: list[TrackStub]) -> None:
        self.results = results


class SearchResultStub:
    def __init__(self, results: list[TrackStub]) -> None:
        self.tracks = SearchTracksStub(results)


class DownloadInfoStub:
    def __init__(
        self,
        direct_link: str | None = None,
        *,
        bitrate_in_kbps: int = 192,
        codec: str = "mp3",
    ) -> None:
        self.direct_link = direct_link
        self.bitrate_in_kbps = bitrate_in_kbps
        self.codec = codec


class LikesStub:
    def __init__(self, tracks: list[TrackStub]) -> None:
        self._tracks = tracks

    def fetch_tracks(self):
        return self._tracks


class FakeYandexClient:
    def __init__(self) -> None:
        self.track = TrackStub(track_id="track-1", title="Remote")
        self.playlist = PlaylistStub("playlist-1", [self.track])
        self.generated_playlist = PlaylistStub("generated-1", [self.track])
        self.search_result = SearchResultStub([self.track])
        self.likes = LikesStub([self.track])
        self.download_infos = [DownloadInfoStub("https://stream.example/track-1")]
        self.account = type("Account", (), {"uid": 7, "login": "listener"})()
        self.me = type("Me", (), {"account": self.account})()
        self.liked_track_ids: list[str] = []
        self.unliked_track_ids: list[str] = []

    def tracks(self, track_ids):
        if track_ids == ["missing"]:
            return []
        return [self.track]

    def search(self, query: str, *, type_: str):
        del query, type_
        return self.search_result

    def users_likes_tracks(self):
        return self.likes

    def users_likes_tracks_add(self, track_id: str):
        self.liked_track_ids.append(track_id)

    def users_likes_tracks_remove(self, track_id: str):
        self.unliked_track_ids.append(track_id)

    def users_playlists_list(self):
        return [self.playlist]

    def users_playlists(self, playlist_id: str):
        del playlist_id
        return self.playlist

    def feed(self):
        return FeedStub([GeneratedPlaylistStub(self.generated_playlist)])

    def rotor_stations_list(self):
        station_id = type("Id", (), {"type": "user", "tag": "onyourwave"})()
        station = type(
            "StationStub",
            (),
            {"id": station_id, "name": "My Wave", "full_image_url": "station.jpg"},
        )()
        return [
            type(
                "StationResultStub",
                (),
                {
                    "station": station,
                    "rup_title": "My Wave",
                    "rup_description": "Personal station",
                },
            )()
        ]

    def rotor_station_tracks(self, station_id: str):
        del station_id
        sequence_item = type("SequenceItem", (), {"track": self.track})()
        return type("StationTracksResultStub", (), {"sequence": [sequence_item]})()

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
    user_playlists = service.get_user_playlists()
    generated_playlists = service.get_generated_playlists()
    stations = service.get_stations()
    station_tracks = service.get_station_tracks("user:onyourwave")

    assert track.id == "track-1"
    assert track.album_title == "Album"
    assert playlist == Playlist(
        id="playlist-1",
        title="Playlist playlist-1",
        owner_name="listener",
        description="Description playlist-1",
        track_count=1,
        artwork_ref=None,
    )
    assert [item.id for item in playlist_tracks] == ["track-1"]
    assert [item.id for item in search_tracks] == ["track-1"]
    assert [item.id for item in liked_tracks] == ["track-1"]
    assert liked_tracks[0].is_liked is True
    assert [item.id for item in user_playlists] == ["playlist-1"]
    assert [item.id for item in generated_playlists] == ["generated-1"]
    assert stations == (
        Station(
            id="user:onyourwave",
            title="My Wave",
            description="Personal station",
            icon_ref="station.jpg",
        ),
    )
    assert [item.id for item in station_tracks] == ["track-1"]


def test_yandex_music_service_resolves_playable_stream() -> None:
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=FakeYandexClient(),
    )

    stream_ref = service.resolve_stream_ref(
        Track(id="track-1", title="Remote", artists=("Artist",), available=True)
    )

    assert stream_ref == "https://stream.example/track-1"


def test_yandex_music_service_selects_stream_by_audio_quality() -> None:
    client = FakeYandexClient()
    client.download_infos = [
        DownloadInfoStub("https://stream.example/lq", bitrate_in_kbps=64),
        DownloadInfoStub("https://stream.example/sd", bitrate_in_kbps=192),
        DownloadInfoStub("https://stream.example/hq", bitrate_in_kbps=320),
    ]
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )
    track = Track(id="track-1", title="Remote", artists=("Artist",), available=True)

    service.set_audio_quality(AudioQuality.LQ)
    assert service.resolve_stream_ref(track) == "https://stream.example/lq"

    service.set_audio_quality(AudioQuality.SD)
    assert service.resolve_stream_ref(track) == "https://stream.example/sd"

    service.set_audio_quality(AudioQuality.HQ)
    assert service.resolve_stream_ref(track) == "https://stream.example/hq"


def test_yandex_music_service_likes_and_unlikes_tracks() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    service.like_track("track-1")
    service.unlike_track("track-1")

    assert client.liked_track_ids == ["track-1"]
    assert client.unliked_track_ids == ["track-1"]


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
