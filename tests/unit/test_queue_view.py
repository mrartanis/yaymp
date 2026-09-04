from dataclasses import replace

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from app.domain import Track
from app.domain.playback import PlaybackStatus, QueueItem
from app.presentation.qt.main_window_queue import MainWindowQueueMixin
from app.presentation.qt.main_window_queue_view import (
    QueueListModel,
    QueueListView,
    QueueRowDelegate,
)
from app.presentation.qt.queue_indicator import animated_levels, paint_indicator


def _queue(size: int) -> tuple[QueueItem, ...]:
    return tuple(QueueItem(Track(str(i), f"Track {i}", ("Artist",))) for i in range(size))


def test_fake_waveform_has_distinct_subpixel_frames_at_sixty_hz():
    frames = set()
    for frame in range(60):
        image = QImage(18, 14, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        levels = animated_levels(frame / 60)
        assert len(levels) == 6
        assert all(0 < level < 1 for level in levels)
        paint_indicator(painter, QRect(0, 0, 18, 14), QColor("#526ee8"), levels)
        painter.end()
        frames.add(bytes(image.constBits()))
    assert len(frames) >= 55


def test_metadata_updates_preserve_selection_without_reset(qtbot):
    view = QueueListView()
    qtbot.addWidget(view)
    model = QueueListModel(view)
    view.setModel(model)
    items = _queue(3)
    model.set_queue(items)
    view.setCurrentIndex(model.index(1, 0))
    resets = []
    changes = []
    model.modelReset.connect(lambda: resets.append(True))
    model.dataChanged.connect(lambda start, end, roles: changes.append(start.row()))

    updated = replace(items[1], track=replace(
        items[1].track, artwork_ref="cover", duration_ms=1234, is_liked=True
    ))
    queue = (items[0], updated, items[2])
    model.set_queue(queue)
    model.set_queue(queue)

    assert resets == []
    assert changes == [1]
    assert view.currentIndex().row() == 1
    assert model.queue_item_at(1) == updated
    mixin = MainWindowQueueMixin()
    assert mixin._queue_key(items) != mixin._queue_key(queue)


def test_unchanged_playback_does_not_invalidate_rows(qapp):
    model = QueueListModel()
    model.set_queue(_queue(4))
    model.set_active_state(1, PlaybackStatus.PLAYING)
    model.set_selected_index(2)
    changes = []
    model.dataChanged.connect(lambda start, end, roles: changes.append(start.row()))
    for _ in range(100):
        model.set_active_state(1, PlaybackStatus.PLAYING)
        model.set_selected_index(2)
    assert changes == []
    model.set_active_state(3, PlaybackStatus.PAUSED)
    assert {1, 3}.issubset(changes)
    assert model.index(3, 0).data(model.PlaybackStatusRole) == PlaybackStatus.PAUSED


def test_animation_stops_when_hidden_or_scrolled_out(qtbot):
    view = QueueListView()
    qtbot.addWidget(view)
    model = QueueListModel(view)
    model.set_queue(_queue(100))
    view.setModel(model)
    view.setItemDelegate(QueueRowDelegate(
        parent=view, thumb_provider=lambda *_: None, thumb_requester=lambda *_: None,
        format_ms=lambda _: "0:00", accent_provider=lambda: "#526ee8",
        accent_text_provider=lambda: "#ffffff", theme_provider=lambda: "dark",
        corner_style_provider=lambda: "rounded",
    ))
    view.resize(400, 200)
    view.show()
    qtbot.waitUntil(view.isVisible)
    view.sync_waveform(0, PlaybackStatus.PLAYING)
    overlay = view._waveform_overlay
    assert overlay._timer.isActive()
    view.scrollTo(model.index(99, 0))
    assert not overlay.isVisible()
    assert not overlay._timer.isActive()
    view.scrollTo(model.index(0, 0))
    assert overlay._timer.isActive()
    view.hide()
    assert not overlay._timer.isActive()
    view.show()
    assert overlay._timer.isActive()
    view.sync_waveform(0, PlaybackStatus.PAUSED)
    assert not overlay._timer.isActive()
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
