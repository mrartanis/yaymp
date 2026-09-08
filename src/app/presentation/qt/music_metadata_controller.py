from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from app.application.error_presenter import user_facing_error_message
from app.application.library_service import LibraryService
from app.application.settings_service import SettingsService
from app.domain import Logger, MusicService, Track
from app.domain.errors import DomainError
from app.presentation.qt.library_task_runner import LibraryTaskRunner


class MusicMetadataController(QObject):
    track_credits_ready = Signal(str, object)
    track_credits_failed = Signal(str, str)
    ai_setting_synced = Signal(bool)
    ai_setting_saved = Signal(bool)
    ai_setting_sync_failed = Signal(str)
    ai_setting_save_failed = Signal(str, bool)

    def __init__(
        self,
        *,
        music_service: MusicService,
        library_service: LibraryService,
        settings_service: SettingsService,
        task_runner: LibraryTaskRunner,
        logger: Logger,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._music_service = music_service
        self._library_service = library_service
        self._settings_service = settings_service
        self._task_runner = task_runner
        self._logger = logger
        self._task_handlers: dict[
            int, tuple[Callable[[object], None], Callable[[object], None]]
        ] = {}
        self._track_waiters: dict[str, set[str]] = {}
        self._track_tasks: dict[str, int] = {}
        task_runner.completed.connect(self._handle_completed)
        task_runner.failed.connect(self._handle_failed)

    def sync_account_setting(self) -> None:
        if self._music_service.get_auth_session() is None:
            return
        self._submit(
            self._music_service.load_account_ai_content_reduction_enabled,
            self._apply_synced_account_setting,
            self._fail_account_setting_sync,
        )

    def save_account_setting(self, enabled: bool) -> None:
        previous = self._music_service.get_ai_content_reduction_enabled()
        self._submit(
            lambda: self._music_service.save_account_ai_content_reduction_enabled(enabled),
            self._apply_saved_account_setting,
            lambda error: self.ai_setting_save_failed.emit(self._error_message(error), previous),
        )

    def request_track_credits(self, track: Track, *, context: str) -> None:
        waiters = self._track_waiters.setdefault(track.id, set())
        waiters.add(context)
        if track.id in self._track_tasks:
            return
        task_id = self._task_runner.submit(
            lambda selected_track=track: self._library_service.load_track_credits(selected_track)
        )
        if task_id is None:
            self._track_waiters.pop(track.id, None)
            return
        self._track_tasks[track.id] = task_id
        self._task_handlers[task_id] = (
            lambda result, track_id=track.id: self._finish_track(track_id, result),
            lambda error, track_id=track.id: self._fail_track(track_id, error),
        )

    def shutdown(self) -> None:
        for task_id in tuple(self._task_handlers):
            self._task_runner.cancel(task_id)
        self._task_handlers.clear()
        self._track_waiters.clear()
        self._track_tasks.clear()

    def _submit(
        self,
        operation: Callable[[], object],
        on_success: Callable[[object], None],
        on_failure: Callable[[object], None],
    ) -> None:
        task_id = self._task_runner.submit(operation)
        if task_id is not None:
            self._task_handlers[task_id] = (on_success, on_failure)

    def _apply_account_setting(self, result: object) -> bool:
        enabled = bool(result)
        self._music_service.set_ai_content_reduction_enabled(enabled)
        self._settings_service.save_ai_content_reduction_enabled(enabled)
        return enabled

    def _apply_synced_account_setting(self, result: object) -> None:
        self.ai_setting_synced.emit(self._apply_account_setting(result))

    def _apply_saved_account_setting(self, result: object) -> None:
        self.ai_setting_saved.emit(self._apply_account_setting(result))

    def _fail_account_setting_sync(self, error: object) -> None:
        self._logger.warning("AI content reduction setting sync failed: %s", error)
        self.ai_setting_sync_failed.emit(self._error_message(error))

    def _finish_track(self, track_id: str, result: object) -> None:
        self._track_tasks.pop(track_id, None)
        contexts = self._track_waiters.pop(track_id, set())
        if not isinstance(result, Track):
            return
        for context in contexts:
            self.track_credits_ready.emit(context, result)

    def _fail_track(self, track_id: str, error: object) -> None:
        self._track_tasks.pop(track_id, None)
        contexts = self._track_waiters.pop(track_id, set())
        message = self._error_message(error)
        for context in contexts:
            self.track_credits_failed.emit(context, message)

    def _handle_completed(self, task_id: int, result: object) -> None:
        handlers = self._task_handlers.pop(task_id, None)
        if handlers is not None:
            handlers[0](result)

    def _handle_failed(self, task_id: int, error: object) -> None:
        handlers = self._task_handlers.pop(task_id, None)
        if handlers is not None:
            handlers[1](error)

    def _error_message(self, error: object) -> str:
        if isinstance(error, DomainError):
            return user_facing_error_message(error)
        return str(error)
