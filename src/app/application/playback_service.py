from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain import (
    Logger,
    PlaybackEngine,
    PlaybackState,
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

    def __init__(
        self,
        *,
        playback_engine: PlaybackEngine,
        logger: Logger,
        music_service: MusicService | None = None,
        randomizer: random.Random | None = None,
    ) -> None:
        self._playback_engine = playback_engine
        self._logger = logger
        self._music_service = music_service
        self._randomizer = randomizer or random.Random()
        self._queue: list[QueueItem] = []
        self._active_index: int | None = None
        self._repeat_mode = RepeatMode.OFF
        self._shuffle_enabled = False
        self._volume = 100
        self._play_order: list[int] = []
        self._play_order_position: int | None = None
        self._last_observed_status = PlaybackStatus.STOPPED

    def replace_queue(
        self,
        tracks: Sequence[Track],
        *,
        start_index: int = 0,
        source_type: str | None = None,
        source_id: str | None = None,
    ) -> PlaybackSnapshot:
        if not tracks:
            raise ValueError("Playback queue cannot be empty")
        if start_index < 0 or start_index >= len(tracks):
            raise IndexError("Playback start index is out of range")

        previous_queue = self._queue
        previous_index = self._active_index
        previous_order = self._play_order
        previous_order_position = self._play_order_position

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
            return self.play()
        except Exception:
            self._queue = previous_queue
            self._active_index = previous_index
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
        self._playback_engine.play()
        self._logger.info("Playback started for index %s", self._active_index)
        return self.snapshot()

    def pause(self) -> PlaybackSnapshot:
        self._playback_engine.pause()
        self._logger.info("Playback paused")
        return self.snapshot()

    def toggle_play_pause(self) -> PlaybackSnapshot:
        state = self.snapshot().state
        if state.status is PlaybackStatus.PLAYING:
            return self.pause()
        return self.play()

    def stop(self) -> PlaybackSnapshot:
        self._playback_engine.stop()
        self._logger.info("Playback stopped")
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
        track = self._music_service.get_track(track_id)
        return self.play_track(track, source_type="track", source_id=track_id)

    def play_station(self, station_id: str) -> PlaybackSnapshot:
        if self._music_service is None:
            raise PlaybackBackendError("Music service is not configured")
        tracks = self._music_service.get_station_tracks(
            station_id,
            limit=self._STATION_QUEUE_BATCH_SIZE,
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
        return self.play()

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
        return self.play()

    def seek(self, position_ms: int) -> PlaybackSnapshot:
        self._playback_engine.seek(position_ms)
        return self.snapshot()

    def refresh(self) -> PlaybackSnapshot:
        engine_state = self._playback_engine.get_state()
        if self._should_auto_advance(engine_state):
            return self.next()
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
            raise IndexError("Queue index is out of range")
        self._activate_index(index)
        return self.play()

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

    def _activate_index(self, index: int) -> None:
        current_item = self._queue[index]
        prepared_item = self._prepare_queue_item(current_item)
        self._queue[index] = prepared_item
        stream_ref = prepared_item.track.stream_ref or ""
        self._playback_engine.load(prepared_item.track, stream_ref=stream_ref)
        self._playback_engine.set_volume(self._volume)
        self._active_index = index
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
        self._activate_index(self._active_index if self._active_index is not None else 0)

    def _compose_state(self, engine_state: PlaybackState) -> PlaybackState:
        return PlaybackState(
            status=engine_state.status,
            active_index=self._active_index,
            position_ms=engine_state.position_ms,
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

        fetched_tracks = self._music_service.get_station_tracks(
            station_id,
            limit=self._STATION_QUEUE_BATCH_SIZE,
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
            self._rebuild_play_order(anchor_index=self._active_index)
