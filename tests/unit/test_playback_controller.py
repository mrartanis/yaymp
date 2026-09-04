import logging
from threading import Event, get_ident

from PySide6.QtCore import QTimer

from app.application.playback_service import PlaybackSnapshot
from app.domain import PlaybackState
from app.presentation.qt.playback_controller import PlaybackController


def test_slow_playback_coalesces_volume_and_refresh_without_blocking_ui(qtbot):
    started = Event()
    release = Event()
    calls = []
    saved = []
    main_thread = get_ident()

    class Playback:
        def set_volume(self, volume):
            calls.append(("volume", volume))
            if volume == 1:
                started.set()
                assert release.wait(3)
            return PlaybackSnapshot((), PlaybackState(volume=volume), None)

        def refresh(self):
            calls.append(("refresh", None))
            return PlaybackSnapshot((), PlaybackState(), None)

        def shutdown(self):
            pass

    class Settings:
        def save_volume(self, volume):
            saved.append((volume, get_ident()))

    controller = PlaybackController(
        playback_service=Playback(), settings_service=Settings(),
        logger=logging.getLogger("test-playback-controller"),
    )
    try:
        controller.set_volume(1)
        qtbot.waitUntil(started.is_set)
        for volume in range(2, 101):
            controller.set_volume(volume)
            controller.refresh()
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        qtbot.waitUntil(lambda: bool(ticks))
        assert calls == [("volume", 1)]
        release.set()
        qtbot.waitUntil(lambda: len(saved) == 2 and not controller._volume_in_flight)
        assert [volume for volume, _ in saved] == [1, 100]
        assert all(thread != main_thread for _, thread in saved)
        assert calls.count(("refresh", None)) == 1
    finally:
        release.set()
        controller.shutdown()
