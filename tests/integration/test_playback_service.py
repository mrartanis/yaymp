import random

import pytest

from app.application.playback_service import PlaybackService
from app.domain import (
    Album,
    AudioQuality,
    CatalogSearchResults,
    PlaybackBackendError,
    PlaybackStatus,
    RepeatMode,
    StreamResolveError,
    Track,
)
from app.infrastructure.playback.fake_playback_engine import FakePlaybackEngine


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


class FakeMusicService:
    def __init__(self, *, track: Track | None = None, stream_ref: str | None = None) -> None:
        self.track = track
        self.stream_ref = stream_ref
        self.resolved_track_ids: list[str] = []
        self.loaded_track_ids: list[str] = []
        self.station_batches: dict[str, list[tuple[Track, ...]]] = {}
        self.station_requests: list[str] = []

    def get_auth_session(self):
        return None

    def build_auth_session(self, token: str, *, expires_at=None):
        from app.domain import AuthSession

        return AuthSession(user_id="user-1", token=token, expires_at=expires_at)

    def get_track(self, track_id: str) -> Track:
        self.loaded_track_ids.append(track_id)
        if self.track is not None:
            return self.track
        return Track(
            id=track_id,
            title=f"Track {track_id}",
            artists=("Artist",),
            duration_ms=200_000,
        )

    def search_tracks(self, query: str, *, limit: int = 25):
        del query, limit
        return ()

    def search_catalog(self, query: str, *, limit: int = 25):
        del query, limit
        return CatalogSearchResults()

    def get_liked_tracks(self, *, limit: int = 100):
        del limit
        return ()

    def like_track(self, track_id: str) -> None:
        self.liked_track_id = track_id

    def unlike_track(self, track_id: str) -> None:
        self.unliked_track_id = track_id

    def set_audio_quality(self, quality: AudioQuality) -> None:
        self.quality = quality

    def get_audio_quality(self) -> AudioQuality:
        return getattr(self, "quality", AudioQuality.HQ)

    def get_user_playlists(self):
        return ()

    def get_generated_playlists(self):
        return ()

    def get_stations(self):
        return ()

    def get_station_tracks(self, station_id: str, *, limit: int = 25):
        del limit
        self.station_requests.append(station_id)
        batches = self.station_batches.get(station_id)
        if batches:
            return batches.pop(0)
        return ()

    def get_playlist(self, playlist_id: str, *, owner_id: str | None = None):
        del owner_id
        raise NotImplementedError

    def get_playlist_tracks(self, playlist_id: str, *, owner_id: str | None = None):
        del playlist_id, owner_id
        return ()

    def get_album(self, album_id: str):
        return Album(id=album_id, title=f"Album {album_id}")

    def get_album_tracks(self, album_id: str):
        del album_id
        return ()

    def get_artist_direct_albums(self, artist_id: str, *, limit: int = 50):
        del artist_id, limit
        return ()

    def get_artist_compilation_albums(self, artist_id: str, *, limit: int = 50):
        del artist_id, limit
        return ()

    def get_artist_tracks(self, artist_id: str, *, limit: int = 50):
        del artist_id, limit
        return ()

    def resolve_stream_ref(self, track: Track) -> str:
        self.resolved_track_ids.append(track.id)
        if self.stream_ref is None:
            raise StreamResolveError("Stream resolution failed")
        return self.stream_ref


class FailingPlaybackEngine(FakePlaybackEngine):
    def __init__(self, *, fail_on_load: bool = False, fail_on_play: bool = False) -> None:
        super().__init__()
        self.fail_on_load = fail_on_load
        self.fail_on_play = fail_on_play

    def load(self, track: Track, *, stream_ref: str) -> None:
        if self.fail_on_load:
            raise PlaybackBackendError(f"Cannot load {track.id}")
        super().load(track, stream_ref=stream_ref)

    def play(self) -> None:
        if self.fail_on_play:
            raise PlaybackBackendError("Cannot start playback")
        super().play()


def build_tracks() -> tuple[Track, ...]:
    return (
        Track(id="one", title="One", artists=("Artist",), duration_ms=120_000, stream_ref="demo://one"),
        Track(id="two", title="Two", artists=("Artist",), duration_ms=180_000, stream_ref="demo://two"),
        Track(id="three", title="Three", artists=("Artist",), duration_ms=240_000, stream_ref="demo://three"),
    )


