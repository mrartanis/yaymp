from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.domain.playback import QueueItem


class MainWindowQueueMixin:
    def _render_queue(self, snapshot) -> None:
        queue_key = self._queue_key(snapshot.queue)
        active_index = snapshot.state.active_index
        queue_changed = queue_key != self._rendered_queue_key
        active_changed = active_index != self._rendered_active_index
        if queue_changed:
            self._rebuild_queue_list(snapshot)
            self._rendered_queue_key = queue_key
        elif active_changed:
            self._update_queue_active_row(active_index)

        if active_changed and active_index is not None:
            active_item = self._queue_list.item(active_index)
            if active_item is not None:
                self._queue_list.scrollToItem(active_item)
        self._rendered_active_index = active_index

    def _rebuild_queue_list(self, snapshot) -> None:
        self._queue_list.blockSignals(True)
        try:
            self._queue_list.clear()
            if (
                self._queue_selected_index is not None
                and self._queue_selected_index >= len(snapshot.queue)
            ):
                self._queue_selected_index = None
            for index, item in enumerate(snapshot.queue):
                row_widget = self._queue_row_widget(
                    item,
                    self._queue_selected_index != snapshot.state.active_index
                    and snapshot.state.active_index == index,
                    self._queue_selected_index == index,
                )
                widget_item = QListWidgetItem()
                widget_item.setSizeHint(row_widget.sizeHint())
                widget_item.setData(Qt.ItemDataRole.UserRole, item)
                self._queue_list.addItem(widget_item)
                self._queue_list.setItemWidget(widget_item, row_widget)
            self._update_queue_active_row(snapshot.state.active_index)
        finally:
            self._queue_list.blockSignals(False)

    def _update_queue_active_row(self, active_index: int | None) -> None:
        self._queue_list.blockSignals(True)
        try:
            selected_index = self._queue_selected_index
            has_selected_row = (
                selected_index is not None
                and 0 <= selected_index < self._queue_list.count()
            )
            for index in range(self._queue_list.count()):
                widget_item = self._queue_list.item(index)
                queue_item = widget_item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(queue_item, QueueItem):
                    continue
                self._queue_list.setItemWidget(
                    widget_item,
                    self._queue_row_widget(
                        queue_item,
                        (
                            not has_selected_row
                            or self._queue_selected_index != active_index
                        )
                        and active_index == index,
                        has_selected_row and selected_index == index,
                    ),
                )
        finally:
            self._queue_list.blockSignals(False)

    def _queue_row_widget(
        self,
        item: QueueItem,
        is_active: bool,
        is_selected: bool,
    ) -> QWidget:
        row = QWidget()
        if is_selected:
            row.setObjectName("queue-row-selected")
        elif is_active:
            row.setObjectName("queue-row-active")
        else:
            row.setObjectName("queue-row")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(8)
        layout.addWidget(self._art_thumb_label(item.track.artwork_ref, size=38))
        text_container = QWidget()
        text_container.setObjectName("queue-text")
        text_container.setMinimumWidth(0)
        text_container.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        title = QLabel(item.track.title)
        title.setObjectName("queue-title")
        title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        subtitle_parts = (
            ", ".join(item.track.artists),
            item.track.album_title or "",
        )
        subtitle = QLabel(" · ".join(part for part in subtitle_parts if part))
        subtitle.setObjectName("queue-subtitle")
        subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        subtitle.setMinimumWidth(0)
        subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        layout.addWidget(text_container, 1)
        duration = QLabel(self._format_ms(item.track.duration_ms))
        duration.setObjectName("queue-duration")
        duration.setFixedWidth(58)
        duration.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(duration, 0, Qt.AlignmentFlag.AlignRight)
        return row

    def _queue_item_text(self, item: QueueItem) -> str:
        artists = ", ".join(item.track.artists)
        album = item.track.album_title or "Single"
        duration = self._format_ms(item.track.duration_ms)
        return f"{album} — {item.track.title}\n{artists} · {duration}"

    def _queue_key(self, queue: tuple[QueueItem, ...]) -> tuple[tuple[str, str, str, str], ...]:
        return tuple(
            (
                item.track.id,
                item.track.title,
                item.track.album_title or "",
                ",".join(item.track.artists),
            )
            for item in queue
        )
