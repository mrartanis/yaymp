from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from app.domain import (
    Album,
    Artist,
    AudioQuality,
    AuthSession,
    CatalogSearchResults,
    DislikedTrackIds,
    LikedTrackIds,
    NetworkError,
    PlayEventReport,
    Playlist,
    RadioFeedbackType,
    RadioSession,
    Station,
    StationTrackBatch,
    Track,
    TrackCredits,
    WaveOption,
    WaveSettings,
)


class FakeMusicService:
    """Stateful in-process substitute for the external Yandex Music boundary."""

    def __init__(self, *, session: AuthSession | None = None) -> None:
        self.session = session
        self.tracks: dict[str, Track] = {}
        self.albums: dict[str, Album] = {}
        self.artists: dict[str, Artist] = {}
        self.playlists: dict[str, Playlist] = {}
        self.playlist_tracks: dict[str, tuple[Track, ...]] = {}
        self.catalog_searches: dict[str, CatalogSearchResults] = {}
        self.generated_playlist_ids: list[str] = []
        self.user_playlist_ids: list[str] = []
        self.liked_track_ids: set[str] = set()
        self.disliked_track_ids: set[str] = set()
        self.liked_album_ids: set[str] = set()
        self.liked_artist_ids: set[str] = set()
        self.disliked_artist_ids: set[str] = set()
        self.liked_playlist_ids: set[str] = set()
        self.station_tracks: dict[str, tuple[Track, ...]] = {}
        self.events: list[tuple[str, object]] = []
        self.offline = False
        self._liked_revision = 1
        self._disliked_revision = 1
        self._playlist_counter = 0
        self._audio_quality = AudioQuality.HQ
        self._language = "ru"
        self._ai_content_reduction_enabled = False

    def add_playlist(
        self,
        playlist: Playlist,
        *,
        tracks: Sequence[Track] = (),
        generated: bool = False,
        user_owned: bool = False,
        liked: bool = False,
    ) -> None:
        stored = replace(playlist, track_count=len(tracks), is_generated=generated)
        self.playlists[stored.id] = stored
        self.playlist_tracks[stored.id] = tuple(tracks)
        self.tracks.update((track.id, track) for track in tracks)
        if generated and stored.id not in self.generated_playlist_ids:
            self.generated_playlist_ids.append(stored.id)
        if user_owned and stored.id not in self.user_playlist_ids:
            self.user_playlist_ids.append(stored.id)
        if liked:
            self.liked_playlist_ids.add(stored.id)

    def get_auth_session(self) -> AuthSession | None:
        return self.session

    def set_auth_session(self, session: AuthSession) -> None:
        self.session = session

    def clear_auth_session(self) -> None:
        self.session = None

    def build_auth_session(
        self,
        token: str,
        *,
        expires_at: datetime | None = None,
    ) -> AuthSession:
        self.session = AuthSession(
            user_id=self.session.user_id if self.session else "fake-user",
            token=token,
            expires_at=expires_at,
            display_name=self.session.display_name if self.session else "Fake User",
        )
        return self.session

    def get_track(self, track_id: str) -> Track:
        self._require_online()
        return self.tracks[track_id]

    def get_tracks(self, track_ids: Sequence[str]) -> Sequence[Track]:
        self._require_online()
        return tuple(self.tracks[track_id] for track_id in track_ids if track_id in self.tracks)

    def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        return self.search_catalog(query, limit=limit).tracks

    def search_catalog(self, query: str, *, limit: int = 25) -> CatalogSearchResults:
        self._require_online()
        del limit
        self.events.append(("search", query))
        return self.catalog_searches.get(query.strip().casefold(), CatalogSearchResults())

    def get_liked_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        self._require_online()
        return tuple(
            replace(self.tracks[track_id], is_liked=True, is_disliked=False)
            for track_id in self.tracks
            if track_id in self.liked_track_ids
        )[:limit]

    def get_liked_track_ids(
        self,
        *,
        if_modified_since_revision: int = 0,
    ) -> LikedTrackIds | None:
        self._require_online()
        if if_modified_since_revision == self._liked_revision:
            return None
        return LikedTrackIds(
            user_id=self._user_id,
            revision=self._liked_revision,
            track_ids=frozenset(self.liked_track_ids),
        )

    def get_disliked_track_ids(
        self,
        *,
        if_modified_since_revision: int = 0,
    ) -> DislikedTrackIds | None:
        self._require_online()
        if if_modified_since_revision == self._disliked_revision:
            return None
        return DislikedTrackIds(
            user_id=self._user_id,
            revision=self._disliked_revision,
            track_ids=frozenset(self.disliked_track_ids),
        )

    def get_liked_albums(self, *, limit: int = 100) -> Sequence[Album]:
        self._require_online()
        return tuple(
            replace(album, is_liked=True)
            for album_id, album in self.albums.items()
            if album_id in self.liked_album_ids
        )[:limit]

    def get_liked_artists(self, *, limit: int = 100) -> Sequence[Artist]:
        self._require_online()
        return tuple(
            replace(artist, is_liked=True, is_disliked=False)
            for artist_id, artist in self.artists.items()
            if artist_id in self.liked_artist_ids
        )[:limit]

    def get_disliked_artists(self, *, limit: int = 100) -> Sequence[Artist]:
        self._require_online()
        return tuple(
            replace(artist, is_liked=False, is_disliked=True)
            for artist_id, artist in self.artists.items()
            if artist_id in self.disliked_artist_ids
        )[:limit]

    def get_liked_playlists(self, *, limit: int = 100) -> Sequence[Playlist]:
        self._require_online()
        return tuple(
            replace(self.playlists[playlist_id], is_liked=True)
            for playlist_id in self.liked_playlist_ids
            if playlist_id in self.playlists
        )[:limit]

    def like_track(self, track_id: str) -> None:
        self._require_online()
        self.liked_track_ids.add(track_id)
        self.disliked_track_ids.discard(track_id)
        self._liked_revision += 1
        self._disliked_revision += 1
        self.events.append(("like_track", track_id))

    def unlike_track(self, track_id: str) -> None:
        self._require_online()
        self.liked_track_ids.discard(track_id)
        self._liked_revision += 1
        self.events.append(("unlike_track", track_id))

    def dislike_track(self, track_id: str) -> None:
        self._require_online()
        self.liked_track_ids.discard(track_id)
        self.disliked_track_ids.add(track_id)
        self._liked_revision += 1
        self._disliked_revision += 1
        self.events.append(("dislike_track", track_id))

    def undislike_track(self, track_id: str) -> None:
        self._require_online()
        self.disliked_track_ids.discard(track_id)
        self._disliked_revision += 1
        self.events.append(("undislike_track", track_id))

    def like_album(self, album_id: str) -> None:
        self._require_online()
        self.liked_album_ids.add(album_id)

    def unlike_album(self, album_id: str) -> None:
        self._require_online()
        self.liked_album_ids.discard(album_id)

    def like_artist(self, artist_id: str) -> None:
        self._require_online()
        self.liked_artist_ids.add(artist_id)
        self.disliked_artist_ids.discard(artist_id)

    def unlike_artist(self, artist_id: str) -> None:
        self._require_online()
        self.liked_artist_ids.discard(artist_id)

    def dislike_artist(self, artist_id: str) -> None:
        self._require_online()
        self.liked_artist_ids.discard(artist_id)
        self.disliked_artist_ids.add(artist_id)

    def undislike_artist(self, artist_id: str) -> None:
        self._require_online()
        self.disliked_artist_ids.discard(artist_id)

    def like_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self._require_online()
        del owner_id
        self.liked_playlist_ids.add(playlist_id)

    def unlike_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self._require_online()
        del owner_id
        self.liked_playlist_ids.discard(playlist_id)

    def set_audio_quality(self, quality: AudioQuality) -> None:
        self._audio_quality = quality

    def get_audio_quality(self) -> AudioQuality:
        return self._audio_quality

    def set_language(self, language: str) -> None:
        self._language = language

    def get_language(self) -> str:
        return self._language

    def set_ai_content_reduction_enabled(self, enabled: bool) -> None:
        self._ai_content_reduction_enabled = enabled

    def get_ai_content_reduction_enabled(self) -> bool:
        return self._ai_content_reduction_enabled

    def load_account_ai_content_reduction_enabled(self) -> bool:
        self._require_online()
        return self._ai_content_reduction_enabled

    def save_account_ai_content_reduction_enabled(self, enabled: bool) -> bool:
        self._require_online()
        self._ai_content_reduction_enabled = enabled
        return enabled

    def get_track_credits(self, track_id: str) -> TrackCredits:
        self._require_online()
        return TrackCredits(items=(), raw_json="{}", language=self._language)

    def get_user_playlists(self) -> Sequence[Playlist]:
        self._require_online()
        return tuple(
            self.playlists[playlist_id]
            for playlist_id in self.user_playlist_ids
            if playlist_id in self.playlists
        )

    def create_playlist(self, title: str, *, visibility: str) -> Playlist:
        self._require_online()
        self._playlist_counter += 1
        playlist = Playlist(
            id=f"created-{self._playlist_counter}",
            title=title,
            owner_id=self._user_id,
            track_count=0,
            revision=1,
            visibility=visibility,
        )
        self.add_playlist(playlist, user_owned=True)
        self.events.append(("create_playlist", playlist.id))
        return self.playlists[playlist.id]

    def delete_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self._require_online()
        del owner_id
        self.playlists.pop(playlist_id, None)
        self.playlist_tracks.pop(playlist_id, None)
        if playlist_id in self.user_playlist_ids:
            self.user_playlist_ids.remove(playlist_id)

    def append_playlist_tracks(
        self,
        playlist_id: str,
        tracks: Sequence[Track],
        *,
        owner_id: str | None = None,
    ) -> Playlist:
        del owner_id
        return self._update_playlist_tracks(
            playlist_id,
            (*self.playlist_tracks[playlist_id], *tracks),
        )

    def replace_playlist_tracks(
        self,
        playlist_id: str,
        tracks: Sequence[Track],
        *,
        owner_id: str | None = None,
    ) -> Playlist:
        del owner_id
        return self._update_playlist_tracks(playlist_id, tuple(tracks))

    def get_generated_playlists(self) -> Sequence[Playlist]:
        self._require_online()
        return tuple(
            self.playlists[playlist_id]
            for playlist_id in self.generated_playlist_ids
            if playlist_id in self.playlists
        )

    def get_stations(self) -> Sequence[Station]:
        self._require_online()
        return (Station(id="user:onyourwave", title="My Wave"),)

    def get_wave_settings(self) -> WaveSettings:
        self._require_online()
        return WaveSettings(
            stations=(WaveOption("user:onyourwave", "My Wave", unspecified=True),),
            settings=(),
            selected_seeds=("user:onyourwave",),
        )

    def reset_last_wave(self) -> None:
        self._require_online()

    def get_station_tracks(self, station_id: str, *, limit: int = 25) -> Sequence[Track]:
        self._require_online()
        return self.station_tracks.get(station_id, ())[:limit]

    def get_station_track_batch(
        self,
        station_id: str,
        *,
        limit: int = 25,
        queue_track_id: str | None = None,
    ) -> StationTrackBatch:
        del queue_track_id
        return StationTrackBatch(
            station_id=station_id,
            batch_id=f"batch-{station_id}",
            tracks=tuple(self.get_station_tracks(station_id, limit=limit)),
        )

    def start_radio_session(
        self,
        station_id: str,
        *,
        seeds: Sequence[str] = (),
        limit: int = 25,
    ) -> RadioSession:
        batch = self.get_station_track_batch(station_id, limit=limit)
        return RadioSession(
            station_id=station_id,
            session_id=f"session-{station_id}",
            batch_id=batch.batch_id,
            feedback_from="fake-radio",
            tracks=batch.tracks,
            seeds=tuple(seeds),
        )

    def get_radio_session_tracks(
        self,
        session: RadioSession,
        *,
        queue: Sequence[str],
        limit: int = 25,
    ) -> RadioSession:
        del queue
        return replace(
            session,
            tracks=tuple(self.get_station_tracks(session.station_id, limit=limit)),
        )

    def get_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> Playlist:
        self._require_online()
        del owner_id
        return self.playlists[playlist_id]

    def get_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> Sequence[Track]:
        self._require_online()
        del owner_id
        return self.playlist_tracks.get(playlist_id, ())

    def get_album(self, album_id: str) -> Album:
        self._require_online()
        return self.albums[album_id]

    def get_album_tracks(self, album_id: str) -> Sequence[Track]:
        self._require_online()
        return tuple(track for track in self.tracks.values() if track.album_id == album_id)

    def get_artist_direct_albums(self, artist_id: str, *, limit: int = 50) -> Sequence[Album]:
        self._require_online()
        return tuple(
            album
            for album in self.albums.values()
            if artist_id in album.artist_ids and album.release_type != "compilation"
        )[:limit]

    def get_artist_compilation_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> Sequence[Album]:
        self._require_online()
        return tuple(
            album
            for album in self.albums.values()
            if artist_id in album.artist_ids and album.release_type == "compilation"
        )[:limit]

    def get_artist_playlists(self, artist_id: str, *, limit: int = 50) -> Sequence[Playlist]:
        self._require_online()
        del artist_id
        return tuple(self.playlists.values())[:limit]

    def get_artist_tracks(self, artist_id: str, *, limit: int = 50) -> Sequence[Track]:
        self._require_online()
        return tuple(
            track for track in self.tracks.values() if artist_id in track.artist_ids
        )[:limit]

    def resolve_stream_ref(self, track: Track) -> str:
        self._require_online()
        return track.stream_ref or f"fake://{track.id}"

    def report_play_audio(self, **payload: object) -> None:
        self.events.append(("play_audio", payload))

    def report_plays(
        self,
        events: Sequence[PlayEventReport],
        *,
        client_now: str,
    ) -> None:
        self.events.append(("plays", (tuple(events), client_now)))

    def report_station_radio_started(self, **payload: object) -> None:
        self.events.append(("radio_started", payload))

    def report_station_track_started(self, **payload: object) -> None:
        self.events.append(("track_started", payload))

    def report_station_track_finished(self, **payload: object) -> None:
        self.events.append(("track_finished", payload))

    def report_station_track_skipped(self, **payload: object) -> None:
        self.events.append(("track_skipped", payload))

    def report_radio_session_feedback(
        self,
        session: RadioSession,
        feedback_type: RadioFeedbackType,
        *,
        track_id: str | None = None,
        total_played_seconds: float | None = None,
    ) -> None:
        self.events.append(
            (
                "radio_feedback",
                (session.session_id, feedback_type, track_id, total_played_seconds),
            )
        )

    @property
    def _user_id(self) -> str:
        return self.session.user_id if self.session is not None else "fake-user"

    def _require_online(self) -> None:
        if self.offline:
            raise NetworkError("Fake Yandex Music service is offline")

    def _update_playlist_tracks(
        self,
        playlist_id: str,
        tracks: Sequence[Track],
    ) -> Playlist:
        self._require_online()
        stored_tracks = tuple(tracks)
        self.tracks.update((track.id, track) for track in stored_tracks)
        self.playlist_tracks[playlist_id] = stored_tracks
        playlist = self.playlists[playlist_id]
        updated = replace(
            playlist,
            track_count=len(stored_tracks),
            revision=(playlist.revision or 0) + 1,
        )
        self.playlists[playlist_id] = updated
        self.events.append(("update_playlist", playlist_id))
        return updated
