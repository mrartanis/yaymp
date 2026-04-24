from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.application.error_presenter import user_facing_error_message
from app.application.playback_service import PlaybackService, PlaybackSnapshot
from app.domain import Logger, Track
from app.domain.errors import DomainError


class PlaybackController(QObject):
    playback_changed = Signal(object)
    playback_failed = Signal(str)

    def __init__(self, *, playback_service: PlaybackService, logger: Logger) -> None:
        super().__init__()
        self._playback_service = playback_service
        self._logger = logger

    def initialize(self) -> None:
        self._emit_snapshot(self._playback_service.snapshot())

    def play(self) -> None:
        self._execute(self._playback_service.play)

    def pause(self) -> None:
        self._execute(self._playback_service.pause)

    def previous(self) -> None:
        self._execute(self._playback_service.previous)

    def next(self) -> None:
        self._execute(self._playback_service.next)

    def seek(self, position_ms: int) -> None:
        self._execute(lambda: self._playback_service.seek(position_ms))

    def set_volume(self, volume: int) -> None:
        self._execute(lambda: self._playback_service.set_volume(volume))

    def select_index(self, index: int) -> None:
        self._execute(lambda: self._playback_service.select_index(index))

    def play_track_by_id(self, track_id: str) -> None:
        self._execute(lambda: self._playback_service.play_track_by_id(track_id))

    def play_track(self, track: Track) -> None:
        self._execute(lambda: self._playback_service.play_track(track))

    def play_tracks(
        self,
        tracks: tuple[Track, ...],
        *,
        start_index: int,
        source_type: str,
        source_id: str,
    ) -> None:
        self._execute(
            lambda: self._playback_service.replace_queue(
                tracks,
                start_index=start_index,
                source_type=source_type,
                source_id=source_id,
            )
        )

    def append_tracks(
        self,
        tracks: tuple[Track, ...],
        *,
        source_type: str,
        source_id: str,
    ) -> None:
        self._execute(
            lambda: self._playback_service.append_queue(
                tracks,
                source_type=source_type,
                source_id=source_id,
            )
        )

    def play_tracks_next(
        self,
        tracks: tuple[Track, ...],
        *,
        source_type: str,
        source_id: str,
    ) -> None:
        self._execute(
            lambda: self._playback_service.insert_queue_next(
                tracks,
                source_type=source_type,
                source_id=source_id,
            )
        )

    def play_track_next(
        self,
        track: Track,
        *,
        source_type: str | None = "track",
        source_id: str | None = None,
    ) -> None:
        self._execute(
            lambda: self._playback_service.insert_queue_next(
                (track,),
                source_type=source_type,
                source_id=source_id or track.id,
            )
        )

    def play_station(self, station_id: str) -> None:
        self._execute(lambda: self._playback_service.play_station(station_id))

    def clear_queue(self) -> None:
        self._execute(self._playback_service.clear_queue)

    def move_queue_item_next(self, index: int) -> None:
        self._execute(lambda: self._playback_service.move_queue_item_next(index))

    def remove_queue_index(self, index: int) -> None:
        self._execute(lambda: self._playback_service.remove_queue_index(index))

    def refresh(self) -> None:
        self._execute(self._playback_service.refresh)

    def _execute(self, operation) -> None:
        try:
            self._emit_snapshot(operation())
        except DomainError as exc:
            self._logger.warning("Playback operation failed: %s", exc)
            self.playback_failed.emit(user_facing_error_message(exc))

    def _emit_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        self.playback_changed.emit(snapshot)
