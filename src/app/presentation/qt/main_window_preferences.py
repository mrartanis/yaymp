from __future__ import annotations

from os import environ

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.application.error_presenter import user_facing_error_message
from app.domain import AudioQuality, PlaybackStatus
from app.domain.errors import DomainError
from app.presentation.qt.auth_dialog import AuthDialog
from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.main_window_styles import build_main_window_stylesheet


class MainWindowPreferencesMixin:
    def _build_settings_popup(self) -> None:
        self._settings_popup = QFrame(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._settings_popup.setObjectName("settings-popup")
        self._settings_popup.installEventFilter(self)
        layout = QVBoxLayout(self._settings_popup)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        quality_label = QLabel("Quality")
        quality_label.setObjectName("settings-section")
        layout.addWidget(quality_label)
        quality_row = QHBoxLayout()
        quality_row.setContentsMargins(0, 0, 0, 0)
        quality_row.setSpacing(6)
        self._quality_buttons: dict[AudioQuality, QPushButton] = {}
        for quality in (AudioQuality.HQ, AudioQuality.SD, AudioQuality.LQ):
            button = QPushButton(quality.name)
            button.setObjectName("quality-option")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, selected=quality: self._set_audio_quality(selected)
            )
            self._quality_buttons[quality] = button
            quality_row.addWidget(button)
        layout.addLayout(quality_row)

        theme_label = QLabel("Theme")
        theme_label.setObjectName("settings-section")
        layout.addWidget(theme_label)
        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(0, 0, 0, 0)
        theme_row.setSpacing(6)
        for theme_id, title in (
            ("system", "System"),
            ("light", "Light"),
            ("dark", "Dark"),
        ):
            button = QPushButton(title)
            button.setObjectName("quality-option")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, selected=theme_id: self._set_theme_preference(selected)
            )
            self._theme_buttons[theme_id] = button
            theme_row.addWidget(button)
        layout.addLayout(theme_row)

        self._logout_button = QPushButton("Logout")
        self._logout_button.setObjectName("settings-action")
        self._logout_button.clicked.connect(self._logout)
        layout.addWidget(self._logout_button)
        self._settings_popup.hide()

    def _build_volume_popup(self) -> None:
        self._volume_popup = QFrame(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._volume_popup.setObjectName("volume-popup")
        layout = QVBoxLayout(self._volume_popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self._volume_slider, 0, Qt.AlignmentFlag.AlignCenter)
        self._volume_popup.installEventFilter(self)
        self._volume_popup.hide()

    def _show_settings_popup(self) -> None:
        if self._settings_popup is None:
            return
        self._settings_popup.adjustSize()
        anchor = self._auth_label.mapToGlobal(QPoint(0, self._auth_label.height() + 6))
        screen = self.screen().availableGeometry()
        x = min(anchor.x(), screen.right() - self._settings_popup.width() - 8)
        x = max(screen.left() + 8, x)
        y = min(anchor.y(), screen.bottom() - self._settings_popup.height() - 8)
        self._settings_popup.move(QPoint(x, y))
        self._settings_popup.show()
        self._settings_popup.raise_()

    def _show_volume_popup(self) -> None:
        if self._volume_popup is None:
            return
        self._volume_popup.adjustSize()
        position = self._volume_button.mapToGlobal(
            QPoint(
                -self._volume_popup.width() // 2 + self._volume_button.width() // 2,
                -self._volume_popup.height() - 6,
            ),
        )
        self._volume_popup.move(position)
        self._volume_popup.show()
        self._volume_popup.raise_()

    def _hide_volume_popup_if_idle(self) -> None:
        if self._volume_popup is None:
            return
        if self._volume_popup.geometry().contains(QCursor.pos()):
            return
        self._volume_popup.hide()

    def _apply_audio_quality(self) -> None:
        raw_quality = self._quality_combo.currentData()
        if not isinstance(raw_quality, str):
            return
        self._set_audio_quality(AudioQuality(raw_quality))

    def _set_audio_quality(self, quality: AudioQuality) -> None:
        self._container.services.music_service.set_audio_quality(quality)
        self._container.services.settings_service.save_audio_quality(quality)
        self._status_label.setText(f"Audio quality: {quality.name}")
        self._quality_combo.setCurrentIndex(self._quality_combo.findData(quality.value))
        for candidate, button in self._quality_buttons.items():
            button.setChecked(candidate is quality)

    def _set_theme_preference(self, theme: str) -> None:
        self._container.services.settings_service.save_theme_preference(theme)
        self._render_theme_preference(theme)
        self._apply_theme()
        self._status_label.setText(f"Theme preference: {theme}")

    def _render_theme_preference(self, theme: str) -> None:
        for candidate, button in self._theme_buttons.items():
            button.setChecked(candidate == theme)

    def _logout(self) -> None:
        self._container.services.auth_service.clear_session()
        self._container.services.music_service.clear_auth_session()
        if self._settings_popup is not None:
            self._settings_popup.hide()
        self._render_auth_state()
        self._status_label.setText("Logged out")
        self._maybe_start_auth_flow()

    def _apply_saved_settings_to_ui(self) -> None:
        quality = self._container.services.settings_service.load_audio_quality()
        quality_index = self._quality_combo.findData(quality.value)
        if quality_index >= 0:
            self._quality_combo.setCurrentIndex(quality_index)
        for candidate, button in self._quality_buttons.items():
            button.setChecked(candidate is quality)
        self._render_theme_preference(self._stored_theme_preference())
        self._apply_theme()

    def _maybe_start_auth_flow(self) -> None:
        if self._container.services.auth_service.current_session() is not None:
            return
        if self._is_headless_test_run():
            return

        self._auth_dialog = AuthDialog(parent=self)
        self._auth_dialog.token_captured.connect(self._complete_auth_flow)
        self._auth_dialog.finished.connect(self._clear_auth_dialog)
        self._auth_dialog.open()

    def _complete_auth_flow(self, token: str, expires_in: int | None) -> None:
        try:
            session = self._container.services.auth_service.authenticate_with_token(
                token,
                music_service=self._container.services.music_service,
                expires_in=expires_in,
            )
        except DomainError as exc:
            self._container.logger.warning("Auth flow failed: %s", exc)
            self._status_label.setText(f"Auth error: {user_facing_error_message(exc)}")
            return

        username = session.display_name or session.user_id
        self._status_label.setText(f"Authenticated as {username}")
        self._render_auth_state()

    def _clear_auth_dialog(self) -> None:
        self._auth_dialog = None

    def _is_headless_test_run(self) -> bool:
        app = QApplication.instance()
        if app is not None and app.platformName() == "offscreen":
            return True
        return environ.get("QT_QPA_PLATFORM") == "offscreen"

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            build_main_window_stylesheet(
                accent=self._accent_color,
                accent_text=self._accent_text_color(),
                theme=self._resolved_theme_mode(),
            )
        )
        self._refresh_theme_icons()
        if self._browser_dialog is not None:
            self._browser_dialog.setStyleSheet(self.styleSheet())
        if self._settings_popup is not None:
            self._settings_popup.setStyleSheet(self.styleSheet())
        if self._volume_popup is not None:
            self._volume_popup.setStyleSheet(self.styleSheet())

    def _stored_theme_preference(self) -> str:
        return self._container.services.settings_service.load_theme_preference()

    def _resolved_theme_mode(self) -> str:
        preference = self._stored_theme_preference()
        if preference in {"light", "dark"}:
            return preference
        app = QApplication.instance()
        if app is None:
            return "dark"
        return (
            "light"
            if app.styleHints().colorScheme() == Qt.ColorScheme.Light
            else "dark"
        )

    def _theme_icon_color(self) -> str:
        return "#1f2736" if self._resolved_theme_mode() == "light" else "#ffffff"

    def _refresh_theme_icons(self) -> None:
        icon_color = self._theme_icon_color()
        if hasattr(self, "_window_minimize_button"):
            self._window_minimize_button.setIcon(
                create_icon("window-minimize.svg", color=icon_color)
            )
        if hasattr(self, "_window_maximize_button"):
            self._refresh_window_maximize_button()
        if hasattr(self, "_window_close_button"):
            self._window_close_button.setIcon(create_icon("window-close.svg", color=icon_color))
        if hasattr(self, "_volume_button"):
            self._volume_button.setIcon(create_icon("volume.svg", color=icon_color))
        if hasattr(self, "_previous_button"):
            self._previous_button.setIcon(create_icon("previous.svg", color=icon_color))
        if hasattr(self, "_next_button"):
            self._next_button.setIcon(create_icon("next.svg", color=icon_color))
        if hasattr(self, "_play_all_button"):
            self._play_all_button.setIcon(create_icon("play.svg", color=icon_color))
        if hasattr(self, "_append_all_button"):
            self._append_all_button.setIcon(create_icon("add_to_playlist.svg", color=icon_color))
        if hasattr(self, "_queue_shuffle_button"):
            self._queue_shuffle_button.setIcon(
                create_icon("shuffle_playlist.svg", color=icon_color)
            )
        if hasattr(self, "_clear_queue_button"):
            self._clear_queue_button.setIcon(create_icon("clear_playlist.svg", color=icon_color))
        if hasattr(self, "_play_pause_button"):
            status_value = self._play_pause_button.property("playback_status") or "stopped"
            self._render_play_pause_button(PlaybackStatus(status_value))
        if hasattr(self, "_like_track_button"):
            self._render_current_track_like_button(
                self._current_track.is_liked if self._current_track else False
            )

    def _refresh_window_maximize_button(self) -> None:
        if not hasattr(self, "_window_maximize_button"):
            return
        icon_color = self._theme_icon_color()
        if self._is_macos_window_controls() and self._title_bar is not None:
            self._title_bar.setVisible(not self.isFullScreen())
        if not self._is_macos_window_controls():
            self._window_maximize_button.setIcon(
                create_icon("window-maximize.svg", color=icon_color)
            )
            self._window_maximize_button.setToolTip(
                "Restore" if self.isMaximized() else "Maximize"
            )
            return
        if self.isFullScreen():
            self._window_maximize_button.setIcon(
                create_icon("window-maximize.svg", color=icon_color)
            )
            self._window_maximize_button.setToolTip("Exit Full Screen")
            return
        self._window_maximize_button.setIcon(
            create_icon("window-maximize.svg", color=icon_color)
        )
        self._window_maximize_button.setToolTip("Full Screen")
