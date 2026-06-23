from __future__ import annotations

import pytest
from yandex_music.exceptions import NotFoundError, UnauthorizedError

from app.domain import (
    Album,
    Artist,
    AudioQuality,
    AuthError,
    AuthSession,
    NetworkError,
    PlayEventReport,
    RadioFeedbackType,
    RadioSession,
    Station,
    StationTrackBatch,
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
        version: str | None = None,
        available: bool = True,
        duration_ms: int = 180_000,
    ) -> None:
        self.id = track_id
        self.title = title
        self.version = version
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

    def get_og_image_url(self):
        raise AssertionError


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
    def __init__(self, tracks: list[TrackStub], *, revision: int = 3) -> None:
        self._tracks = tracks
        self.revision = revision
        self.tracks = [
            type(
                "TrackShortStub",
                (),
                {
                    "id": track.id,
                    "album_id": getattr(track.albums[0], "id", None) if track.albums else None,
                    "track_id": f"{track.id}:{track.albums[0].id}" if track.albums else track.id,
                    "timestamp": "2026-04-22T00:00:00+00:00",
                },
            )()
            for track in tracks
        ]

    def fetch_tracks(self):
        return self._tracks


class LikeStub:
    def __init__(
        self,
        *,
        album=None,
        artist=None,
        playlist=None,
        entity_id: str | None = None,
    ) -> None:
        self.album = album
        self.artist = artist
        self.playlist = playlist
        self.id = entity_id