def test_replace_queue_and_play_from_index() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )

    snapshot = service.replace_queue(build_tracks(), start_index=1, source_type="test")

    assert snapshot.state.status is PlaybackStatus.PLAYING
    assert snapshot.state.active_index == 1
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "two"
    assert len(snapshot.queue) == 3


def test_append_queue_preserves_source_context() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks()[:1], start_index=0, source_type="track", source_id="one")

    snapshot = service.append_queue(
        build_tracks()[1:],
        source_type="album",
        source_id="album-1",
    )

    assert [item.track.id for item in snapshot.queue] == ["one", "two", "three"]
    assert snapshot.queue[1].source_type == "album"
    assert snapshot.queue[1].source_id == "album-1"
    assert snapshot.queue[1].source_index == 0


def test_play_single_track_replaces_queue_and_starts_playback() -> None:
    service = PlaybackService(playback_engine=FakePlaybackEngine(), logger=TestLogger())

    snapshot = service.play_track(build_tracks()[0], source_type="single-track")

    assert len(snapshot.queue) == 1
    assert snapshot.state.status is PlaybackStatus.PLAYING
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "one"


def test_next_and_previous_move_inside_queue() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=1, source_type="test")

    next_snapshot = service.next()
    previous_snapshot = service.previous()

    assert next_snapshot.state.active_index == 2
    assert previous_snapshot.state.active_index == 1


def test_refresh_auto_advances_when_active_track_finishes() -> None:
    engine = FakePlaybackEngine()
    service = PlaybackService(playback_engine=engine, logger=TestLogger())
    service.replace_queue(build_tracks(), start_index=0, source_type="test")

    engine.stop()
    snapshot = service.refresh()

    assert snapshot.state.status is PlaybackStatus.PLAYING
    assert snapshot.state.active_index == 1
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "two"


def test_refresh_does_not_auto_advance_after_manual_stop() -> None:
    service = PlaybackService(playback_engine=FakePlaybackEngine(), logger=TestLogger())
    service.replace_queue(build_tracks(), start_index=0, source_type="test")

    stopped_snapshot = service.stop()
    refreshed_snapshot = service.refresh()

    assert stopped_snapshot.state.status is PlaybackStatus.STOPPED
    assert refreshed_snapshot.state.status is PlaybackStatus.STOPPED
    assert refreshed_snapshot.state.active_index == 0


def test_queue_edges_stop_at_end_and_restart_track_at_beginning() -> None:
    service = PlaybackService(playback_engine=FakePlaybackEngine(), logger=TestLogger())
    service.replace_queue(build_tracks(), start_index=2, source_type="test")

    end_snapshot = service.next()
    start_snapshot = service.previous()

    assert end_snapshot.state.status is PlaybackStatus.STOPPED
    assert end_snapshot.state.active_index == 2
    assert start_snapshot.state.active_index == 1


def test_previous_at_queue_start_keeps_first_track_active() -> None:
    service = PlaybackService(playback_engine=FakePlaybackEngine(), logger=TestLogger())
    service.replace_queue(build_tracks(), start_index=0, source_type="test")

    snapshot = service.previous()

    assert snapshot.state.active_index == 0
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "one"


def test_repeat_all_wraps_queue_edges() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=2, source_type="test")
    service.set_repeat_mode(RepeatMode.ALL)

    snapshot = service.next()

    assert snapshot.state.active_index == 0
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "one"


def test_repeat_one_replays_current_track() -> None:
    service = PlaybackService(playback_engine=FakePlaybackEngine(), logger=TestLogger())
    service.replace_queue(build_tracks(), start_index=1, source_type="test")
    service.set_repeat_mode(RepeatMode.ONE)

    next_snapshot = service.next()
    previous_snapshot = service.previous()

    assert next_snapshot.state.active_index == 1
    assert previous_snapshot.state.active_index == 1
    assert previous_snapshot.state.position_ms == 0


def test_shuffle_uses_stable_order_and_previous_rewinds_that_order() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        randomizer=random.Random(7),
    )
    service.replace_queue(build_tracks(), start_index=0, source_type="test")
    service.set_shuffle_enabled(True)

    first = service.next()
    second = service.next()
    back = service.previous()

    assert first.current_item is not None
    assert second.current_item is not None
    assert back.current_item is not None
    assert first.current_item.track.id == "three"
    assert second.current_item.track.id == "two"
    assert back.current_item.track.id == "three"


