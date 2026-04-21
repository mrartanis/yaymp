from __future__ import annotations

import pytest

from app.domain import (
    Album,
    Artist,
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
    def __init__(
        self,
        title: str,
        album_id: str = "album-1",
        *,
        album_type: str | None = None,
    ) -> None:
        self.id = album_id
        self.title = title
        self.type = album_type
        self.artists = [ArtistStub("Artist")]
        self.year = 2024
        self.track_count = 1
        self.cover_uri = "covers/album.jpg"


class ArtistResultStub:
    def __init__(self) -> None:
        self.id = "artist-1"
        self.name = "Artist"
        self.cover_uri = "covers/artist.jpg"


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
    def __init__(
        self,
        playlist_id: str,
        tracks: list[TrackStub],
        *,
        owner_uid: int = 7,
    ) -> None:
        self.uid = owner_uid
        self.kind = playlist_id
        self.title = f"Playlist {playlist_id}"
        self.tracks = [PlaylistEntryStub(track) for track in tracks]
        self.description = f"Description {playlist_id}"
        self.track_count = len(tracks)
        self.owner = type("Owner", (), {"uid": owner_uid, "name": "listener"})()


class GeneratedPlaylistStub:
    def __init__(self, playlist: PlaylistStub) -> None:
        self.data = playlist


class FeedStub:
    def __init__(self, generated_playlists: list[GeneratedPlaylistStub]) -> None:
        self.generated_playlists = generated_playlists


class SearchTracksStub:
    def __init__(self, results: list[TrackStub]) -> None:
        self.results = results


class SearchGroupStub:
    def __init__(self, results: list[object]) -> None:
        self.results = results


class SearchResultStub:
    def __init__(
        self,
        results: list[TrackStub],
        *,
        albums: list[AlbumStub] | None = None,
        artists: list[ArtistResultStub] | None = None,
        playlists: list[PlaylistStub] | None = None,
    ) -> None:
        self.tracks = SearchTracksStub(results)
        self.albums = SearchGroupStub(albums or [])
        self.artists = SearchGroupStub(artists or [])
        self.playlists = SearchGroupStub(playlists or [])


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
        self.album = AlbumStub("Album", album_id="album-1")
        self.single = AlbumStub("Single", album_id="single-1", album_type="single")
        self.compilation = AlbumStub(
            "Compilation",
            album_id="compilation-1",
            album_type="compilation",
        )
        self.playlist = PlaylistStub("playlist-1", [self.track])
        self.generated_playlist = PlaylistStub("generated-1", [self.track])
        self.search_result = SearchResultStub(
            [self.track],
            albums=[self.album, self.single, self.compilation],
            artists=[ArtistResultStub()],
            playlists=[self.playlist],
        )
        self.artist_albums = type("ArtistAlbumsStub", (), {"albums": [self.album, self.single]})()
        self.artist_compilations = type(
            "ArtistAlbumsStub",
            (),
            {"albums": [self.compilation]},
        )()
        self.artist_tracks = type("ArtistTracksStub", (), {"tracks": [self.track]})()
        self.likes = LikesStub([self.track])
        self.download_infos = [DownloadInfoStub("https://stream.example/track-1")]
        self.account = type("Account", (), {"uid": 7, "login": "listener"})()
        self.me = type("Me", (), {"account": self.account})()
        self.liked_track_ids: list[str] = []
        self.unliked_track_ids: list[str] = []
        self.playlist_requests: list[tuple[str, str | None]] = []

    def tracks(self, track_ids):
        if track_ids == ["missing"]:
            return []
        return [self.track]

    def search(self, query: str, *, type_: str | None = None):
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

    def users_playlists(self, playlist_id: str, user_id: str | None = None):
        self.playlist_requests.append((playlist_id, user_id))
        return self.playlist

    def albums(self, album_id: str):
        del album_id
        return [self.album]

    def albums_with_tracks(self, album_id: str):
        del album_id
        album = AlbumStub("Album", album_id="album-1")
        album.volumes = [[self.track]]
        return album

    def artists_direct_albums(
        self,
        artist_id: str,
        *,
        page: int = 0,
        page_size: int = 20,
        sort_by: str = "year",
    ):
        del artist_id, page, page_size, sort_by
        return self.artist_albums

    def artists_also_albums(
        self,
        artist_id: str,
        *,
        page: int = 0,
        page_size: int = 20,
        sort_by: str = "year",
    ):
        del artist_id, page, page_size, sort_by
        return self.artist_compilations

    def artists_tracks(
        self,
        artist_id: str,
        *,
        page: int = 0,
        page_size: int = 20,
    ):
        del artist_id, page, page_size
        return self.artist_tracks

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
    search_results = service.search_catalog("remote")
    liked_tracks = service.get_liked_tracks()
    user_playlists = service.get_user_playlists()
    generated_playlists = service.get_generated_playlists()
    stations = service.get_stations()
    station_tracks = service.get_station_tracks("user:onyourwave")
    album = service.get_album("album-1")
    album_tracks = service.get_album_tracks("album-1")
    artist_albums = service.get_artist_direct_albums("artist-1")
    artist_compilations = service.get_artist_compilation_albums("artist-1")
    artist_tracks = service.get_artist_tracks("artist-1")

    assert track.id == "track-1"
    assert track.album_title == "Album"
    assert playlist == Playlist(
        id="playlist-1",
        title="Playlist playlist-1",
        owner_id="7",
        owner_name="listener",
        description="Description playlist-1",
        track_count=1,
        artwork_ref=None,
    )
    assert client.playlist_requests == [("playlist-1", None), ("playlist-1", None)]
    assert [item.id for item in playlist_tracks] == ["track-1"]
    assert [item.id for item in search_tracks] == ["track-1"]
    assert search_results.albums == (
        Album(
            id="album-1",
            title="Album",
            artists=("Artist",),
            release_type=None,
            year=2024,
            track_count=1,
            artwork_ref="covers/album.jpg",
        ),
    )
    assert [item.id for item in search_results.singles] == ["single-1"]
    assert [item.id for item in search_results.compilations] == ["compilation-1"]
    assert search_results.artists == (
        Artist(id="artist-1", name="Artist", artwork_ref="covers/artist.jpg"),
    )
    assert [item.id for item in search_results.playlists] == ["playlist-1"]
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
    assert album.id == "album-1"
    assert [item.id for item in album_tracks] == ["track-1"]
    assert [item.id for item in artist_albums] == ["album-1", "single-1"]
    assert [item.id for item in artist_compilations] == ["compilation-1"]
    assert [item.id for item in artist_tracks] == ["track-1"]


def test_yandex_music_service_loads_playlist_tracks_with_owner_context() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    tracks = service.get_playlist_tracks("164404", owner_id="music-blog")

    assert [track.id for track in tracks] == ["track-1"]
    assert client.playlist_requests == [("164404", "music-blog")]


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