class FakeYandexClient:
    def __init__(self) -> None:
        self.base_url = "https://api.music.yandex.net"
        self.report_unknown_fields = False
        self.track = TrackStub(track_id="track-1", title="Remote", version="Live Version")
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
        self.artist_brief_info_result = type(
            "ArtistBriefInfoStub",
            (),
            {"playlists": [self.playlist]},
        )()
        self.artist_tracks = type("ArtistTracksStub", (), {"tracks": [self.track]})()
        self.likes = LikesStub([self.track])
        self.dislikes = LikesStub([TrackStub(track_id="track-9", title="Muted Track")], revision=4)
        self.album_likes = [LikeStub(album=self.album)]
        self.artist_likes = [LikeStub(artist=ArtistResultStub())]
        self.artist_dislikes = [
            type(
                "ArtistDislikeStub",
                (),
                {
                    "id": "artist-9",
                    "name": "Muted Artist",
                    "cover_uri": "covers/disliked-artist.jpg",
                },
            )()
        ]
        self.playlist_likes = [LikeStub(playlist=self.playlist)]
        self.download_infos = [DownloadInfoStub("https://stream.example/track-1")]
        self.account = type("Account", (), {"uid": 7, "login": "listener"})()
        self.me = type("Me", (), {"account": self.account})()
        self.liked_track_ids: list[str] = []
        self.unliked_track_ids: list[str] = []
        self.disliked_track_ids: list[str] = []
        self.undisliked_track_ids: list[str] = []
        self.liked_album_ids: list[str] = []
        self.unliked_album_ids: list[str] = []
        self.liked_artist_ids: list[str] = []
        self.unliked_artist_ids: list[str] = []
        self.disliked_artist_ids: list[str] = []
        self.undisliked_artist_ids: list[str] = []
        self.liked_playlist_ids: list[str] = []
        self.unliked_playlist_ids: list[str] = []
        self.playlist_requests: list[tuple[str, str | None]] = []
        self.station_track_queue: str | None = None
        self.play_audio_calls: list[dict[str, object]] = []
        self.plays_calls: list[dict[str, object]] = []
        self.station_feedback_calls: list[dict[str, object]] = []
        self.radio_session_tracks_queue: list[str] = []
        self.radio_session_new_calls: list[dict[str, object]] = []
        self.request = self.FakeRequest(self)

    class FakeRequest:
        def __init__(self, client: "FakeYandexClient") -> None:
            self._client = client

        def _track_payload(self) -> dict[str, object]:
            return {
                "id": self._client.track.id,
                "title": self._client.track.title,
                "version": self._client.track.version,
                "available": self._client.track.available,
                "durationMs": self._client.track.duration_ms,
                "artists": [{"name": artist.name} for artist in self._client.track.artists],
                "albums": [
                    {
                        "id": album.id,
                        "title": album.title,
                        "year": album.year,
                        "artists": [{"name": artist.name} for artist in album.artists],
                    }
                    for album in self._client.track.albums
                ],
                "coverUri": self._client.track.cover_uri,
            }

        def post(self, url: str, data=None, json=None, **kwargs):
            del kwargs
            if url.endswith("/rotor/session/new"):
                self._client.radio_session_new_calls.append(json or data or {})
                return {
                    "radioSessionId": "session-1",
                    "batchId": "batch-1",
                    "descriptionSeed": {"type": "user", "tag": "onyourwave"},
                    "sequence": [
                        {"type": "track", "liked": False, "track": self._track_payload()}
                    ],
                }
            if url.endswith("/rotor/session/session-1/tracks"):
                payload = json if isinstance(json, dict) else data
                if isinstance(payload, dict):
                    queue = payload.get("queue") or []
                    if queue:
                        self._client.radio_session_tracks_queue.append(str(queue[0]))
                return {
                    "batchId": "batch-2",
                    "sequence": [
                        {"type": "track", "liked": False, "track": self._track_payload()}
                    ],
                }
            if url.endswith("/rotor/session/session-1/feedback"):
                payload = {"type": "session-feedback", **((json or data) or {})}
                self._client.station_feedback_calls.append(payload)
                return {"status": "ok"}
            if "/dislikes/tracks/add-multiple" in url:
                self._client.disliked_track_ids.append(str((data or {}).get("track-ids")))
                return {"revision": 4}
            if "/dislikes/tracks/remove" in url:
                self._client.undisliked_track_ids.append(str((data or {}).get("track-ids")))
                return {"revision": 5}
            if "/dislikes/artists/add-multiple" in url:
                self._client.disliked_artist_ids.append(str((data or {}).get("artist-ids")))
                return "ok"
            if "/dislikes/artists/remove" in url:
                self._client.undisliked_artist_ids.append(str((data or {}).get("artist-ids")))
                return "ok"
            if "/plays?client-now=" in url:
                self._client.plays_calls.append({"url": url, "payload": json if json is not None else data})
                return "ok"
            raise AssertionError(url)

        def get(self, url: str, params=None, **kwargs):
            del kwargs
            if url.endswith("/dislikes/tracks"):
                if (params or {}).get("if_modified_since_revision") == 4:
                    return {"result": None}
                return {
                    "result": {
                        "library": {
                            "uid": 7,
                            "revision": 4,
                            "tracks": [{"id": "track-9", "albumId": "album-9"}],
                        }
                    }
                }
            if url.endswith("/dislikes/artists"):
                return {
                    "result": [
                        {
                            "id": "artist-9",
                            "name": "Muted Artist",
                            "cover": {"uri": "covers/disliked-artist.jpg"},
                        }
                    ]
                }
            raise AssertionError(url)

    def tracks(self, track_ids):
        if track_ids == ["missing"]:
            return []
        return [self.track]

    def search(self, query: str, *, type_: str | None = None):
        del query, type_
        return self.search_result

    def users_likes_tracks(self, if_modified_since_revision: int = 0):
        if if_modified_since_revision == self.likes.revision:
            return None
        return self.likes

    def users_likes_albums(self, user_id=None, rich: bool = True):
        del user_id, rich
        return self.album_likes

    def users_likes_artists(self, user_id=None, with_timestamps: bool = True):
        del user_id, with_timestamps
        return self.artist_likes

    def users_likes_playlists(self, user_id=None):
        del user_id
        return self.playlist_likes

    def users_dislikes_tracks(self, user_id=None, if_modified_since_revision: int = 0):
        del user_id
        if if_modified_since_revision == self.dislikes.revision:
            return None
        return self.dislikes

    def users_dislikes_artists(self, user_id=None):
        del user_id
        return self.artist_dislikes

    def users_likes_tracks_add(self, track_id: str):
        self.liked_track_ids.append(track_id)

    def users_likes_tracks_remove(self, track_id: str):
        self.unliked_track_ids.append(track_id)

    def users_dislikes_tracks_add(self, track_id: str):
        self.disliked_track_ids.append(track_id)

    def users_dislikes_tracks_remove(self, track_id: str):
        self.undisliked_track_ids.append(track_id)

    def users_likes_albums_add(self, album_id: str):
        self.liked_album_ids.append(album_id)

    def users_likes_albums_remove(self, album_id: str):
        self.unliked_album_ids.append(album_id)

    def users_likes_artists_add(self, artist_id: str):
        self.liked_artist_ids.append(artist_id)

    def users_likes_artists_remove(self, artist_id: str):
        self.unliked_artist_ids.append(artist_id)

    def users_dislikes_artists_add(self, artist_id: str):
        self.disliked_artist_ids.append(artist_id)

    def users_dislikes_artists_remove(self, artist_id: str):
        self.undisliked_artist_ids.append(artist_id)

    def users_likes_playlists_add(self, playlist_id: str):
        self.liked_playlist_ids.append(playlist_id)

    def users_likes_playlists_remove(self, playlist_id: str):
        self.unliked_playlist_ids.append(playlist_id)

    def users_playlists_list(self):
        return [self.playlist]

    def users_playlists(self, playlist_id: str, user_id: str | None = None):
        self.playlist_requests.append((playlist_id, user_id))
        return self.playlist

    def albums(self, album_id: str):
        del album_id
        return [self.album]

    def artists(self, artist_ids):
        del artist_ids
        return [ArtistResultStub()]

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

    def artists_brief_info(self, artist_id: str):
        del artist_id
        return self.artist_brief_info_result

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

    def rotor_station_tracks(self, station_id: str, queue: str | None = None):
        del station_id
        self.station_track_queue = queue
        sequence_item = type("SequenceItem", (), {"track": self.track})()
        return type(
            "StationTracksResultStub",
            (),
            {"sequence": [sequence_item], "batch_id": "batch-1"},
        )()

    def play_audio(self, **kwargs):
        self.play_audio_calls.append(kwargs)
        return True

    def rotor_station_feedback_radio_started(self, **kwargs):
        self.station_feedback_calls.append({"type": "radioStarted", **kwargs})
        return True

    def rotor_station_feedback_track_started(self, **kwargs):
        self.station_feedback_calls.append({"type": "trackStarted", **kwargs})
        return True

    def rotor_station_feedback_track_finished(self, **kwargs):
        self.station_feedback_calls.append({"type": "trackFinished", **kwargs})
        return True

    def rotor_station_feedback_skip(self, **kwargs):
        self.station_feedback_calls.append({"type": "skip", **kwargs})
        return True

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
    liked_track_ids = service.get_liked_track_ids()
    unchanged_liked_track_ids = service.get_liked_track_ids(
        if_modified_since_revision=client.likes.revision
    )
    disliked_track_ids = service.get_disliked_track_ids()
    unchanged_disliked_track_ids = service.get_disliked_track_ids(
        if_modified_since_revision=4
    )
    liked_albums = service.get_liked_albums()
    liked_artists = service.get_liked_artists()
    disliked_artists = service.get_disliked_artists()
    liked_playlists = service.get_liked_playlists()
    user_playlists = service.get_user_playlists()
    generated_playlists = service.get_generated_playlists()
    stations = service.get_stations()
    station_tracks = service.get_station_tracks("user:onyourwave")
    station_batch = service.get_station_track_batch("user:onyourwave", queue_track_id="track-0")
    album = service.get_album("album-1")
    album_tracks = service.get_album_tracks("album-1")
    artist_albums = service.get_artist_direct_albums("artist-1")
    artist_compilations = service.get_artist_compilation_albums("artist-1")
    artist_playlists = service.get_artist_playlists("artist-1")
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
    assert liked_track_ids is not None
    assert liked_track_ids.revision == 3
    assert liked_track_ids.track_ids == frozenset({"track-1"})
    assert unchanged_liked_track_ids is None
    assert disliked_track_ids is not None
    assert disliked_track_ids.revision == 4
    assert disliked_track_ids.track_ids == frozenset({"track-9"})
    assert unchanged_disliked_track_ids is None
    assert [item.id for item in liked_albums] == ["album-1"]
    assert [item.id for item in liked_artists] == ["artist-1"]
    assert disliked_artists == (
        Artist(
            id="artist-9",
            name="Muted Artist",
            artwork_ref="covers/disliked-artist.jpg",
            is_disliked=True,
        ),
    )
    assert [item.id for item in liked_playlists] == ["playlist-1"]
    assert [item.id for item in user_playlists] == ["playlist-1"]
    assert [item.id for item in generated_playlists] == ["generated-1"]
    assert generated_playlists[0].is_generated is True
    assert stations == (
        Station(
            id="user:onyourwave",
            title="My Wave",
            description="Personal station",
            icon_ref="station.jpg",
        ),
    )
    assert [item.id for item in station_tracks] == ["track-1"]
    assert station_batch == StationTrackBatch(
        station_id="user:onyourwave",
        batch_id="batch-1",
        tracks=(track,),
    )
    assert client.station_track_queue == "track-0"
    assert album.id == "album-1"
    assert [item.id for item in album_tracks] == ["track-1"]
    assert [item.id for item in artist_albums] == ["album-1", "single-1"]
    assert [item.id for item in artist_compilations] == ["compilation-1"]
    assert [item.id for item in artist_playlists] == ["playlist-1"]
    assert [item.id for item in artist_tracks] == ["track-1"]


