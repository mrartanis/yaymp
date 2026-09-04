from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QElapsedTimer, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPaintEvent, QShowEvent
from PySide6.QtWidgets import QWidget

from app.domain.playback import PlaybackStatus
from app.presentation.qt.queue_indicator import (
    IDLE_LEVELS,
    animated_levels,
    normalize_playback_status,
    paint_indicator,
)

if TYPE_CHECKING:
    from app.presentation.qt.main_window_queue_view import QueueListView


class QueueWaveformOverlay(QWidget):
    """Animate only the visible indicator, without repainting the queue rows."""

    _INDICATOR_WIDTH = 18
    _INDICATOR_GAP = 8
    _DURATION_WIDTH = 58
    _ROW_INSET_X = 2
    _ROW_INSET_Y = 1

    def __init__(self, *, parent: "QueueListView", accent_provider) -> None:
        super().__init__(parent.viewport())
        self._view = parent
        self._accent_provider = accent_provider
        self._clock = QElapsedTimer()
        self._clock.start()
        self._active_row: int | None = None
        self._playback_status = PlaybackStatus.STOPPED
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._advance_animation)
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def sync_state(self, active_row: int | None, playback_status: PlaybackStatus) -> None:
        self._active_row = active_row
        self._playback_status = normalize_playback_status(playback_status)
        if active_row is None:
            self._timer.stop()
            self.hide()
            return
        if self._playback_status != PlaybackStatus.PLAYING:
            self._timer.stop()
        self._sync_geometry()
        self.update()

    def refresh_position(self) -> None:
        if self._active_row is None:
            self.hide()
            return
        self._sync_geometry()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        if self._playback_status == PlaybackStatus.PLAYING:
            self._timer.start()
        super().showEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        levels = (
            animated_levels(self._clock.elapsed() / 1000.0)
            if self._playback_status == PlaybackStatus.PLAYING else IDLE_LEVELS
        )
        paint_indicator(
            painter, self.rect().adjusted(1, 1, -1, -1), QColor(self._accent_provider()), levels
        )

    def _advance_animation(self) -> None:
        self.update()

    def _sync_geometry(self) -> None:
        if self._active_row is None or self._view.window().isMinimized():
            self.hide()
            return
        model = self._view.model()
        if model is None:
            self.hide()
            return
        index = model.index(self._active_row, 0)
        if not index.isValid():
            self.hide()
            return
        row_rect = self._view.visualRect(index)
        if not row_rect.isValid() or not row_rect.intersects(self._view.viewport().rect()):
            self.hide()
            return
        content_rect = row_rect.adjusted(
            self._ROW_INSET_X + 6,
            self._ROW_INSET_Y + 5,
            -(self._ROW_INSET_X + 6),
            -(self._ROW_INSET_Y + 5),
        )
        duration_rect = QRect(
            content_rect.right() - self._DURATION_WIDTH + 1,
            content_rect.top(),
            self._DURATION_WIDTH,
            content_rect.height(),
        )
        rect = QRect(
            duration_rect.left() - self._INDICATOR_GAP - self._INDICATOR_WIDTH,
            content_rect.center().y() - 7,
            self._INDICATOR_WIDTH,
            14,
        )
        self.setGeometry(rect.adjusted(-1, -1, 1, 1))
        self.show()
        if (
            self.isVisible()
            and self._playback_status == PlaybackStatus.PLAYING
            and not self._timer.isActive()
        ):
            self._timer.start()
