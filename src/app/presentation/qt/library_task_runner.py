from __future__ import annotations

from collections.abc import Callable
from threading import Lock

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from app.domain import Logger
from app.domain.errors import DomainError


class _LibraryTaskWorker(QObject):
    completed = Signal(int, object)
    failed = Signal(int, object)
    settled = Signal(int)

    def __init__(self, *, is_cancelled: Callable[[int], bool], logger: Logger) -> None:
        super().__init__()
        self._is_cancelled = is_cancelled
        self._logger = logger

    @Slot(int, object)
    def execute(self, task_id: int, operation: Callable[[], object]) -> None:
        if self._is_cancelled(task_id):
            self.settled.emit(task_id)
            return
        try:
            result = operation()
        except DomainError as exc:
            self._logger.warning("Library background task failed: %s", exc)
            self.failed.emit(task_id, exc)
        except Exception as exc:  # pragma: no cover - defensive guard
            self._logger.exception("Unexpected library background task failure: %s", exc)
            self.failed.emit(task_id, exc)
        else:
            if not self._is_cancelled(task_id):
                self.completed.emit(task_id, result)
        finally:
            self.settled.emit(task_id)


class LibraryTaskRunner(QObject):
    """One controlled background lane for library API, cache, and serialization work."""

    completed = Signal(int, object)
    failed = Signal(int, object)
    _requested = Signal(int, object)

    def __init__(self, *, logger: Logger, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = Lock()
        self._next_task_id = 0
        self._cancelled: set[int] = set()
        self._shutdown_started = False
        self._thread = QThread(self)
        self._worker = _LibraryTaskWorker(is_cancelled=self._is_cancelled, logger=logger)
        self._worker.moveToThread(self._thread)
        self._requested.connect(self._worker.execute, Qt.ConnectionType.QueuedConnection)
        self._worker.completed.connect(self._complete)
        self._worker.failed.connect(self._fail)
        self._worker.settled.connect(self._settle)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def submit(self, operation: Callable[[], object]) -> int | None:
        with self._lock:
            if self._shutdown_started:
                return None
            self._next_task_id += 1
            task_id = self._next_task_id
        self._requested.emit(task_id, operation)
        return task_id

    def cancel(self, task_id: int | None) -> None:
        if task_id is None:
            return
        with self._lock:
            self._cancelled.add(task_id)

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True
        self._thread.quit()
        self._thread.wait(6000)

    def _is_cancelled(self, task_id: int) -> bool:
        with self._lock:
            return self._shutdown_started or task_id in self._cancelled

    @Slot(int, object)
    def _complete(self, task_id: int, result: object) -> None:
        if self._is_cancelled(task_id):
            return
        self.completed.emit(task_id, result)

    @Slot(int, object)
    def _fail(self, task_id: int, error: object) -> None:
        if self._is_cancelled(task_id):
            return
        self.failed.emit(task_id, error)

    @Slot(int)
    def _settle(self, task_id: int) -> None:
        with self._lock:
            self._cancelled.discard(task_id)
