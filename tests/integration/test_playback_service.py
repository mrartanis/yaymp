import random

import pytest

from app.application.playback_service import PlaybackService
from app.domain import (
    Album,
    AudioQuality,
    CatalogSearchResults,
    LikedTrackIds,
    LikedTrackSnapshot,
    PlaybackBackendError,
    PlaybackStatus,
    QueueItem,
    RepeatMode,
    SavedPlaybackQueue,
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
        from app.domain import AuthSession

        return AuthSession(user_id="user-1", token="token")

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

    def get_liked_track_ids(self, *, if_modified_since_revision: int = 0):
        del if_modified_since_revision
        return LikedTrackIds(user_id="user-1", revision=1, track_ids=frozenset())

    def get_liked_albums(self, *, limit: int = 100):
        del limit
        return ()

    def get_liked_artists(self, *, limit: int = 100):
        del limit
        return ()

    def get_liked_playlists(self, *, limit: int = 100):
        del limit
        return ()

    def like_track(self, track_id: str) -> None:
        self.liked_track_id = track_id

    def unlike_track(self, track_id: str) -> None:
        self.unliked_track_id = track_id

    def like_album(self, album_id: str) -> None:
        self.liked_album_id = album_id

    def unlike_album(self, album_id: str) -> None:
        self.unliked_album_id = album_id

    def like_artist(self, artist_id: str) -> None:
        self.liked_artist_id = artist_id

    def unlike_artist(self, artist_id: str) -> None:
        self.unliked_artist_id = artist_id

    def like_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self.liked_playlist = (playlist_id, owner_id)

    def unlike_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self.unliked_playlist = (playlist_id, owner_id)

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

    def get_artist_playlists(self, artist_id: str, *, limit: int = 50):
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
    def __init__(
        self,
        *,
        fail_on_load: bool = False,
        fail_on_play: bool = False,
        fail_on_seek: bool = False,
    ) -> None:
        super().__init__()
        self.fail_on_load = fail_on_load
        self.fail_on_play = fail_on_play
        self.fail_on_seek = fail_on_seek

    def load(self, track: Track, *, stream_ref: str) -> None:
        if self.fail_on_load:
            raise PlaybackBackendError(f"Cannot load {track.id}")
        super().load(track, stream_ref=stream_ref)

    def play(self) -> None:
        if self.fail_on_play:
            raise PlaybackBackendError("Cannot start playback")
        super().play()

    def seek(self, position_ms: int) -> None:
        if self.fail_on_seek:
            raise PlaybackBackendError("Cannot seek yet")
        super().seek(position_ms)


class InMemoryPlaybackStateRepo:
    def __init__(self, saved_queue: SavedPlaybackQueue | None = None) -> None:
        self.saved_queue = saved_queue
        self.load_error: Exception | None = None

    def load_playback_queue(self) -> SavedPlaybackQueue | None:
        if self.load_error is not None:
            raise self.load_error
        return self.saved_queue

    def save_playback_queue(
        self,
        queue,
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


class InMemoryLibraryCacheRepo:
    def __init__(self) -> None:
        self.catalog_search = {}
        self.tracks: dict[str, Track] = {}
        self.liked_tracks: dict[str, LikedTrackIds] = {}
        self.liked_track_snapshots: dict[str, LikedTrackSnapshot] = {}
        self.liked_album_snapshots: dict[str, tuple[Album, ...]] = {}
        self.liked_artist_snapshots: dict[str, tuple] = {}
        self.liked_playlist_snapshots: dict[str, tuple] = {}
        self.user_playlist_snapshots: dict[str, tuple] = {}
        self.generated_playlist_snapshots: dict[str, tuple] = {}

    def load_recent_searches(self):
        return ()

    def save_recent_searches(self, searches):
        del searches

    def load_catalog_search(self, query: str):
        return self.catalog_search.get(query.strip().casefold())

    def save_catalog_search(self, query: str, results):
        self.catalog_search[query.strip().casefold()] = results

    def load_track_metadata(self, track_id: str):
        return self.tracks.get(track_id)

    def save_track_metadata(self, track: Track):
        self.tracks[track.id] = track

    def load_liked_track_ids(self, user_id: str):
        return self.liked_tracks.get(user_id)

    def save_liked_track_ids(self, liked_tracks: LikedTrackIds):
        self.liked_tracks[liked_tracks.user_id] = liked_tracks

    def load_liked_track_snapshot(self, user_id: str):
        return self.liked_track_snapshots.get(user_id)

    def save_liked_track_snapshot(self, snapshot: LikedTrackSnapshot):
        self.liked_track_snapshots[snapshot.user_id] = snapshot

    def load_liked_album_snapshot(self, user_id: str):
        return self.liked_album_snapshots.get(user_id)

    def save_liked_album_snapshot(self, user_id: str, albums):
        self.liked_album_snapshots[user_id] = tuple(albums)

    def load_liked_artist_snapshot(self, user_id: str):
        return self.liked_artist_snapshots.get(user_id)

    def save_liked_artist_snapshot(self, user_id: str, artists):
        self.liked_artist_snapshots[user_id] = tuple(artists)

    def load_liked_playlist_snapshot(self, user_id: str):
        return self.liked_playlist_snapshots.get(user_id)

    def save_liked_playlist_snapshot(self, user_id: str, playlists):
        self.liked_playlist_snapshots[user_id] = tuple(playlists)

    def load_user_playlist_snapshot(self, user_id: str):
        return self.user_playlist_snapshots.get(user_id)

    def save_user_playlist_snapshot(self, user_id: str, playlists):
        self.user_playlist_snapshots[user_id] = tuple(playlists)

    def load_generated_playlist_snapshot(self, user_id: str):
        return self.generated_playlist_snapshots.get(user_id)

    def save_generated_playlist_snapshot(self, user_id: str, playlists):
        self.generated_playlist_snapshots[user_id] = tuple(playlists)

    def mark_track_liked(self, user_id: str, track_id: str):
        current = self.liked_tracks.get(
            user_id,
            LikedTrackIds(user_id=user_id, revision=0, track_ids=frozenset()),
        )
        self.liked_tracks[user_id] = LikedTrackIds(
            user_id=user_id,
            revision=current.revision,
            track_ids=current.track_ids | {track_id},
        )

    def mark_track_unliked(self, user_id: str, track_id: str):
        current = self.liked_tracks.get(user_id)
        if current is None:
            return
        self.liked_tracks[user_id] = LikedTrackIds(
            user_id=user_id,
            revision=current.revision,
            track_ids=current.track_ids - {track_id},
        )

    def load_artwork_ref(self, item_id: str):
        del item_id
        return None

    def save_artwork_ref(self, item_id: str, artwork_ref: str):
        del item_id, artwork_ref


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


def test_insert_queue_next_places_tracks_after_active_item() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=0, source_type="album", source_id="album-1")

    snapshot = service.insert_queue_next(
        (
            Track(id="next-1", title="Next 1", artists=("Artist",), stream_ref="demo://next-1"),
            Track(id="next-2", title="Next 2", artists=("Artist",), stream_ref="demo://next-2"),
        ),
        source_type="track",
        source_id="next",
    )

    assert [item.track.id for item in snapshot.queue] == ["one", "next-1", "next-2", "two", "three"]
    assert snapshot.state.active_index == 0


def test_move_queue_item_next_reorders_existing_item() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=0, source_type="album", source_id="album-1")

    snapshot = service.move_queue_item_next(2)

    assert [item.track.id for item in snapshot.queue] == ["one", "three", "two"]
    assert snapshot.state.active_index == 0


