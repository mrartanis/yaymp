from __future__ import annotations

from app.domain import NetworkError
from app.presentation.qt.library_task_runner import LibraryTaskRunner
from app.presentation.qt.library_warmup_controller import LibraryWarmupController


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


class FakeLibraryService:
    def __init__(self, *, fail_generated: bool = False) -> None:
        self.calls: list[object] = []
        self.fail_generated = fail_generated

    def load_liked_tracks(self, *, limit: int = 100):
        self.calls.append(("liked tracks", limit))
        return ()

    def load_user_playlists(self, *, force_refresh: bool = False):
        self.calls.append(("user playlists", force_refresh))
        return ()

    def load_generated_playlists(self, *, force_refresh: bool = False):
        self.calls.append(("generated playlists", force_refresh))
        if self.fail_generated:
            raise NetworkError("offline")
        return ()

    def load_liked_playlists(self, *, force_refresh: bool = False):
        self.calls.append(("liked playlists", force_refresh))
        return ()

    def load_liked_albums(self, *, force_refresh: bool = False):
        self.calls.append(("liked albums", force_refresh))
        return ()

    def load_liked_artists(self, *, force_refresh: bool = False):
        self.calls.append(("liked artists", force_refresh))
        return ()

    def refresh_disliked_track_index(self):
        self.calls.append("disliked tracks")

    def refresh_disliked_artist_snapshot(self):
        self.calls.append("disliked artists")


def test_warmup_refreshes_all_snapshots_and_continues_after_failure(qtbot) -> None:
    logger = TestLogger()
    runner = LibraryTaskRunner(logger=logger)
    service = FakeLibraryService(fail_generated=True)
    controller = LibraryWarmupController(
        library_service=service,  # type: ignore[arg-type]
        task_runner=runner,
        logger=logger,
    )
    finished: list[bool] = []
    controller.finished.connect(lambda: finished.append(True))

    try:
        controller.start()
        qtbot.waitUntil(lambda: bool(finished), timeout=2000)
    finally:
        controller.shutdown()
        runner.shutdown()

    assert service.calls == [
        ("liked tracks", 500),
        ("user playlists", True),
        ("generated playlists", True),
        ("liked playlists", True),
        ("liked albums", True),
        ("liked artists", True),
        "disliked tracks",
        "disliked artists",
    ]


def test_foreground_task_can_run_between_warmup_jobs(qtbot) -> None:
    logger = TestLogger()
    runner = LibraryTaskRunner(logger=logger)
    service = FakeLibraryService()
    controller = LibraryWarmupController(
        library_service=service,  # type: ignore[arg-type]
        task_runner=runner,
        logger=logger,
    )
    foreground_submitted: list[bool] = []

    def submit_foreground(_task_id: int, _result: object) -> None:
        if foreground_submitted or service.calls != [("liked tracks", 500)]:
            return
        foreground_submitted.append(True)
        runner.submit(lambda: service.calls.append("foreground"))

    runner.completed.connect(submit_foreground)

    try:
        controller.start()
        qtbot.waitUntil(
            lambda: ("user playlists", True) in service.calls,
            timeout=1000,
        )
    finally:
        controller.shutdown()
        runner.shutdown()

    assert service.calls[:3] == [
        ("liked tracks", 500),
        "foreground",
        ("user playlists", True),
    ]
