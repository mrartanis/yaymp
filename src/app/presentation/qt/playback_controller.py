from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.application.playback_service import PlaybackService, PlaybackSnapshot
from app.domain import Logger
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

    def _execute(self, operation) -> None:
        try:
            self._emit_snapshot(operation())
        except DomainError as exc:
            self._logger.warning("Playback operation failed: %s", exc)
            self.playback_failed.emit(str(exc))

    def _emit_snapshot(self, snapshot: PlaybackSnapshot) -> None:
        self.playback_changed.emit(snapshot)
