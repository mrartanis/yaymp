from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.domain import (
    AuthRepo,
    AuthSession,
    Clock,
    LibraryCacheRepo,
    Logger,
    MusicService,
    PlaybackEngine,
    PlaybackState,
    PlaybackStatus,
    Playlist,
    SettingsRepo,
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

    def get_liked_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        return [Track(id=f"liked-{limit}", title="Liked", artists=("Artist",))]

    def get_playlist(self, playlist_id: str) -> Playlist:
        return Playlist(id=playlist_id, title="Playlist")

    def get_playlist_tracks(self, playlist_id: str) -> Sequence[Track]:
        return [Track(id=f"{playlist_id}-track", title="Playlist Track", artists=("Artist",))]

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
