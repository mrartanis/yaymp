from dataclasses import replace

from app.application.playback_service import PlaybackSnapshot
from app.bootstrap.startup import build_startup_context
from app.domain import PlaybackState, QueueItem, Track
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
    assert context.main_window.isVisible()
    context.main_window._set_theme_preference("light")

    assert context.container.services.settings_service.load_theme_preference() == "light"
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
