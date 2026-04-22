from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from time import monotonic

from app.application.track_metadata import merge_cached_liked_state, merge_cached_liked_states
from app.domain import (
    LibraryCacheRepo,
    Logger,
    PlaybackEngine,
    PlaybackState,
    PlaybackStateRepo,
    PlaybackStatus,
    QueueItem,
    RepeatMode,
    Track,
)
from app.domain.errors import PlaybackBackendError, StreamResolveError
from app.domain.protocols import MusicService


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    queue: tuple[QueueItem, ...]
    state: PlaybackState
    current_item: QueueItem | None


class PlaybackService:
    _STATION_QUEUE_REFILL_THRESHOLD = 3
    _STATION_QUEUE_BATCH_SIZE = 10
    _STATION_QUEUE_RETAIN_BEFORE_ACTIVE = 10
    _STATION_QUEUE_MAX_LENGTH = 60
    _STATION_QUEUE_PERSIST_LENGTH = 50
    _POSITION_PERSIST_INTERVAL_SECONDS = 5.0

    def __init__(
        self,
        *,
        playback_engine: PlaybackEngine,
        logger: Logger,
        music_service: MusicService | None = None,
        library_cache_repo: LibraryCacheRepo | None = None,
        playback_state_repo: PlaybackStateRepo | None = None,
        randomizer: random.Random | None = None,
    ) -> None:
        self._playback_engine = playback_engine
        self._logger = logger
        self._music_service = music_service
        self._library_cache_repo = library_cache_repo
        self._playback_state_repo = playback_state_repo
        self._randomizer = randomizer or random.Random()
        self._queue: list[QueueItem] = []
        self._active_index: int | None = None
        self._active_item_loaded = False
        self._restored_position_ms = 0
        self._pending_restore_seek_ms = 0
        self._repeat_mode = RepeatMode.OFF
        self._shuffle_enabled = False
        self._volume = 100
        self._play_order: list[int] = []
        self._play_order_position: int | None = None
        self._last_observed_status = PlaybackStatus.STOPPED
        self._last_position_persisted_at = 0.0
        self._playback_engine.on_ready_for_seek(self._apply_pending_restore_seek)

    def replace_queue(
        self,
        tracks: Sequence[Track],
        *,
        start_index: int = 0,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        if not tracks:
            raise PlaybackBackendError("Playback queue cannot be empty")
        if start_index < 0 or start_index >= len(tracks):
            raise PlaybackBackendError("Playback start index is out of range")

        previous_queue = self._queue
        previous_index = self._active_index
        previous_loaded = self._active_item_loaded
        previous_order = self._play_order
        previous_order_position = self._play_order_position

        tracks = merge_cached_liked_states(
            tuple(tracks),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._queue = [
            QueueItem(
                track=track,
                source_type=source_type,
                source_id=source_id,
                source_index=index,
            )
            for index, track in enumerate(tracks)
        ]
        self._rebuild_play_order(anchor_index=start_index)

        try:
            self._activate_index(start_index)
            snapshot = self.play()
            self._persist_playback_queue(position_ms=0)
            return snapshot
        except Exception:
            self._queue = previous_queue
            self._active_index = previous_index
            self._active_item_loaded = previous_loaded
            self._play_order = previous_order
            self._play_order_position = previous_order_position
            raise

    def append_queue(
        self,
        tracks: Sequence[Track],
        *,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        start_source_index = sum(
            1
            for item in self._queue
            if item.source_type == source_type and item.source_id == source_id
        )
        tracks = merge_cached_liked_states(
            tuple(tracks),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        for offset, track in enumerate(tracks):
            self._queue.append(
                QueueItem(
                    track=track,
                    source_type=source_type,
                    source_id=source_id,
                    source_index=start_source_index + offset,
                )
            )
        self._rebuild_play_order(anchor_index=self._active_index)
        self._logger.info("Appended %s tracks to queue", len(tracks))
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def restore_saved_queue(self) -> PlaybackSnapshot:
        if self._playback_state_repo is None:
            return self.snapshot()
        try:
            saved_queue = self._playback_state_repo.load_playback_queue()
        except Exception as exc:
            self._logger.warning("Failed to restore playback queue: %s", exc)
            self._clear_persisted_playback_queue()
            return self.snapshot()

        if saved_queue is None or not saved_queue.queue:
            return self.snapshot()

        self._queue = [
            QueueItem(
                track=merge_cached_liked_state(
                    item.track,
                    self._library_cache_repo,
                    user_id=self._current_user_id(),
                ),
                source_type=item.source_type,
                source_id=item.source_id,
                source_index=item.source_index,
            )
            for item in saved_queue.queue
        ]
        if saved_queue.active_index is None:
            self._active_index = 0
        else:
            self._active_index = max(0, min(len(self._queue) - 1, saved_queue.active_index))
        self._active_item_loaded = False
        self._restored_position_ms = saved_queue.position_ms
        self._rebuild_play_order(anchor_index=self._active_index)
        self._logger.info("Restored %s playback queue items", len(self._queue))
        return self.snapshot()

    def snapshot(self) -> PlaybackSnapshot:
        self._ensure_station_queue_capacity(min_remaining=self._STATION_QUEUE_REFILL_THRESHOLD)
        return self._build_snapshot(self._playback_engine.get_state())

    def current_item(self) -> QueueItem | None:
        if self._active_index is None:
            return None
        if self._active_index < 0 or self._active_index >= len(self._queue):
            return None
        return self._queue[self._active_index]

    def play(self) -> PlaybackSnapshot:
        if self.current_item() is None:
            raise PlaybackBackendError("No active queue item to play")
        if not self._active_item_loaded:
            self._pending_restore_seek_ms = self._restored_position_ms
            self._load_current_item()
        self._playback_engine.play()
        self._logger.info("Playback started for index %s", self._active_index)
        return self.snapshot()

    def pause(self) -> PlaybackSnapshot:
        self._playback_engine.pause()
        self._logger.info("Playback paused")
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def toggle_play_pause(self) -> PlaybackSnapshot:
        state = self.snapshot().state
        if state.status is PlaybackStatus.PLAYING:
            return self.pause()
        return self.play()

    def stop(self) -> PlaybackSnapshot:
        self._playback_engine.stop()
        self._logger.info("Playback stopped")
        self._persist_playback_queue(position_ms=0)
        return self.snapshot()

    def clear_queue(self) -> PlaybackSnapshot:
        self._playback_engine.stop()
        self._queue = []
        self._active_index = None
        self._active_item_loaded = False
        self._restored_position_ms = 0
        self._pending_restore_seek_ms = 0
        self._play_order = []
        self._play_order_position = None
        self._last_observed_status = PlaybackStatus.STOPPED
        self._clear_persisted_playback_queue()
        self._logger.info("Playback queue cleared")
        return self.snapshot()

    def play_track(
        self,
        track: Track,
        *,
        source_type: str | None = "track",
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        return self.replace_queue(
            (track,),
            start_index=0,
            source_type=source_type,
            source_id=source_id or track.id,
        )

    def play_track_by_id(self, track_id: str) -> PlaybackSnapshot:
        if self._music_service is None:
            raise PlaybackBackendError("Music service is not configured")
        track = merge_cached_liked_state(
            self._music_service.get_track(track_id),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        return self.play_track(track, source_type="track", source_id=track_id)

    def play_station(self, station_id: str) -> PlaybackSnapshot:
        if self._music_service is None:
            raise PlaybackBackendError("Music service is not configured")
        tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_station_tracks(
                    station_id,
                    limit=self._STATION_QUEUE_BATCH_SIZE,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        if not tracks:
            raise PlaybackBackendError(f"Station {station_id} returned no tracks")
        return self.replace_queue(
            tracks,
            start_index=0,
            source_type="station",
            source_id=station_id,
        )

    def next(self) -> PlaybackSnapshot:
        if self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if self._repeat_mode is RepeatMode.ONE:
            self._activate_index(self._active_index)
            return self.play()

        next_index = self._resolve_next_index()
        if next_index is None:
            self.stop()
            return self.snapshot()

        self._activate_index(next_index)
        snapshot = self.play()
        self._persist_playback_queue(position_ms=0)
        return snapshot

    def previous(self) -> PlaybackSnapshot:
        if self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if self._repeat_mode is RepeatMode.ONE:
            self.seek(0)
            self._activate_index(self._active_index)
            return self.play()

        current_state = self._playback_engine.get_state()
        if current_state.position_ms > 3_000:
            self.seek(0)
            return self.snapshot()

        previous_index = self._resolve_previous_index()
        self._activate_index(previous_index)
        snapshot = self.play()
        self._persist_playback_queue(position_ms=0)
        return snapshot

    def seek(self, position_ms: int) -> PlaybackSnapshot:
        self._playback_engine.seek(position_ms)
        self._persist_playback_queue(position_ms=self._current_position_ms())
        return self.snapshot()

    def refresh(self) -> PlaybackSnapshot:
        engine_state = self._playback_engine.get_state()
        if self._should_auto_advance(engine_state):
            return self.next()
        self._persist_playback_position_if_due(engine_state)
        return self._build_snapshot(engine_state)

    def set_volume(self, volume: int) -> PlaybackSnapshot:
        bounded_volume = max(0, min(100, volume))
        self._volume = bounded_volume
        self._playback_engine.set_volume(bounded_volume)
        return self.snapshot()

    def set_repeat_mode(self, repeat_mode: RepeatMode) -> PlaybackSnapshot:
        self._repeat_mode = repeat_mode
        return self.snapshot()

    def set_shuffle_enabled(self, enabled: bool) -> PlaybackSnapshot:
        self._shuffle_enabled = enabled
        self._rebuild_play_order(anchor_index=self._active_index)
        return self.snapshot()

    def select_index(self, index: int) -> PlaybackSnapshot:
        if index < 0 or index >= len(self._queue):
            raise PlaybackBackendError("Queue index is out of range")
        self._activate_index(index)
        snapshot = self.play()
        self._persist_playback_queue(position_ms=0)
        return snapshot

    def _resolve_next_index(self) -> int | None:
        if not self._queue or self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if self._play_order_position is None:
            self._rebuild_play_order(anchor_index=self._active_index)

        assert self._play_order_position is not None
        next_position = self._play_order_position + 1
        if next_position >= len(self._play_order):
            if self._repeat_mode is RepeatMode.ALL:
                next_position = 0
            else:
                return None
        self._play_order_position = next_position
        return self._play_order[next_position]

    def _resolve_previous_index(self) -> int:
        if not self._queue or self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        if self._play_order_position is None:
            self._rebuild_play_order(anchor_index=self._active_index)

        assert self._play_order_position is not None
        previous_position = self._play_order_position - 1
        if previous_position < 0:
            if self._repeat_mode is RepeatMode.ALL:
                previous_position = len(self._play_order) - 1
            else:
                previous_position = 0
        self._play_order_position = previous_position
        return self._play_order[previous_position]

    def _activate_index(self, index: int, *, preserve_restored_position: bool = False) -> None:
        current_item = self._queue[index]
        prepared_item = self._prepare_queue_item(current_item)
        self._queue[index] = prepared_item
        stream_ref = prepared_item.track.stream_ref or ""
        self._playback_engine.load(prepared_item.track, stream_ref=stream_ref)
        self._playback_engine.set_volume(self._volume)
        self._active_index = index
        self._active_item_loaded = True
        if not preserve_restored_position:
            self._restored_position_ms = 0
        self._sync_play_order_position(index)

    def _prepare_queue_item(self, item: QueueItem) -> QueueItem:
        stream_ref = item.track.stream_ref
        if not stream_ref:
            if self._music_service is None:
                raise StreamResolveError("Track has no stream reference")
            stream_ref = self._music_service.resolve_stream_ref(item.track)
        if not stream_ref:
            raise StreamResolveError("Track has no stream reference")
        return QueueItem(
            track=Track(
                id=item.track.id,
                title=item.track.title,
                artists=item.track.artists,
                album_title=item.track.album_title,
                album_year=item.track.album_year,
                duration_ms=item.track.duration_ms,
                stream_ref=stream_ref,
                artwork_ref=item.track.artwork_ref,
                available=item.track.available,
                is_liked=item.track.is_liked,
            ),
            source_type=item.source_type,
            source_id=item.source_id,
            source_index=item.source_index,
        )

    def _rebuild_play_order(self, *, anchor_index: int | None) -> None:
        self._play_order = list(range(len(self._queue)))
        if not self._play_order:
            self._play_order_position = None
            return

        if self._shuffle_enabled:
            self._randomizer.shuffle(self._play_order)
            if anchor_index is not None and anchor_index in self._play_order:
                self._play_order.remove(anchor_index)
                self._play_order.insert(0, anchor_index)
                self._play_order_position = 0
                return

        if anchor_index is None:
            self._play_order_position = 0
            return
        self._play_order_position = self._play_order.index(anchor_index)

    def _sync_play_order_position(self, index: int) -> None:
        if index not in self._play_order:
            self._rebuild_play_order(anchor_index=index)
            return
        self._play_order_position = self._play_order.index(index)

    def _load_current_item(self) -> None:
        current_item = self.current_item()
        if current_item is None:
            raise PlaybackBackendError("No current queue item")
        self._activate_index(
            self._active_index if self._active_index is not None else 0,
            preserve_restored_position=True,
        )

    def _compose_state(self, engine_state: PlaybackState) -> PlaybackState:
        position_ms = engine_state.position_ms
        if self.current_item() is not None and not self._active_item_loaded:
            position_ms = self._restored_position_ms
        return PlaybackState(
            status=engine_state.status,
            active_index=self._active_index,
            position_ms=position_ms,
            duration_ms=engine_state.duration_ms,
            volume=engine_state.volume,
            shuffle_enabled=self._shuffle_enabled,
            repeat_mode=self._repeat_mode,
            audio_codec=engine_state.audio_codec,
            audio_bitrate=engine_state.audio_bitrate,
        )

    def _build_snapshot(self, engine_state: PlaybackState) -> PlaybackSnapshot:
        state = self._compose_state(engine_state)
        self._last_observed_status = state.status
        return PlaybackSnapshot(
            queue=tuple(self._queue),
            state=state,
            current_item=self.current_item(),
        )

    def _should_auto_advance(self, engine_state: PlaybackState) -> bool:
        return (
            engine_state.status is PlaybackStatus.STOPPED
            and self._last_observed_status is PlaybackStatus.PLAYING
            and self.current_item() is not None
        )

    def _ensure_station_queue_capacity(self, *, min_remaining: int) -> None:
        current_item = self.current_item()
        if current_item is None or current_item.source_type != "station":
            return
        if self._music_service is None or self._active_index is None:
            return

        remaining = len(self._queue) - self._active_index - 1
        if remaining >= min_remaining:
            return

        station_id = current_item.source_id
        if not station_id:
            return

        fetched_tracks = merge_cached_liked_states(
            tuple(
                self._music_service.get_station_tracks(
                    station_id,
                    limit=self._STATION_QUEUE_BATCH_SIZE,
                )
            ),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        if not fetched_tracks:
            return

        existing_ids = {item.track.id for item in self._queue}
        next_source_index = len(self._queue)
        appended = 0
        for track in fetched_tracks:
            if track.id in existing_ids:
                continue
            self._queue.append(
                QueueItem(
                    track=track,
                    source_type="station",
                    source_id=station_id,
                    source_index=next_source_index,
                )
            )
            existing_ids.add(track.id)
            next_source_index += 1
            appended += 1

        if appended:
            self._logger.info("Appended %s station tracks for %s", appended, station_id)
            self._trim_station_queue()
            self._rebuild_play_order(anchor_index=self._active_index)
            self._persist_playback_queue(position_ms=self._current_position_ms())

    def _trim_station_queue(self) -> None:
        current_item = self.current_item()
        if current_item is None or current_item.source_type != "station":
            return
        if self._active_index is None or len(self._queue) <= self._STATION_QUEUE_MAX_LENGTH:
            return

        drop_count = max(
            len(self._queue) - self._STATION_QUEUE_MAX_LENGTH,
            self._active_index - self._STATION_QUEUE_RETAIN_BEFORE_ACTIVE,
        )
        drop_count = max(0, min(drop_count, self._active_index))
        if drop_count <= 0:
            return

        del self._queue[:drop_count]
        self._active_index -= drop_count

    def _persist_playback_position_if_due(self, engine_state: PlaybackState) -> None:
        if self.current_item() is None:
            return
        now = monotonic()
        if now - self._last_position_persisted_at < self._POSITION_PERSIST_INTERVAL_SECONDS:
            return
        self._persist_playback_queue(position_ms=engine_state.position_ms)

    def _apply_pending_restore_seek(self) -> None:
        if self._pending_restore_seek_ms <= 0:
            return
        position_ms = self._pending_restore_seek_ms
        try:
            self._playback_engine.seek(position_ms)
        except PlaybackBackendError as exc:
            self._pending_restore_seek_ms = 0
            self._restored_position_ms = 0
            self._logger.warning("Failed to restore playback position: %s", exc)
            return

        self._pending_restore_seek_ms = 0
        self._restored_position_ms = 0
        self._persist_playback_queue(position_ms=position_ms)

    def _persist_playback_queue(self, *, position_ms: int | None = None) -> None:
        if self._playback_state_repo is None:
            return
        queue, active_index = self._queue_for_persistence()
        if position_ms is None:
            position_ms = self._current_position_ms()
        try:
            self._playback_state_repo.save_playback_queue(
                queue,
                active_index=active_index,
                position_ms=position_ms if queue else 0,
            )
            self._last_position_persisted_at = monotonic()
        except Exception as exc:
            self._logger.warning("Failed to save playback queue: %s", exc)

    def _clear_persisted_playback_queue(self) -> None:
        if self._playback_state_repo is None:
            return
        try:
            self._playback_state_repo.clear_playback_queue()
        except Exception as exc:
            self._logger.warning("Failed to clear saved playback queue: %s", exc)

    def _queue_for_persistence(self) -> tuple[tuple[QueueItem, ...], int | None]:
        active_item = self.current_item()
        if active_item is not None and active_item.source_type == "demo":
            return (), None
        if (
            active_item is None
            or active_item.source_type != "station"
            or self._active_index is None
        ):
            return tuple(self._queue), self._active_index if self._queue else None

        start_index = max(0, self._active_index - self._STATION_QUEUE_RETAIN_BEFORE_ACTIVE)
        end_index = min(len(self._queue), start_index + self._STATION_QUEUE_PERSIST_LENGTH)
        if end_index - start_index < self._STATION_QUEUE_PERSIST_LENGTH:
            start_index = max(0, end_index - self._STATION_QUEUE_PERSIST_LENGTH)
        return tuple(self._queue[start_index:end_index]), self._active_index - start_index

    def _current_position_ms(self) -> int:
        if self.current_item() is not None and not self._active_item_loaded:
            return self._restored_position_ms
        return self._playback_engine.get_state().position_ms

    def _current_user_id(self) -> str | None:
        if self._music_service is None:
            return None
        session = self._music_service.get_auth_session()
        return session.user_id if session is not None else None
