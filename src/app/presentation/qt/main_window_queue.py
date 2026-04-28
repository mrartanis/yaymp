from __future__ import annotations

from random import Random

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.domain.playback import PlaybackStatus, QueueItem


class NowPlayingIndicator(QWidget):
    def __init__(
        self,
        color: str,
        *,
        animated: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self._rng = Random(id(self))
        self._levels = [0.5, 0.78, 0.6, 0.88]
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self._advance)
        self.setFixedSize(18, 14)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.set_animated(animated)

    def sizeHint(self) -> QSize:
        return QSize(18, 14)

    def set_animated(self, animated: bool) -> None:
        if animated:
            self._timer.start()
        else:
            self._timer.stop()

    def _advance(self) -> None:
        next_levels: list[float] = []
        for index, current in enumerate(self._levels):
            floor = 0.32 if index % 2 == 0 else 0.42
            ceiling = 0.96 if index in {1, 3} else 0.86
            target = self._rng.uniform(floor, ceiling)
            next_levels.append(current * 0.35 + target * 0.65)
        if self._rng.random() < 0.3:
            spike_index = self._rng.randrange(len(next_levels))
            next_levels[spike_index] = min(0.98, next_levels[spike_index] + 0.14)
        self._levels = next_levels
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        bar_width = 3
        gap = 1
        baseline = self.height() - 1
        min_height = 4
        drawable_height = self.height() - 2
        for index, factor in enumerate(self._levels):
            height = max(min_height, int(drawable_height * factor))
            x = index * (bar_width + gap) + 1
            y = baseline - height
            painter.drawRoundedRect(x, y, bar_width, height, 1.5, 1.5)


class MainWindowQueueMixin:
    def _render_queue(self, snapshot) -> None:
        queue_key = self._queue_key(snapshot.queue)
        active_index = snapshot.state.active_index
        playback_status = snapshot.state.status
        queue_changed = queue_key != self._rendered_queue_key
        active_changed = active_index != self._rendered_active_index
        status_changed = playback_status != self._rendered_playback_status
        if queue_changed:
            self._rebuild_queue_list(snapshot)
            self._rendered_queue_key = queue_key
        elif active_changed or status_changed:
            self._update_queue_active_row(active_index, playback_status)

        if active_changed and active_index is not None:
            active_item = self._queue_list.item(active_index)
            if active_item is not None:
                self._queue_list.scrollToItem(active_item)
        self._rendered_active_index = active_index
        self._rendered_playback_status = playback_status

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
                    snapshot.state.status,
                )
                widget_item = QListWidgetItem()
                widget_item.setSizeHint(row_widget.sizeHint())
                widget_item.setData(Qt.ItemDataRole.UserRole, item)
                self._queue_list.addItem(widget_item)
                self._queue_list.setItemWidget(widget_item, row_widget)
            if self._queue_selected_index is None:
                self._queue_list.setCurrentRow(-1)
                self._queue_list.clearSelection()
            self._update_queue_active_row(
                snapshot.state.active_index,
                snapshot.state.status,
            )
            self._relayout_queue_rows()
        finally:
            self._queue_list.blockSignals(False)

    def _update_queue_active_row(
        self,
        active_index: int | None,
        playback_status: PlaybackStatus,
    ) -> None:
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
                        playback_status,
                    ),
                )
            self._relayout_queue_rows()
        finally:
            self._queue_list.blockSignals(False)

    def _relayout_queue_rows(self) -> None:
        if getattr(self, "_queue_list", None) is None:
            return
        for index in range(self._queue_list.count()):
            widget_item = self._queue_list.item(index)
            row_widget = self._queue_list.itemWidget(widget_item)
            if row_widget is None:
                continue
            row_widget.updateGeometry()
            widget_item.setSizeHint(row_widget.sizeHint())
        self._queue_list.updateGeometries()
        self._queue_list.doItemsLayout()
        self._queue_list.viewport().update()

    def _queue_row_widget(
        self,
        item: QueueItem,
        is_active: bool,
        is_selected: bool,
        playback_status: PlaybackStatus,
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
        if is_active:
            indicator_color = (
                self._accent_text_color() if is_selected else self._accent_color
            )
            layout.addWidget(
                NowPlayingIndicator(
                    indicator_color,
                    animated=playback_status is PlaybackStatus.PLAYING,
                ),
                0,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )
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