def test_yandex_music_service_maps_artist_cover_from_nested_cover_uri() -> None:
    client = FakeYandexClient()
    client.search_result = SearchResultStub(
        [],
        artists=[
            type(
                "ArtistCoverStub",
                (),
                {
                    "id": "artist-2",
                    "name": "Covered Artist",
                    "cover": type("CoverStub", (), {"uri": "covers/artist-nested.jpg"})(),
                },
            )()
        ]
    )
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    search_results = service.search_catalog("covered")

    assert search_results.artists == (
        Artist(id="artist-2", name="Covered Artist", artwork_ref="covers/artist-nested.jpg"),
    )


def test_yandex_music_service_loads_playlist_tracks_with_owner_context() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    tracks = service.get_playlist_tracks("164404", owner_id="music-blog")

    assert [track.id for track in tracks] == ["track-1"]
    assert tracks[0].version == "Live Version"
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


def test_yandex_music_service_reports_playback_telemetry() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )
    track = Track(
        id="track-1",
        title="Remote",
        artists=("Artist",),
        album_id="album-1",
    )

    service.report_play_audio(
        track=track,
        from_="desktop_win-yaymp",
        play_id="play-1",
        track_length_seconds=180,
        total_played_seconds=42,
        end_position_seconds=42,
        playlist_id="user-1:3",
        timestamp="2026-05-12T14:00:42.000000Z",
        client_now="2026-05-12T14:00:42.000000Z",
    )
    service.report_plays(
        (
            PlayEventReport(
                track_id="track-1",
                from_="mobile-album-track-default",
                play_id="play-1",
                timestamp="2026-05-12T14:00:00.000000Z",
                start_timestamp="2026-05-12T14:00:00.000000Z",
                add_tracks_to_player_time="2026-05-12T14:00:00.000000Z",
                track_length_seconds=180.0,
                total_played_seconds=42.0,
                start_position_seconds=0.0,
                end_position_seconds=42.0,
                context="album",
                context_item="album-1",
                album_id="album-1",
                change_reason="skip",
            ),
        ),
        client_now="2026-05-12T14:00:42.000000Z",
    )
    service.report_station_radio_started(
        station_id="user:onyourwave",
        from_="desktop_win-radio-user-onyourwave",
        batch_id="batch-1",
    )
    service.report_station_track_started(
        station_id="user:onyourwave",
        track_id="track-1",
        batch_id="batch-1",
    )
    service.report_station_track_finished(
        station_id="user:onyourwave",
        track_id="track-1",
        total_played_seconds=180.0,
        batch_id="batch-1",
    )
    service.report_station_track_skipped(
        station_id="user:onyourwave",
        track_id="track-1",
        total_played_seconds=12.0,
        batch_id="batch-1",
    )

    assert client.play_audio_calls == [
        {
            "track_id": "track-1",
            "from_": "desktop_win-yaymp",
            "album_id": "album-1",
            "playlist_id": "user-1:3",
            "play_id": "play-1",
            "timestamp": "2026-05-12T14:00:42.000000Z",
            "track_length_seconds": 180,
            "total_played_seconds": 42,
            "end_position_seconds": 42,
            "client_now": "2026-05-12T14:00:42.000000Z",
        }
    ]
    assert client.plays_calls == [
        {
            "url": "https://api.music.yandex.net/plays?client-now=2026-05-12T14:00:42.000000Z",
            "payload": {
                "plays": [
                    {
                        "trackId": "track-1",
                        "from": "mobile-album-track-default",
                        "fromCache": False,
                        "playId": "play-1",
                        "timestamp": "2026-05-12T14:00:00.000000Z",
                        "startTimestamp": "2026-05-12T14:00:00.000000Z",
                        "addTracksToPlayerTime": "2026-05-12T14:00:00.000000Z",
                        "trackLengthSeconds": 180.0,
                        "totalPlayedSeconds": 42.0,
                        "startPositionSeconds": 0.0,
                        "endPositionSeconds": 42.0,
                        "context": "album",
                        "contextItem": "album-1",
                        "albumId": "album-1",
                        "changeReason": "skip",
                    }
                ]
            },
        }
    ]
    assert [call["type"] for call in client.station_feedback_calls] == [
        "radioStarted",
        "trackStarted",
        "trackFinished",
        "skip",
    ]


