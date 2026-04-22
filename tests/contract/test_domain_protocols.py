from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.domain import (
    Album,
    Artist,
    AudioQuality,
    AuthRepo,
    AuthSession,
    CatalogSearchResults,
    Clock,
    LibraryCacheRepo,
    Logger,
    MusicService,
    PlaybackEngine,
    PlaybackState,
    PlaybackStateRepo,
    PlaybackStatus,
    Playlist,
    QueueItem,
    SavedPlaybackQueue,
    SettingsRepo,
    Station,
    Track,
)


class FakeMusicService:
    def get_auth_session(self) -> AuthSession | None:
        return AuthSession(user_id="user-1", token="token")

    def build_auth_session(
        self,
        token: str,
        *,
        expires_at: datetime | None = None,
    ) -> AuthSession:
        return AuthSession(
            user_id="user-1",
            token=token,
            expires_at=expires_at,
            display_name="listener",
        )

    def get_track(self, track_id: str) -> Track:
        return Track(id=track_id, title=f"Track {track_id}", artists=("Artist",))

    def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        return [Track(id=f"{query}-{limit}", title=query, artists=("Artist",))]

    def search_catalog(self, query: str, *, limit: int = 25) -> CatalogSearchResults:
        return CatalogSearchResults(
            tracks=tuple(self.search_tracks(query, limit=limit)),
            albums=(Album(id=f"album-{query}", title=f"Album {query}"),),
        )

    def get_liked_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        return [Track(id=f"liked-{limit}", title="Liked", artists=("Artist",))]

    def get_liked_albums(self, *, limit: int = 100) -> Sequence[Album]:
        return [Album(id=f"liked-album-{limit}", title="Liked Album")]

    def get_liked_artists(self, *, limit: int = 100) -> Sequence[Artist]:
        return [Artist(id=f"liked-artist-{limit}", name="Liked Artist")]

    def like_track(self, track_id: str) -> None:
        self.liked_track_id = track_id

    def unlike_track(self, track_id: str) -> None:
        self.unliked_track_id = track_id

    def set_audio_quality(self, quality: AudioQuality) -> None:
        self.quality = quality

    def get_audio_quality(self) -> AudioQuality:
        return getattr(self, "quality", AudioQuality.HQ)

    def get_user_playlists(self) -> Sequence[Playlist]:
        return [Playlist(id="playlist-1", title="Playlist")]

    def get_generated_playlists(self) -> Sequence[Playlist]:
        return [Playlist(id="generated-1", title="Playlist of the day")]

    def get_stations(self) -> Sequence[Station]:
        return [Station(id="user:onyourwave", title="My Wave")]

    def get_station_tracks(self, station_id: str, *, limit: int = 25) -> Sequence[Track]:
        return [Track(id=f"{station_id}-{limit}", title="Wave Track", artists=("Artist",))]

    def get_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> Playlist:
        del owner_id
        return Playlist(id=playlist_id, title="Playlist")

    def get_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> Sequence[Track]:
        del owner_id
        return [Track(id=f"{playlist_id}-track", title="Playlist Track", artists=("Artist",))]

    def get_album(self, album_id: str) -> Album:
        return Album(id=album_id, title="Album")

    def get_album_tracks(self, album_id: str) -> Sequence[Track]:
        return [Track(id=f"{album_id}-track", title="Album Track", artists=("Artist",))]

    def get_artist_direct_albums(self, artist_id: str, *, limit: int = 50) -> Sequence[Album]:
        del limit
        return [Album(id=f"{artist_id}-album", title="Artist Album")]

    def get_artist_compilation_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> Sequence[Album]:
        del limit
        return [Album(id=f"{artist_id}-compilation", title="Artist Compilation")]

    def get_artist_tracks(self, artist_id: str, *, limit: int = 50) -> Sequence[Track]:
        return [Track(id=f"{artist_id}-track-{limit}", title="Artist Track", artists=("Artist",))]

    def resolve_stream_ref(self, track: Track) -> str:
        return track.stream_ref or f"stream:{track.id}"


