from __future__ import annotations

from PySide6.QtCore import QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget

from app.domain import Track
from app.domain.playback import PlaybackStatus, QueueItem
from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.main_window_styles import _palette_for_theme
from app.presentation.qt.preference_markers import (
    preference_marker_icon_name,
    preference_marker_kind,
)
from app.presentation.qt.queue_indicator import normalize_playback_status, paint_indicator
from app.presentation.qt.queue_list_model import QueueListModel


class QueueRowDelegate(QStyledItemDelegate):
    _ROW_HEIGHT = 48
    _THUMB_SIZE = 38
    _ROW_INSET_X = 2
    _ROW_INSET_Y = 1
    _TEXT_GAP = 8
    _DURATION_WIDTH = 58
    _INDICATOR_WIDTH = 18
    _INDICATOR_GAP = 8
    _PREFERENCE_ICON_SIZE = 16
    _PREFERENCE_ICON_GAP = 8

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
        thumb_provider,
        thumb_requester,
        format_ms,
        accent_provider,
        accent_text_provider,
        theme_provider,
        corner_style_provider,
    ) -> None:
        super().__init__(parent)
        self._thumb_provider = thumb_provider
        self._thumb_requester = thumb_requester
        self._format_ms = format_ms
        self._accent_provider = accent_provider
        self._accent_text_provider = accent_text_provider
        self._theme_provider = theme_provider
        self._corner_style_provider = corner_style_provider

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QSize:
        del option, index
        return QSize(0, self._ROW_HEIGHT)

    def sync_animation(
        self,
        active_row: int | None,
        playback_status: PlaybackStatus,
    ) -> None:
        del active_row, playback_status

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        queue_item = index.data(QueueListModel.QueueItemRole)
        if not isinstance(queue_item, QueueItem):
            return
        is_active = bool(index.data(QueueListModel.ActiveRole))
        is_selected = bool(index.data(QueueListModel.SelectedRole))
        playback_status = normalize_playback_status(
            index.data(QueueListModel.PlaybackStatusRole)
        )

        palette = _palette_for_theme(self._theme_provider())
        accent = QColor(self._accent_provider())
        accent_text = QColor(self._accent_text_provider())
        row_radius = 8 if self._corner_style_provider() == "rounded" else 0
        active_row_bg = QColor(accent)
        active_row_bg.setAlphaF(0.18 if self._theme_provider() == "light" else 0.22)
        transparent = QColor(0, 0, 0, 0)
        if is_selected:
            background = accent
            title_color = accent_text
            secondary_color = accent_text
            duration_color = accent_text
            indicator_color = accent_text
        elif is_active:
            background = active_row_bg
            title_color = QColor(palette.text_title)
            secondary_color = QColor(palette.text_secondary)
            duration_color = QColor(palette.text_primary)
            indicator_color = accent
        else:
            background = transparent
            title_color = QColor(palette.text_title)
            secondary_color = QColor(palette.text_secondary)
            duration_color = QColor(palette.text_primary)
            indicator_color = accent

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        row_rect = option.rect.adjusted(
            self._ROW_INSET_X,
            self._ROW_INSET_Y,
            -self._ROW_INSET_X,
            -self._ROW_INSET_Y,
        )
        painter.drawRoundedRect(row_rect, row_radius, row_radius)

        content_rect = row_rect.adjusted(6, 5, -6, -5)
        thumb_rect = QRect(
            content_rect.left(),
            content_rect.top(),
            self._THUMB_SIZE,
            self._THUMB_SIZE,
        )
        painter.setBrush(QColor(palette.art_thumb_bg))
        painter.drawRoundedRect(
            thumb_rect,
            6 if self._corner_style_provider() == "rounded" else 0,
            6 if self._corner_style_provider() == "rounded" else 0,
        )
        pixmap = self._thumb_provider(queue_item.track.artwork_ref, self._THUMB_SIZE)
        if pixmap is None and queue_item.track.artwork_ref:
            self._thumb_requester(
                queue_item.track.artwork_ref,
                self._THUMB_SIZE,
                index.row(),
            )
        if pixmap is not None:
            painter.drawPixmap(thumb_rect, pixmap)
        else:
            painter.setPen(QColor(palette.album_art_text))
            note_font = QFont(option.font)
            note_font.setPointSize(max(10, note_font.pointSize()))
            painter.setFont(note_font)
            painter.drawText(thumb_rect, Qt.AlignmentFlag.AlignCenter, "♪")

        duration_rect = QRect(
            content_rect.right() - self._DURATION_WIDTH + 1,
            content_rect.top(),
            self._DURATION_WIDTH,
            content_rect.height(),
        )
        marker_kind = preference_marker_kind(queue_item.track)
        preference_width = (
            self._PREFERENCE_ICON_SIZE + self._PREFERENCE_ICON_GAP if marker_kind else 0
        )
        indicator_width = self._INDICATOR_WIDTH + self._INDICATOR_GAP if is_active else 0
        text_left = thumb_rect.right() + 1 + self._TEXT_GAP
        text_right = duration_rect.left() - preference_width - indicator_width - self._TEXT_GAP
        text_rect = QRect(
            text_left,
            content_rect.top(),
            max(10, text_right - text_left),
            content_rect.height(),
        )
        title_rect = QRect(text_rect.left(), text_rect.top(), text_rect.width(), 18)
        subtitle_rect = QRect(
            text_rect.left(),
            text_rect.bottom() - 16,
            text_rect.width(),
            16,
        )
        title_font = QFont(option.font)
        title_font.setWeight(QFont.Weight.DemiBold)
        subtitle_font = QFont(option.font)
        subtitle_font.setPointSize(max(10, option.font.pointSize() - 1))
        duration_font = QFont("Menlo", max(10, option.font.pointSize() - 1))
        if duration_font.family() != "Menlo":
            duration_font = QFont(option.font)
            duration_font.setPointSize(max(10, option.font.pointSize() - 1))

        painter.setPen(title_color)
        painter.setFont(title_font)
        title_metrics = painter.fontMetrics()
        version = queue_item.track.version or ""
        version_font = QFont(option.font)
        version_font.setPointSize(max(9, option.font.pointSize() - 2))
        version_text = f" · {version}" if version else ""
        version_width = 0
        if version_text:
            painter.setFont(version_font)
            version_width = painter.fontMetrics().horizontalAdvance(version_text)
            painter.setFont(title_font)
        title_text = painter.fontMetrics().elidedText(
            queue_item.track.title,
            Qt.TextElideMode.ElideRight,
            max(10, title_rect.width() - version_width),
        )
        title_width = min(title_metrics.horizontalAdvance(title_text), title_rect.width())
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title_text,
        )
        if version_text and title_width < title_rect.width():
            version_rect = QRect(
                title_rect.left() + title_width,
                title_rect.top(),
                max(0, title_rect.width() - title_width),
                title_rect.height(),
            )
            painter.setPen(secondary_color)
            painter.setFont(version_font)
            painter.drawText(
                version_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                painter.fontMetrics().elidedText(
                    version_text,
                    Qt.TextElideMode.ElideRight,
                    version_rect.width(),
                ),
            )

        subtitle_parts = (", ".join(queue_item.track.artists), queue_item.track.album_title or "")
        subtitle_text = " · ".join(part for part in subtitle_parts if part)
        painter.setPen(secondary_color)
        painter.setFont(subtitle_font)
        subtitle_text = painter.fontMetrics().elidedText(
            subtitle_text,
            Qt.TextElideMode.ElideRight,
            subtitle_rect.width(),
        )
        painter.drawText(
            subtitle_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            subtitle_text,
        )

        painter.setPen(duration_color)
        painter.setFont(duration_font)
        painter.drawText(
            duration_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._format_ms(queue_item.track.duration_ms),
        )

        preference_rect: QRect | None = None
        if marker_kind is not None:
            preference_left = (
                duration_rect.left()
                - self._PREFERENCE_ICON_GAP
                - self._PREFERENCE_ICON_SIZE
            )
            if is_active:
                preference_left -= indicator_width
            preference_rect = QRect(
                preference_left,
                content_rect.center().y() - self._PREFERENCE_ICON_SIZE // 2,
                self._PREFERENCE_ICON_SIZE,
                self._PREFERENCE_ICON_SIZE,
            )
            self._paint_preference_marker(
                painter,
                preference_rect,
                queue_item.track,
                accent=accent,
                muted=QColor(palette.text_muted),
            )

        if is_active:
            indicator_rect = QRect(
                duration_rect.left() - self._INDICATOR_GAP - self._INDICATOR_WIDTH,
                content_rect.center().y() - 7,
                self._INDICATOR_WIDTH,
                14,
            )
            if playback_status != PlaybackStatus.PLAYING:
                paint_indicator(painter, indicator_rect, indicator_color)
        painter.restore()

    def _paint_preference_marker(
        self,
        painter: QPainter,
        rect: QRect,
        track: Track,
        *,
        accent: QColor,
        muted: QColor,
    ) -> None:
        marker_kind = preference_marker_kind(track)
        if marker_kind is None:
            return
        icon_name = preference_marker_icon_name(
            marker_kind,
            theme_mode=self._theme_provider(),
        )
        color = accent.name() if marker_kind == "liked" else muted.name()
        pixmap = create_icon(icon_name, color=color, size=self._PREFERENCE_ICON_SIZE).pixmap(
            self._PREFERENCE_ICON_SIZE,
            self._PREFERENCE_ICON_SIZE,
        )
        painter.drawPixmap(rect, pixmap)


    def update_row(self, row: int) -> None:
        self._update_row(row)

    def _update_row(self, row: int) -> None:
        parent = self.parent()
        if not isinstance(parent, QWidget):
            return
        view = parent
        if not hasattr(view, "model"):
            return
        model = view.model()
        if model is None:
            return
        index = model.index(row, 0)
        if not index.isValid():
            return
        rect = view.visualRect(index)
        if not rect.isValid():
            return
        view.viewport().update(rect)