def test_yandex_music_service_uses_radio_session_flow() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    session = service.start_radio_session("user:onyourwave")
    continued = service.get_radio_session_tracks(session)
    service.report_radio_session_feedback(session, RadioFeedbackType.RADIO_STARTED)
    service.report_radio_session_feedback(
        session,
        RadioFeedbackType.TRACK_STARTED,
        track_id="track-1",
    )
    service.report_radio_session_feedback(
        session,
        RadioFeedbackType.TRACK_FINISHED,
        track_id="track-1",
        total_played_seconds=180.0,
    )

    assert session == RadioSession(
        station_id="user:onyourwave",
        session_id="session-1",
        batch_id="batch-1",
        feedback_from="radio-mobile-user-onyourwave-default",
        queue_anchor_track_id="track-1",
        tracks=(
            Track(
                id="track-1",
                title="Remote",
                artists=("Artist",),
                version="Live Version",
                artist_ids=(),
                album_id="album-1",
                album_title="Album",
                album_year=2024,
                duration_ms=180_000,
                artwork_ref="covers/track.jpg",
                accent_color=None,
                available=True,
                is_liked=False,
            ),
        ),
    )
    assert continued.batch_id == "batch-2"
    assert client.radio_session_new_calls == [
        {"seeds": ["user:onyourwave"], "includeTracksInResponse": True}
    ]
    assert client.radio_session_tracks_queue == ["track-1"]
    assert client.station_feedback_calls == [
        {
            "type": "session-feedback",
            "event": {
                "type": "radioStarted",
                "timestamp": client.station_feedback_calls[0]["event"]["timestamp"],
            },
            "batchId": "batch-1",
            "from": "radio-mobile-user-onyourwave-default",
        },
        {
            "type": "session-feedback",
            "event": {
                "type": "trackStarted",
                "timestamp": client.station_feedback_calls[1]["event"]["timestamp"],
                "trackId": "track-1",
            },
            "batchId": "batch-1",
            "from": "radio-mobile-user-onyourwave-default",
        },
        {
            "type": "session-feedback",
            "event": {
                "type": "trackFinished",
                "timestamp": client.station_feedback_calls[2]["event"]["timestamp"],
                "trackId": "track-1",
                "totalPlayedSeconds": 180.0,
            },
            "batchId": "batch-1",
            "from": "radio-mobile-user-onyourwave-default",
        },
    ]


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


