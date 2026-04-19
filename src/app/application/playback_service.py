from __future__ import annotations

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


@dataclass(frozen=True, slots=True)
class PlaybackSnapshot:
    queue: tuple[QueueItem, ...]
    state: PlaybackState
    current_item: QueueItem | None


class PlaybackService:
    def __init__(self, *, playback_engine: PlaybackEngine, logger: Logger) -> None:
        self._playback_engine = playback_engine
        self._logger = logger
        self._queue: list[QueueItem] = []
        self._active_index: int | None = None
        self._repeat_mode = RepeatMode.OFF
        self._shuffle_enabled = False
        self._volume = 100

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

        self._queue = [
            QueueItem(
                track=track,
                source_type=source_type,
                source_id=source_id,
                source_index=index,
            )
            for index, track in enumerate(tracks)
        ]
        self._active_index = start_index
        self._load_current_item()
        self.play()
        return self.snapshot()

    def snapshot(self) -> PlaybackSnapshot:
        return PlaybackSnapshot(
            queue=tuple(self._queue),
            state=self._compose_state(self._playback_engine.get_state()),
            current_item=self.current_item(),
        )

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

    def next(self) -> PlaybackSnapshot:
        if self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        next_index = self._active_index + 1
        if next_index >= len(self._queue):
            if self._repeat_mode is RepeatMode.ALL:
                next_index = 0
            else:
                self.stop()
                return self.snapshot()

        self._active_index = next_index
        self._load_current_item()
        return self.play()

    def previous(self) -> PlaybackSnapshot:
        if self._active_index is None:
            raise PlaybackBackendError("No active queue item")

        current_state = self._playback_engine.get_state()
        if current_state.position_ms > 3_000:
            self.seek(0)
            return self.snapshot()

        previous_index = self._active_index - 1
        if previous_index < 0:
            if self._repeat_mode is RepeatMode.ALL:
                previous_index = len(self._queue) - 1
            else:
                previous_index = 0

        self._active_index = previous_index
        self._load_current_item()
        return self.play()

    def seek(self, position_ms: int) -> PlaybackSnapshot:
        self._playback_engine.seek(position_ms)
        return self.snapshot()

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
        return self.snapshot()

    def select_index(self, index: int) -> PlaybackSnapshot:
        if index < 0 or index >= len(self._queue):
            raise IndexError("Queue index is out of range")
        self._active_index = index
        self._load_current_item()
        return self.play()

    def _load_current_item(self) -> None:
        current_item = self.current_item()
        if current_item is None:
            raise PlaybackBackendError("No current queue item")
        if not current_item.track.stream_ref:
            raise StreamResolveError("Track has no stream reference")

        self._playback_engine.load(current_item.track, stream_ref=current_item.track.stream_ref)
        self._playback_engine.set_volume(self._volume)

    def _compose_state(self, engine_state: PlaybackState) -> PlaybackState:
        return PlaybackState(
            status=engine_state.status,
            active_index=self._active_index,
            position_ms=engine_state.position_ms,
            duration_ms=engine_state.duration_ms,
            volume=engine_state.volume,
            shuffle_enabled=self._shuffle_enabled,
            repeat_mode=self._repeat_mode,
        )