class FakePlaybackEngine:
    def __init__(self) -> None:
        self._state = PlaybackState()

    def load(self, queue_item: Track, *, stream_ref: str) -> None:
        self._state = PlaybackState(
            status=PlaybackStatus.PAUSED,
            active_index=0,
            duration_ms=queue_item.duration_ms,
        )

    def play(self) -> None:
        self._state = PlaybackState(status=PlaybackStatus.PLAYING)

    def pause(self) -> None:
        self._state = PlaybackState(status=PlaybackStatus.PAUSED)

    def stop(self) -> None:
        self._state = PlaybackState(status=PlaybackStatus.STOPPED)

    def seek(self, position_ms: int) -> None:
        self._state = PlaybackState(status=self._state.status, position_ms=position_ms)

    def set_volume(self, volume: int) -> None:
        self._state = PlaybackState(status=self._state.status, volume=volume)

    def get_state(self) -> PlaybackState:
        return self._state

    def on_ready_for_seek(self, callback: Any) -> None:
        self.ready_for_seek_callback = callback


class FakeSettingsRepo:
    def load_settings(self) -> Mapping[str, Any]:
        return {"volume": 70}

    def save_settings(self, settings: Mapping[str, Any]) -> None:
        self.settings = dict(settings)


class FakeLibraryCacheRepo:
    def load_recent_searches(self) -> Sequence[str]:
        return ["ambient", "jazz"]

    def save_recent_searches(self, searches: Sequence[str]) -> None:
        self.searches = list(searches)

    def load_track_metadata(self, track_id: str) -> Track | None:
        return Track(id=track_id, title="Cached", artists=("Artist",))

    def save_track_metadata(self, track: Track) -> None:
        self.track = track

    def load_artwork_ref(self, item_id: str) -> str | None:
        return f"art:{item_id}"

    def save_artwork_ref(self, item_id: str, artwork_ref: str) -> None:
        self.artwork = (item_id, artwork_ref)


class FakePlaybackStateRepo:
    def load_playback_queue(self) -> SavedPlaybackQueue | None:
        return SavedPlaybackQueue(
            queue=(QueueItem(track=Track(id="track-1", title="Track", artists=("Artist",))),),
            active_index=0,
        )

    def save_playback_queue(
        self,
        queue: Sequence[QueueItem],
        *,
        active_index: int | None,
        position_ms: int = 0,
    ) -> None:
        self.saved_queue = SavedPlaybackQueue(
            queue=tuple(queue),
            active_index=active_index,
            position_ms=position_ms,
        )

    def clear_playback_queue(self) -> None:
        self.saved_queue = None


class FakeAuthRepo:
    def load_session(self) -> AuthSession | None:
        return AuthSession(user_id="user-2", token="token-2")

    def save_session(self, session: AuthSession) -> None:
        self.session = session

    def clear_session(self) -> None:
        self.session = None


class FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 4, 19, tzinfo=UTC)


def test_fakes_satisfy_runtime_checkable_protocols() -> None:
    assert isinstance(FakeMusicService(), MusicService)
    assert isinstance(FakePlaybackEngine(), PlaybackEngine)
    assert isinstance(FakePlaybackStateRepo(), PlaybackStateRepo)
    assert isinstance(FakeSettingsRepo(), SettingsRepo)
    assert isinstance(FakeLibraryCacheRepo(), LibraryCacheRepo)
    assert isinstance(FakeAuthRepo(), AuthRepo)
    assert isinstance(FakeClock(), Clock)
    assert isinstance(logging.getLogger("yaymp-test"), Logger)


def test_protocol_shaped_fakes_expose_expected_behavior() -> None:
    music_service = FakeMusicService()
    playback_engine = FakePlaybackEngine()

    track = music_service.search_tracks("signal")[0]
    stream_ref = music_service.resolve_stream_ref(track)
    playback_engine.load(track, stream_ref=stream_ref)
    playback_engine.play()

    assert stream_ref == f"stream:{track.id}"
    assert playback_engine.get_state().status is PlaybackStatus.PLAYING
