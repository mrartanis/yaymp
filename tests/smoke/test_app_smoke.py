from dataclasses import replace
from datetime import UTC, datetime

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QMenu

from app.application.playback_service import PlaybackSnapshot
from app.bootstrap.startup import build_startup_context
from app.domain import PlaybackState, PlaybackStatus, QueueItem, Track, TrackAiUsage
from app.presentation.qt.dialog_chrome import WindowTitleBar


def test_main_window_can_be_constructed(qtbot, qapp, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("YAYMP_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("YAYMP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("YAYMP_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("YAYMP_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("YAYMP_PLAYBACK_BACKEND", "fake")

    context = build_startup_context(argv=["yaymp-test"], existing_qt_app=qapp)

    qtbot.addWidget(context.main_window)
    context.main_window.show()

    assert context.main_window.windowTitle() == "YAYMP"
    assert isinstance(context.main_window._title_bar, WindowTitleBar)
    assert context.container.config.settings_file.name == "settings.json"
    assert context.container.services.settings_service.load_volume() == 100
    assert (
        context.container.services.settings_service.load_ai_content_reduction_enabled() is False
    )
    assert context.container.services.music_service.get_ai_content_reduction_enabled() is False
    assert context.main_window._ai_content_reduction_buttons[False].isChecked()
    assert context.main_window.isVisible()
    context.main_window._set_language_preference("en")
    assert context.container.services.music_service.get_language() == "en"
    context.main_window._set_theme_preference("light")
    context.main_window._music_metadata_controller._apply_saved_account_setting(True)

    assert context.container.services.settings_service.load_theme_preference() == "light"
    assert context.container.services.settings_service.load_ai_content_reduction_enabled() is True
    assert context.container.services.music_service.get_ai_content_reduction_enabled() is True
    assert context.main_window._ai_content_reduction_buttons[True].isChecked()
    assert "#f5f7fb" in context.main_window.styleSheet()

    window = context.main_window
    fits = []
    original_fit = window._fit_track_text_labels

    def count_fit():
        fits.append(True)
        original_fit()

    monkeypatch.setattr(window, "_fit_track_text_labels", count_fit)
    track = Track("test", "First title", ("Artist",), duration_ms=60000)
    item = QueueItem(track)
    snapshot = PlaybackSnapshot((item,), PlaybackState(active_index=0), item)
    window._render_snapshot(snapshot)
    window._render_snapshot(replace(snapshot, state=replace(snapshot.state, position_ms=1000)))
    assert len(fits) == 1
    assert window._seek_slider.value() == 1000

    window._render_track_liked(replace(track, is_liked=True))
    updated_item = replace(item, track=replace(track, title="Updated title"))
    window._render_snapshot(replace(snapshot, queue=(updated_item,), current_item=updated_item))
    assert window._track_title_label.text() == "Updated title"
    assert window._queue_model.queue_item_at(0).track.is_liked

    ai_track = replace(
        track,
        version="Remastered",
        ai_usage=TrackAiUsage.POSSIBLE,
        credits_raw_json=(
            '{"credits": [{"title": "AI use", "value": "Possible"}], '
            '"futureField": {"value": 1}}'
        ),
        credits_cached_at=datetime.now(tz=UTC),
    )
    ai_item = replace(item, track=ai_track)
    window._render_snapshot(replace(snapshot, queue=(ai_item,), current_item=ai_item))
    assert window._track_version_label.text() == "Remastered · AI"

    menu = QMenu(window)
    assert window._populate_track_menu(menu, track)
    assert window._t("action.track_info") in {action.text() for action in menu.actions()}
    window._show_track_info(ai_track)
    assert window._track_info_dialog is not None
    assert window._track_info_dialog.windowTitle() == window._t("track_info.title")
    assert window._track_info_dialog._additional_raw_fields(ai_track.credits_raw_json) == (
        ("futureField.value", "1"),
    )
    window._track_info_dialog.close()


def test_position_poll_does_not_repaint_transport(qtbot, qapp, tmp_path, monkeypatch):
    for name in ("CONFIG", "DATA", "CACHE", "LOG"):
        monkeypatch.setenv(f"YAYMP_{name}_DIR", str(tmp_path / name.lower()))
    monkeypatch.setenv("YAYMP_PLAYBACK_BACKEND", "fake")
    context = build_startup_context(argv=["yaymp-test"], existing_qt_app=qapp)
    window = context.main_window
    qtbot.addWidget(window)
    window._playback_poll_timer.stop()
    window.show()
    qtbot.wait(100)
    item = QueueItem(Track("123", "Title", ("Artist",), duration_ms=600_000))
    snapshot = PlaybackSnapshot(
        (item,), PlaybackState(status=PlaybackStatus.PAUSED, duration_ms=600_000), item
    )
    window._render_snapshot(snapshot)
    qtbot.wait(100)

    class PaintCounter(QObject):
        def __init__(self):
            super().__init__()
            self.count = 0

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint:
                self.count += 1
            return False

    counter = PaintCounter()
    for widget in (
        window._play_pause_button,
        window._transport_widget,
        window._hero_widget,
        window._hero_info_widget,
    ):
        widget.installEventFilter(counter)
    for pos in range(1000, 31_000, 1000):
        window._render_snapshot(replace(snapshot, state=replace(snapshot.state, position_ms=pos)))
        qapp.processEvents()
    assert counter.count == 0
    before = window._play_pause_button.icon().cacheKey()
    window._render_play_pause_button(PlaybackStatus.PLAYING)
    assert window._play_pause_button.icon().cacheKey() != before
    assert window._play_pause_button.property("playback_status") == "playing"
    monkeypatch.setattr(window, "_t", lambda key: "Localized pause")
    window._render_play_pause_button(PlaybackStatus.PLAYING)
    assert window._play_pause_button.toolTip() == "Localized pause"
    before = window._play_pause_button.icon().cacheKey()
    monkeypatch.setattr(window, "_accent_text_color", lambda: "#123456")
    window._render_play_pause_button(PlaybackStatus.PLAYING)
    assert window._play_pause_button.icon().cacheKey() != before
