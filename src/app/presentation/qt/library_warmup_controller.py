from __future__ import annotations

from collections import deque
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from app.application.library_service import LibraryService
from app.domain import Logger
from app.presentation.qt.library_task_runner import LibraryTaskRunner


class LibraryWarmupController(QObject):
    """Refreshes library snapshots without delaying startup or foreground navigation."""

    finished = Signal()
    _INTER_JOB_DELAY_MS = 50
    _LIKED_TRACK_WARMUP_LIMIT = 500

    def __init__(
        self,
        *,
        library_service: LibraryService,
        task_runner: LibraryTaskRunner,
        logger: Logger,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._library_service = library_service
        self._task_runner = task_runner
        self._logger = logger
        self._jobs: deque[tuple[str, Callable[[], object]]] = deque()
        self._task_id: int | None = None
        self._generation = 0
        self._task_runner.completed.connect(self._handle_completed)
        self._task_runner.failed.connect(self._handle_failed)

    @property
    def running(self) -> bool:
        return self._task_id is not None or bool(self._jobs)

    def start(self) -> None:
        if self.running:
            return
        self._generation += 1
        self._jobs.extend(
            (
                (
                    "liked tracks",
                    lambda: self._library_service.load_liked_tracks(
                        limit=self._LIKED_TRACK_WARMUP_LIMIT
                    ),
                ),
                (
                    "user playlists",
                    lambda: self._library_service.load_user_playlists(force_refresh=True),
                ),
                (
                    "generated playlists",
                    lambda: self._library_service.load_generated_playlists(force_refresh=True),
                ),
                (
                    "liked playlists",
                    lambda: self._library_service.load_liked_playlists(force_refresh=True),
                ),
                (
                    "liked albums",
                    lambda: self._library_service.load_liked_albums(force_refresh=True),
                ),
                (
                    "liked artists",
                    lambda: self._library_service.load_liked_artists(force_refresh=True),
                ),
                ("disliked tracks", self._library_service.refresh_disliked_track_index),
                ("disliked artists", self._library_service.refresh_disliked_artist_snapshot),
            )
        )
        self._submit_next(self._generation)

    def cancel(self) -> None:
        self._generation += 1
        self._jobs.clear()
        if self._task_id is not None:
            self._task_runner.cancel(self._task_id)
            self._task_id = None

    def shutdown(self) -> None:
        self.cancel()

    def _submit_next(self, generation: int) -> None:
        if generation != self._generation:
            return
        if not self._jobs:
            self.finished.emit()
            return
        label, operation = self._jobs.popleft()
        task_id = self._task_runner.submit(operation)
        if task_id is None:
            self._jobs.clear()
            return
        self._task_id = task_id
        self._logger.debug("Warming library cache: %s", label)

    @Slot(int, object)
    def _handle_completed(self, task_id: int, _result: object) -> None:
        if task_id != self._task_id:
            return
        self._task_id = None
        generation = self._generation
        QTimer.singleShot(
            self._INTER_JOB_DELAY_MS,
            lambda: self._submit_next(generation),
        )

    @Slot(int, object)
    def _handle_failed(self, task_id: int, error: object) -> None:
        if task_id != self._task_id:
            return
        self._logger.warning("Library cache warmup job failed: %s", error)
        self._task_id = None
        generation = self._generation
        QTimer.singleShot(
            self._INTER_JOB_DELAY_MS,
            lambda: self._submit_next(generation),
        )
