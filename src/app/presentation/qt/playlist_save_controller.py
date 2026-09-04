from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.application.playlist_save_service import PlaylistSaveService
from app.domain import PlaylistSaveRequest
from app.presentation.qt.library_task_runner import LibraryTaskRunner


class PlaylistSaveController(QObject):
    destinations_loaded = Signal(object)
    save_succeeded = Signal(object)
    operation_failed = Signal(object)

    def __init__(
        self,
        *,
        service: PlaylistSaveService,
        task_runner: LibraryTaskRunner,
    ) -> None:
        super().__init__()
        self._service = service
        self._runner = task_runner
        self._task_ids: set[int] = set()
        self._load_task_id: int | None = None
        self._save_task_id: int | None = None
        self._runner.completed.connect(self._handle_completed)
        self._runner.failed.connect(self._handle_failed)

    @property
    def busy(self) -> bool:
        return self._load_task_id is not None or self._save_task_id is not None

    def load_destinations(self) -> None:
        if self.busy:
            return
        task_id = self._runner.submit(self._service.load_destinations)
        if task_id is not None:
            self._load_task_id = task_id
            self._task_ids.add(task_id)

    def save(self, request: PlaylistSaveRequest) -> None:
        if self._save_task_id is not None:
            return
        task_id = self._runner.submit(lambda: self._service.save(request))
        if task_id is not None:
            self._save_task_id = task_id
            self._task_ids.add(task_id)

    def cancel_load(self) -> None:
        if self._load_task_id is None:
            return
        self._runner.cancel(self._load_task_id)
        self._task_ids.discard(self._load_task_id)
        self._load_task_id = None

    def shutdown(self) -> None:
        for task_id in self._task_ids:
            self._runner.cancel(task_id)
        self._task_ids.clear()

    def _handle_completed(self, task_id: int, result: object) -> None:
        if task_id not in self._task_ids:
            return
        self._task_ids.discard(task_id)
        if task_id == self._load_task_id:
            self._load_task_id = None
            self.destinations_loaded.emit(result)
        elif task_id == self._save_task_id:
            self._save_task_id = None
            self.save_succeeded.emit(result)

    def _handle_failed(self, task_id: int, error: object) -> None:
        if task_id not in self._task_ids:
            return
        self._task_ids.discard(task_id)
        if task_id == self._load_task_id:
            self._load_task_id = None
        if task_id == self._save_task_id:
            self._save_task_id = None
        self.operation_failed.emit(error)