def test_remove_queue_index_removes_non_active_item_without_interrupting_playback() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=0, source_type="album", source_id="album-1")

    snapshot = service.remove_queue_index(1)

    assert [item.track.id for item in snapshot.queue] == ["one", "three"]
    assert snapshot.state.active_index == 0
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "one"


def test_remove_queue_index_replaces_active_item_with_next_track() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=1, source_type="album", source_id="album-1")

    snapshot = service.remove_queue_index(1)

    assert [item.track.id for item in snapshot.queue] == ["one", "three"]
    assert snapshot.state.active_index == 1
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "three"
    assert snapshot.state.status is PlaybackStatus.PLAYING


def test_playback_service_persists_queue_after_replace_and_append() -> None:
    state_repo = InMemoryPlaybackStateRepo()
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        playback_state_repo=state_repo,
    )

    service.replace_queue(build_tracks()[:1], start_index=0, source_type="track", source_id="one")
    service.append_queue(build_tracks()[1:], source_type="album", source_id="album-1")

    assert state_repo.saved_queue is not None
    assert [item.track.id for item in state_repo.saved_queue.queue] == ["one", "two", "three"]
    assert state_repo.saved_queue.active_index == 0
    assert state_repo.saved_queue.position_ms == 0


def test_playback_service_clears_queue_and_saved_state() -> None:
    state_repo = InMemoryPlaybackStateRepo()
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        playback_state_repo=state_repo,
    )
    service.replace_queue(build_tracks(), start_index=1, source_type="album", source_id="album-1")

    snapshot = service.clear_queue()

    assert snapshot.queue == ()
    assert snapshot.current_item is None
    assert snapshot.state.active_index is None
    assert snapshot.state.status is PlaybackStatus.STOPPED
    assert state_repo.saved_queue is None


def test_playback_service_drops_saved_queue_when_restore_fails() -> None:
    state_repo = InMemoryPlaybackStateRepo(
        SavedPlaybackQueue(
            queue=(QueueItem(track=Track(id="one", title="One", artists=("Artist",))),),
            active_index=0,
        )
    )
    state_repo.load_error = RuntimeError("bad state")
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        playback_state_repo=state_repo,
    )

    snapshot = service.restore_saved_queue()

    assert snapshot.queue == ()
    assert state_repo.saved_queue is None