def test_replace_queue_resolves_missing_stream_refs_through_music_service() -> None:
    music_service = FakeMusicService(stream_ref="resolved://one")
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        music_service=music_service,
    )

    snapshot = service.play_track(
        Track(id="one", title="One", artists=("Artist",), duration_ms=120_000),
        source_type="resolved",
    )

    assert snapshot.current_item is not None
    assert snapshot.current_item.track.stream_ref == "resolved://one"
    assert music_service.resolved_track_ids == ["one"]


def test_replace_queue_raises_when_stream_cannot_be_resolved() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        music_service=FakeMusicService(stream_ref=None),
    )

    with pytest.raises(StreamResolveError):
        service.play_track(Track(id="missing", title="Missing", artists=("Artist",)))


def test_play_track_by_id_loads_track_from_music_service() -> None:
    music_service = FakeMusicService(
        track=Track(
            id="remote-1",
            title="Remote",
            artists=("Artist",),
            duration_ms=210_000,
            stream_ref="resolved://remote-1",
        ),
        stream_ref="resolved://remote-1",
    )
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        music_service=music_service,
    )

    snapshot = service.play_track_by_id("remote-1")

    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "remote-1"
    assert music_service.loaded_track_ids == ["remote-1"]


def test_play_station_loads_initial_station_queue_and_starts_playback() -> None:
    music_service = FakeMusicService(stream_ref="resolved://wave")
    music_service.station_batches["user:onyourwave"] = [
        (
            Track(id="w1", title="Wave 1", artists=("Artist",), duration_ms=1_000),
            Track(id="w2", title="Wave 2", artists=("Artist",), duration_ms=1_000),
        )
    ]
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        music_service=music_service,
    )

    snapshot = service.play_station("user:onyourwave")

    assert snapshot.state.status is PlaybackStatus.PLAYING
    assert [item.track.id for item in snapshot.queue] == ["w1", "w2"]
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "w1"
    assert music_service.station_requests[0] == "user:onyourwave"


def test_station_queue_refills_when_near_end() -> None:
    music_service = FakeMusicService(stream_ref="resolved://wave")
    music_service.station_batches["user:onyourwave"] = [
        (
            Track(id="w1", title="Wave 1", artists=("Artist",), duration_ms=1_000),
            Track(id="w2", title="Wave 2", artists=("Artist",), duration_ms=1_000),
            Track(id="w3", title="Wave 3", artists=("Artist",), duration_ms=1_000),
        ),
        (
            Track(id="w3", title="Wave 3", artists=("Artist",), duration_ms=1_000),
            Track(id="w4", title="Wave 4", artists=("Artist",), duration_ms=1_000),
            Track(id="w5", title="Wave 5", artists=("Artist",), duration_ms=1_000),
        ),
    ]
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        music_service=music_service,
    )
    service.play_station("user:onyourwave")

    snapshot = service.next()

    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "w2"
    assert [item.track.id for item in snapshot.queue] == ["w1", "w2", "w3", "w4", "w5"]
    assert music_service.station_requests == ["user:onyourwave", "user:onyourwave"]


def test_next_rolls_back_active_index_when_backend_load_fails() -> None:
    service = PlaybackService(
        playback_engine=FailingPlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=0, source_type="test")
    service._playback_engine.fail_on_load = True

    with pytest.raises(PlaybackBackendError):
        service.next()

    snapshot = service.snapshot()
    assert snapshot.state.active_index == 0
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "one"


def test_replace_queue_surfaces_backend_play_errors_without_losing_loaded_track() -> None:
    service = PlaybackService(
        playback_engine=FailingPlaybackEngine(fail_on_play=True),
        logger=TestLogger(),
    )

    with pytest.raises(PlaybackBackendError):
        service.replace_queue(build_tracks(), start_index=0, source_type="test")

    snapshot = service.snapshot()
    assert snapshot.state.active_index is None
    assert snapshot.current_item is None


def test_playback_service_uses_domain_errors_for_invalid_queue_requests() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )

    with pytest.raises(PlaybackBackendError):
        service.replace_queue((), start_index=0)

    with pytest.raises(PlaybackBackendError):
        service.replace_queue(build_tracks(), start_index=99)


def test_seek_and_volume_persist_across_track_transitions() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=0, source_type="test")

    service.seek(45_000)
    service.set_volume(33)
    snapshot = service.next()

    assert snapshot.state.volume == 33
    assert snapshot.state.position_ms == 0
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "two"
