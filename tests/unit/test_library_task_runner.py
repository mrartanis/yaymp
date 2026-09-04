from __future__ import annotations

import threading
import time

from PySide6.QtCore import QTimer

from app.presentation.qt.library_task_runner import LibraryTaskRunner


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


def test_runner_keeps_gui_event_loop_responsive(qtbot) -> None:
    runner = LibraryTaskRunner(logger=TestLogger())
    gui_thread_id = threading.get_ident()
    completed: list[tuple[int, int]] = []
    timer_fired: list[bool] = []
    runner.completed.connect(
        lambda _task_id, worker_thread_id: completed.append(
            (worker_thread_id, threading.get_ident())
        )
    )

    try:
        task_id = runner.submit(lambda: (time.sleep(0.12), threading.get_ident())[1])
        QTimer.singleShot(10, lambda: timer_fired.append(True))

        qtbot.waitUntil(lambda: bool(timer_fired), timeout=500)
        assert completed == []
        qtbot.waitUntil(lambda: bool(completed), timeout=1000)
    finally:
        runner.shutdown()

    assert task_id is not None
    assert completed[0][0] != gui_thread_id
    assert completed[0][1] == gui_thread_id


def test_runner_suppresses_cancelled_task_result(qtbot) -> None:
    runner = LibraryTaskRunner(logger=TestLogger())
    completed: list[int] = []
    runner.completed.connect(lambda task_id, _result: completed.append(task_id))

    try:
        task_id = runner.submit(lambda: (time.sleep(0.05), "done")[1])
        assert task_id is not None
        runner.cancel(task_id)
        qtbot.wait(120)
    finally:
        runner.shutdown()

    assert task_id not in completed
