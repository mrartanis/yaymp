from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout


class WindowTitleBar(QFrame):
    """Shared title bar for the main window and frameless dialogs."""

    double_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.controls_layout = QHBoxLayout(self)
        self.controls_layout.setContentsMargins(2, 0, 0, 0)
        self.controls_layout.setSpacing(6)
        self._press_global_position: QPointF | None = None
        self._press_window_position = QPoint()
        self._manual_drag = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self.window().isMaximized():
            super().mousePressEvent(event)
            return
        self._press_global_position = event.globalPosition()
        self._press_window_position = self.window().pos()
        self._manual_drag = False
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._press_global_position is None or not bool(
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition() - self._press_global_position
        if not self._manual_drag and delta.manhattanLength() < QApplication.startDragDistance():
            event.accept()
            return
        if not self._manual_drag:
            handle = self.window().windowHandle()
            if handle is not None and handle.startSystemMove():
                self._press_global_position = None
                event.accept()
                return
            self._manual_drag = True
        self.window().move(self._press_window_position + delta.toPoint())
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_global_position = None
        self._manual_drag = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_global_position = None
            self._manual_drag = False
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
