from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QMouseEvent, QResizeEvent, QShowEvent


class MainWindowWindowingMixin:
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._fit_track_text_labels()
        update_responsive_layout = getattr(self, "_update_responsive_layout", None)
        if callable(update_responsive_layout):
            update_responsive_layout()
        if self._auth_flow_checked:
            return
        self._auth_flow_checked = True
        QTimer.singleShot(0, self._maybe_start_auth_flow)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_track_text_labels()
        update_responsive_layout = getattr(self, "_update_responsive_layout", None)
        if callable(update_responsive_layout):
            update_responsive_layout()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._system_media.shutdown()
        super().closeEvent(event)

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if self._handle_frame_resize_event(watched, event):
            return True
        auth_label = getattr(self, "_auth_label", None)
        title_bar = getattr(self, "_title_bar", None)
        title_drag_handle = getattr(self, "_title_drag_handle", None)
        settings_popup = getattr(self, "_settings_popup", None)
        volume_button = getattr(self, "_volume_button", None)
        volume_popup = getattr(self, "_volume_popup", None)
        player_panel_frame = getattr(self, "_player_panel_frame", None)
        track_metadata_zone = getattr(self, "_track_metadata_zone", None)
        artwork_label = getattr(self, "_artwork_label", None)
        track_title_label = getattr(self, "_track_title_label", None)
        track_meta_label = getattr(self, "_track_meta_label", None)
        track_album_label = getattr(self, "_track_album_label", None)
        if watched is auth_label:
            if event.type() == QEvent.Type.MouseButtonPress:
                if settings_popup is not None and settings_popup.isVisible():
                    settings_popup.hide()
                else:
                    self._show_settings_popup()
                return True
            return False
        if watched in {title_bar, title_drag_handle}:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._toggle_maximized()
                return True
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = self._as_mouse_event(event)
                if (
                    mouse_event is not None
                    and mouse_event.button() == Qt.MouseButton.LeftButton
                    and not self.isMaximized()
                ):
                    self._start_system_move()
                    return True
            return False
        if watched in {
            player_panel_frame,
            track_metadata_zone,
            artwork_label,
            track_title_label,
            track_meta_label,
            track_album_label,
        }:
            if event.type() == QEvent.Type.MouseButtonPress:
                mouse_event = self._as_mouse_event(event)
                if (
                    mouse_event is not None
                    and mouse_event.button() == Qt.MouseButton.LeftButton
                    and not self.isMaximized()
                ):
                    self._start_system_move()
                    return True
            return False
        if watched is settings_popup:
            if event.type() == QEvent.Type.Leave and settings_popup is not None:
                settings_popup.hide()
            return False
        if watched is volume_button:
            if event.type() == QEvent.Type.Enter:
                self._show_volume_popup()
            return False
        if watched is volume_popup:
            if event.type() == QEvent.Type.Leave:
                self._hide_volume_popup_if_idle()
            return False
        return super().eventFilter(watched, event)

    def _as_mouse_event(self, event: QEvent) -> QMouseEvent | None:
        return event if isinstance(event, QMouseEvent) else None
