from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt
from PySide6.QtWidgets import QWidget

from app.domain.playback import PlaybackStatus, QueueItem


class QueueListModel(QAbstractListModel):
    """Queue rows with targeted notifications for metadata and playback changes."""

    QueueItemRole = Qt.ItemDataRole.UserRole + 1
    ActiveRole = Qt.ItemDataRole.UserRole + 2
    SelectedRole = Qt.ItemDataRole.UserRole + 3
    PlaybackStatusRole = Qt.ItemDataRole.UserRole + 4

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: tuple[QueueItem, ...] = ()
        self._active_index: int | None = None
        self._selected_index: int | None = None
        self._playback_status = PlaybackStatus.STOPPED

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object | None:
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == self.QueueItemRole:
            return item
        if role == self.ActiveRole:
            return index.row() == self._active_index
        if role == self.SelectedRole:
            return index.row() == self._selected_index
        if role == self.PlaybackStatusRole:
            return self._playback_status
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base_flags = super().flags(index)
        if not index.isValid():
            return base_flags | Qt.ItemFlag.ItemIsDropEnabled
        return (
            base_flags
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

    def set_queue(self, items: tuple[QueueItem, ...]) -> None:
        if items == self._items:
            return
        if len(items) == len(self._items) and all(
            new.track.id == old.track.id for new, old in zip(items, self._items, strict=True)
        ):
            previous = self._items
            self._items = items
            for row, (old, new) in enumerate(zip(previous, items, strict=True)):
                if old != new:
                    index = self.index(row, 0)
                    self.dataChanged.emit(index, index, [self.QueueItemRole])
            return
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def set_active_state(
        self,
        active_index: int | None,
        playback_status: PlaybackStatus,
    ) -> None:
        previous_active = self._active_index
        previous_status = self._playback_status
        if previous_active == active_index and previous_status == playback_status:
            return
        self._active_index = active_index
        self._playback_status = playback_status
        self._emit_row_updates(
            previous_active,
            active_index,
            include_active=(
                previous_active != active_index
                or previous_status != playback_status
            ),
        )

    def set_selected_index(self, selected_index: int | None) -> None:
        previous_selected = self._selected_index
        if previous_selected == selected_index:
            return
        self._selected_index = selected_index
        self._emit_row_updates(
            previous_selected,
            selected_index,
            include_active=False,
        )

    def queue_item_at(self, row: int) -> QueueItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def replace_queue_item(self, row: int, item: QueueItem) -> None:
        if not 0 <= row < len(self._items):
            return
        items = list(self._items)
        items[row] = item
        self._items = tuple(items)
        model_index = self.index(row, 0)
        self.dataChanged.emit(
            model_index,
            model_index,
            [
                self.QueueItemRole,
                self.ActiveRole,
                self.SelectedRole,
                self.PlaybackStatusRole,
            ],
        )

    def active_index(self) -> int | None:
        return self._active_index

    def selected_index(self) -> int | None:
        return self._selected_index

    def _emit_row_updates(
        self,
        previous_row: int | None,
        current_row: int | None,
        *,
        include_active: bool,
    ) -> None:
        rows = {
            row for row in (previous_row, current_row, self._active_index, self._selected_index)
            if row is not None and 0 <= row < len(self._items)
        }
        roles = [self.QueueItemRole, self.SelectedRole]
        if include_active:
            roles.extend([self.ActiveRole, self.PlaybackStatusRole])
        for row in rows:
            model_index = self.index(row, 0)
            self.dataChanged.emit(model_index, model_index, roles)