def test_playback_service_persists_seek_position() -> None:
    state_repo = InMemoryPlaybackStateRepo()
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        playback_state_repo=state_repo,
    )

    service.replace_queue(build_tracks(), start_index=0, source_type="album", source_id="album-1")
    service.seek(45_000)

    assert state_repo.saved_queue is not None
    assert state_repo.saved_queue.position_ms == 45_000


def test_playback_service_restores_saved_queue_without_autoplay() -> None:
    state_repo = InMemoryPlaybackStateRepo(
        SavedPlaybackQueue(
            queue=(
                QueueItem(
                    track=Track(id="one", title="One", artists=("Artist",)),
                    source_type="album",
                    source_id="album-1",
                    source_index=0,
                ),
            ),
            active_index=0,
            position_ms=45_000,
        )
    )
    music_service = FakeMusicService(stream_ref="resolved://one")
    engine = FakePlaybackEngine()
    service = PlaybackService(
        playback_engine=engine,
        logger=TestLogger(),
        music_service=music_service,
        playback_state_repo=state_repo,
    )

    restored = service.restore_saved_queue()
    played = service.play()
    engine.emit_ready_for_seek()
    refreshed = service.refresh()

    assert restored.state.status is PlaybackStatus.STOPPED
    assert restored.state.position_ms == 45_000
    assert restored.current_item is not None
    assert restored.current_item.track.id == "one"
    assert music_service.resolved_track_ids == ["one"]
    assert played.state.status is PlaybackStatus.PLAYING
    assert refreshed.state.status is PlaybackStatus.PLAYING
    assert refreshed.state.position_ms == 45_000


def test_playback_service_applies_restore_seek_on_backend_ready_event() -> None:
    state_repo = InMemoryPlaybackStateRepo(
        SavedPlaybackQueue(
            queue=(QueueItem(track=Track(id="one", title="One", artists=("Artist",))),),
            active_index=0,
            position_ms=45_000,
        )
    )
    engine = FakePlaybackEngine()
    service = PlaybackService(
        playback_engine=engine,
        logger=TestLogger(),
        music_service=FakeMusicService(stream_ref="resolved://one"),
        playback_state_repo=state_repo,
    )
    restored = service.restore_saved_queue()
    played = service.play()
    before_ready = service.refresh()
    engine.emit_ready_for_seek()
    after_ready = service.refresh()

    assert restored.state.position_ms == 45_000
    assert played.state.status is PlaybackStatus.PLAYING
    assert before_ready.state.status is PlaybackStatus.PLAYING
    assert before_ready.state.position_ms == 0
    assert after_ready.state.position_ms == 45_000


def test_playback_service_does_not_retry_restore_seek_after_ready_event_failure() -> None:
    state_repo = InMemoryPlaybackStateRepo(
        SavedPlaybackQueue(
            queue=(QueueItem(track=Track(id="one", title="One", artists=("Artist",))),),
            active_index=0,
            position_ms=45_000,
        )
    )
    engine = FailingPlaybackEngine(fail_on_seek=True)
    service = PlaybackService(
        playback_engine=engine,
        logger=TestLogger(),
        music_service=FakeMusicService(stream_ref="resolved://one"),
        playback_state_repo=state_repo,
    )
    service.restore_saved_queue()
    service.play()
    engine.emit_ready_for_seek()
    engine.fail_on_seek = False
    engine.emit_ready_for_seek()

    assert service.refresh().state.position_ms == 0


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


def test_play_station_preserves_cached_liked_state() -> None:
    music_service = FakeMusicService(stream_ref="resolved://wave")
    music_service.station_batches["user:onyourwave"] = [
        (Track(id="w1", title="Wave 1", artists=("Artist",), duration_ms=1_000),)
    ]
    cache_repo = InMemoryLibraryCacheRepo()
    cache_repo.save_track_metadata(
        Track(id="w1", title="Liked Wave", artists=("Artist",), is_liked=True)
    )
    cache_repo.save_liked_track_ids(
        LikedTrackIds(user_id="user-1", revision=1, track_ids=frozenset({"w1"}))
    )
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        music_service=music_service,
        library_cache_repo=cache_repo,
    )

    snapshot = service.play_station("user:onyourwave")

    assert snapshot.current_item is not None
    assert snapshot.current_item.track.is_liked is True


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


def test_station_queue_persistence_is_bounded_around_active_item() -> None:
    state_repo = InMemoryPlaybackStateRepo()
    tracks = tuple(
        Track(id=f"w{index}", title=f"Wave {index}", artists=("Artist",), stream_ref=f"s://{index}")
        for index in range(80)
    )
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
        playback_state_repo=state_repo,
    )

    service.replace_queue(
        tracks,
        start_index=70,
        source_type="station",
        source_id="user:onyourwave",
    )

    assert state_repo.saved_queue is not None
    assert len(state_repo.saved_queue.queue) == 50
    assert state_repo.saved_queue.active_index == 40
    assert state_repo.saved_queue.queue[40].track.id == "w70"


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