def test_yandex_music_service_dislikes_and_undislikes_tracks_and_artists() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    service.dislike_track("track-1")
    service.undislike_track("track-1")
    service.dislike_artist("artist-1")
    service.undislike_artist("artist-1")

    assert client.disliked_track_ids == ["track-1"]
    assert client.undisliked_track_ids == ["track-1"]
    assert client.disliked_artist_ids == ["artist-1"]
    assert client.undisliked_artist_ids == ["artist-1"]


def test_yandex_music_service_likes_and_unlikes_album_artist_and_playlist() -> None:
    client = FakeYandexClient()
    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=client,
    )

    service.like_album("album-1")
    service.unlike_album("album-1")
    service.like_artist("artist-1")
    service.unlike_artist("artist-1")
    service.like_playlist("playlist-1", owner_id="7")
    service.unlike_playlist("playlist-1", owner_id="7")

    assert client.liked_album_ids == ["album-1"]
    assert client.unliked_album_ids == ["album-1"]
    assert client.liked_artist_ids == ["artist-1"]
    assert client.unliked_artist_ids == ["artist-1"]
    assert client.liked_playlist_ids == ["7:playlist-1"]
    assert client.unliked_playlist_ids == ["7:playlist-1"]


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


def test_yandex_music_service_maps_unauthorized_failures_to_auth_error() -> None:
    class UnauthorizedClient(FakeYandexClient):
        def tracks(self, track_ids):
            del track_ids
            raise UnauthorizedError("expired token")

    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=UnauthorizedClient(),
    )

    with pytest.raises(AuthError):
        service.get_track("track-1")


def test_yandex_music_service_maps_not_found_tracks_to_unavailable() -> None:
    class NotFoundClient(FakeYandexClient):
        def tracks(self, track_ids):
            del track_ids
            raise NotFoundError("missing")

    service = YandexMusicService(
        session=AuthSession(user_id="user-1", token="token"),
        client=NotFoundClient(),
    )

    with pytest.raises(TrackUnavailableError):
        service.get_track("missing")
