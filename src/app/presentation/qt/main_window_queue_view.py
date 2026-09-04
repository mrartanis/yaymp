from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QListView, QWidget

from app.domain.playback import PlaybackStatus
from app.presentation.qt.queue_list_model import QueueListModel as QueueListModel
from app.presentation.qt.queue_row_delegate import QueueRowDelegate as QueueRowDelegate
from app.presentation.qt.queue_waveform_overlay import QueueWaveformOverlay


class QueueListView(QListView):
    reorder_requested = Signal(int, int)

    def __init__(self, parent: QWidget | None = None, *, accent_provider=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._waveform_overlay = QueueWaveformOverlay(
            parent=self,
            accent_provider=accent_provider or (lambda: "#526ee8"),
        )

    def sync_waveform(self, active_row: int | None, playback_status: PlaybackStatus) -> None:
        self._waveform_overlay.sync_state(active_row, playback_status)

    def setModel(self, model) -> None:  # noqa: N802
        previous = self.model()
        if previous is not None:
            previous.dataChanged.disconnect(self._refresh_waveform_rows)
        super().setModel(model)
        if model is not None:
            model.dataChanged.connect(self._refresh_waveform_rows)

    def _refresh_waveform_rows(self, *_args: object) -> None:
        # An opaque child does not inherit the viewport's repaint requests.
        self._waveform_overlay.update()

    def refresh_waveform_visibility(self) -> None:
        self._waveform_overlay.refresh_position()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._waveform_overlay.refresh_position()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._waveform_overlay.refresh_position()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        event.acceptProposedAction()
        super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        source_row = self.currentIndex().row()
        if source_row < 0:
            event.ignore()
            return

        target_row = self._target_row_for_event(event)
        row_count = self.model().rowCount() if self.model() is not None else 0
        if row_count <= 0:
            event.ignore()
            return
        target_row = max(0, min(target_row, row_count))
        final_row = target_row - 1 if target_row > source_row else target_row
        if final_row == source_row:
            event.acceptProposedAction()
            return

        self.reorder_requested.emit(source_row, final_row)
        event.acceptProposedAction()

    def _target_row_for_event(self, event: QDropEvent) -> int:
        position = event.position().toPoint()
        index = self.indexAt(position)
        if not index.isValid():
            model = self.model()
            return model.rowCount() if model is not None else 0
        rect = self.visualRect(index)
        if position.y() > rect.center().y():
            return index.row() + 1
        return index.row()
