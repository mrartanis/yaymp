from __future__ import annotations

import colorsys
from dataclasses import replace
from os import environ
from pathlib import Path

import shiboken6
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QPixmap, QResizeEvent, QShowEvent
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.application.error_presenter import user_facing_error_message
from app.bootstrap.container import AppContainer
from app.domain import Album, Artist, AudioQuality, PlaybackStatus, Playlist, Station, Track
from app.domain.errors import DomainError
from app.domain.playback import QueueItem
from app.presentation.qt.auth_dialog import AuthDialog
from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.library_controller import (
    BrowserContent,
    BrowserItem,
    BrowserTab,
    LibraryController,
)
from app.presentation.qt.playback_controller import PlaybackController


class MainWindow(QMainWindow):
    def __init__(self, *, container: AppContainer) -> None:
        super().__init__()
        self._container = container
        self._controller = PlaybackController(
            playback_service=container.services.playback_service,
            logger=container.logger,
        )
        self._library_controller = LibraryController(
            search_service=container.services.search_service,
            library_service=container.services.library_service,
            logger=container.logger,
        )
        self._current_track: Track | None = None
        self._current_browser_content: BrowserContent | None = None
        self._artwork_manager = QNetworkAccessManager(self)
        self._pending_artwork_track_id: str | None = None
        self._pending_thumb_labels: dict[str, list[QLabel]] = {}
        self._queued_thumb_downloads: list[tuple[str, Path]] = []
        self._active_thumb_downloads = 0
        self._max_active_thumb_downloads = 4
        self._auth_dialog: AuthDialog | None = None
        self._auth_flow_checked = False
        self._browser_tab_ids: tuple[str, ...] = ()
        self._updating_browser_tabs = False
        self._loading_more_content = False
        self._accent_color = "#526ee8"
        self._queue_collapsed = False
        self._browser_auto_open_enabled = False
        self._browser_dialog: QDialog | None = None
        self._settings_popup: QFrame | None = None
        self._volume_popup: QFrame | None = None
        self._sidebar_popup: QFrame | None = None
        self._rendered_queue_key: tuple[tuple[str, str, str, str], ...] = ()
        self._rendered_active_index: int | None = None
        self._queue_selected_index: int | None = None
        self._track_like_overrides: dict[str, bool] = {}
        self._track_label_base_sizes: dict[QLabel, int] = {}
        self._playback_poll_timer = QTimer(self)
        self._playback_poll_timer.setInterval(1000)
        self.setWindowTitle("YAYMP")
        self._build_ui()
        self.setMinimumWidth(560)
        self.resize(self.minimumWidth(), 720)
        self._apply_saved_settings_to_ui()
        self._wire_controller()
        self._controller.initialize()
        self._library_controller.initialize()
        self._browser_auto_open_enabled = True
        self._hide_browser_panel()
        self._render_auth_state()
        self._playback_poll_timer.start()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._fit_track_text_labels()
        if self._auth_flow_checked:
            return
        self._auth_flow_checked = True
        QTimer.singleShot(0, self._maybe_start_auth_flow)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fit_track_text_labels()

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if watched is self._auth_label:
            if event.type() == QEvent.Type.Enter:
                self._show_settings_popup()
            return False
        if watched is self._settings_popup:
            if event.type() == QEvent.Type.Leave and self._settings_popup is not None:
                self._settings_popup.hide()
            return False
        if watched is self._volume_button:
            if event.type() == QEvent.Type.Enter:
                self._show_volume_popup()
            return False
        if watched is self._volume_popup:
            if event.type() == QEvent.Type.Leave:
                self._hide_volume_popup_if_idle()
            return False
        return super().eventFilter(watched, event)

    def _build_ui(self) -> None:
        root = QWidget(self)
        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(14, 14, 14, 14)
        outer_layout.setSpacing(8)

        outer_layout.addLayout(self._build_body(), 1)

        self.setCentralWidget(root)
        self._apply_theme()

    def _build_title_bar(self) -> QFrame:
        frame = self._plain_frame("top-bar")
        frame.setObjectName("top-bar")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(10)
        self._sidebar_toggle_button = QPushButton("≡")
        self._sidebar_toggle_button.setObjectName("sidebar-toggle")
        self._sidebar_toggle_button.setToolTip("Toggle navigation")
        self._sidebar_toggle_button.setFixedSize(38, 34)
        layout.addWidget(self._sidebar_toggle_button)
        self._now_playing_label = self._panel_label("Ready to play")
        self._now_playing_label.setObjectName("now-playing")
        layout.addWidget(self._now_playing_label, 1)
        self._auth_label = self._panel_label("Login required", align_right=True)
        layout.addWidget(self._auth_label)
        return frame

    def _build_transport_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self._previous_button = self._icon_button("previous.svg", "Previous")
        self._play_pause_button = self._icon_button("play.svg", "Play")
        self._play_pause_button.setObjectName("play-button")
        self._play_pause_button.setFixedSize(52, 44)
        self._next_button = self._icon_button("next.svg", "Next")
        self._like_track_button = QPushButton()
        self._like_track_button.setObjectName("like-current-button")
        self._like_track_button.setIcon(create_icon("heart_outline.svg"))
        self._like_track_button.setToolTip("Like current track")
        self._like_track_button.setFixedSize(34, 32)
        for button in (
            self._previous_button,
            self._play_pause_button,
            self._next_button,
            self._like_track_button,
        ):
            layout.addWidget(button)
        return layout

    def _build_body(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        main_column = QVBoxLayout()
        main_column.setSpacing(4)
        main_column.addWidget(self._build_player_panel(), 0)
        main_column.addWidget(self._build_queue_panel(), 1)
        layout.addLayout(main_column, 1)

        self._build_sidebar_popup()
        self._build_browser_dialog()
        return layout

    def _build_player_panel(self) -> QFrame:
        frame = self._panel_frame("Main Player")
        layout = frame.layout()
        assert layout is not None

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 300_000)
        self._seek_slider.setSingleStep(1_000)
        self._seek_slider.setPageStep(10_000)
        self._seek_slider.setObjectName("seek-slider")
        self._seek_slider.setFixedWidth(302)
        self._seek_label = self._panel_label("0:00 / 0:00")
        self._seek_label.setObjectName("seek-label")
        self._seek_label.setFixedHeight(28)
        self._seek_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self._seek_label.setMinimumWidth(92)
        self._seek_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._volume_slider = QSlider(Qt.Orientation.Vertical)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(100)
        self._volume_slider.setObjectName("volume-slider")
        self._volume_slider.setFixedSize(26, 118)
        self._volume_label = self._panel_label("Volume 100%")
        self._quality_combo = QComboBox()
        self._quality_combo.setObjectName("quality-combo")
        self._quality_combo.setFixedWidth(58)
        self._quality_combo.addItem("HQ", AudioQuality.HQ.value)
        self._quality_combo.addItem("SD", AudioQuality.SD.value)
        self._quality_combo.addItem("LQ", AudioQuality.LQ.value)
        self._quality_combo.setCurrentIndex(0)
        self._track_title_label = self._panel_label("Starter Signal")
        self._track_title_label.setObjectName("track-title")
        self._track_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_title_label.setWordWrap(True)
        self._track_title_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self._track_title_label.setMaximumHeight(108)
        self._track_meta_label = self._panel_label("Artist metadata will appear here")
        self._track_meta_label.setObjectName("track-artist")
        self._track_meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_meta_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self._track_meta_label.setMaximumHeight(72)
        self._track_meta_label.setWordWrap(True)
        self._track_album_label = self._panel_label("Album")
        self._track_album_label.setObjectName("track-album")
        self._track_album_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._track_album_label.setWordWrap(True)
        self._track_album_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self._track_album_label.setMaximumHeight(72)
        self._audio_info_label = self._panel_label("")
        self._audio_info_label.setObjectName("queue-audio-info")
        self._audio_info_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self._track_technical_label = self._panel_label("")
        self._track_technical_label.setObjectName("track-tech")
        self._track_technical_label.setVisible(False)
        self._playback_state_label = self._panel_label("Stopped")
        self._playback_state_label.setObjectName("playback-state")
        self._status_label = self._panel_label("")
        self._status_label.setObjectName("inline-status")
        self._status_label.setVisible(False)
        self._queue_status_label = self._panel_label("Queue idle", align_right=True)
        self._queue_status_label.setObjectName("queue-summary")
        self._artwork_label = QLabel("No cover")
        self._artwork_label.setObjectName("album-art")
        self._artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork_label.setFixedSize(300, 300)
        self._artwork_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._sidebar_toggle_button = QPushButton("≡")
        self._sidebar_toggle_button.setObjectName("sidebar-toggle")
        self._sidebar_toggle_button.setToolTip("Toggle navigation")
        self._sidebar_toggle_button.setFixedSize(30, 28)
        self._my_wave_top_button = QPushButton("My Wave")
        self._my_wave_top_button.setObjectName("my-wave-button")
        self._my_wave_top_button.setFixedHeight(28)
        self._auth_label = self._panel_label("Login required", align_right=True)
        self._auth_label.setObjectName("auth-label")
        self._auth_label.setFixedHeight(28)
        self._auth_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._auth_label.installEventFilter(self)
        self._volume_button = QPushButton()
        self._volume_button.setObjectName("volume-button")
        self._volume_button.setIcon(create_icon("volume.svg"))
        self._volume_button.setToolTip("Volume")
        self._volume_button.setFixedSize(34, 32)
        self._volume_button.installEventFilter(self)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(self._sidebar_toggle_button)
        top_row.addWidget(self._my_wave_top_button)
        top_row.addStretch(1)
        top_row.addWidget(self._auth_label, 0, Qt.AlignmentFlag.AlignVCenter)

        layout.addLayout(top_row)
        layout.addSpacing(6)

        hero_widget = QWidget()
        hero_widget.setFixedHeight(self._artwork_label.height())
        hero = QHBoxLayout(hero_widget)
        hero.setSpacing(14)
        hero.setContentsMargins(0, 0, 0, 0)
        hero.addWidget(self._artwork_label, 0, Qt.AlignmentFlag.AlignCenter)
        info_widget = QWidget()
        info_widget.setMinimumWidth(0)
        info_widget.setFixedHeight(self._artwork_label.height())
        info_widget.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(5)
        info_layout.setContentsMargins(0, 0, 0, 0)
        text_block = QWidget()
        text_block.setObjectName("track-metadata-zone")
        text_block.setMinimumWidth(0)
        text_block.setFixedHeight(176)
        text_block.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        text_block_layout = QVBoxLayout(text_block)
        text_block_layout.setContentsMargins(0, 0, 0, 0)
        text_block_layout.setSpacing(5)
        text_block_layout.addStretch(1)
        text_block_layout.addWidget(self._track_title_label)
        text_block_layout.addWidget(self._track_meta_label)
        text_block_layout.addWidget(self._track_album_label)
        text_block_layout.addStretch(1)
        info_layout.addStretch(1)
        info_layout.addWidget(text_block)
        info_layout.addStretch(1)
        info_layout.addLayout(self._build_transport_bar())
        info_layout.addSpacing(10)
        hero.addWidget(info_widget, 1)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.addWidget(self._seek_slider, 0)
        progress_row.addWidget(self._seek_label)
        progress_row.addWidget(self._volume_button)
        progress_row.addWidget(self._like_track_button)
        progress_row.addStretch(1)

        secondary_row = QHBoxLayout()
        secondary_row.setSpacing(8)
        secondary_row.setContentsMargins(0, 0, 0, 0)
        secondary_row.addStretch(1)

        layout.addWidget(hero_widget)
        layout.addLayout(progress_row)
        layout.addLayout(secondary_row)
        self._build_settings_popup()
        self._build_volume_popup()
        self._track_label_base_sizes = {
            self._track_title_label: 28,
            self._track_meta_label: 16,
            self._track_album_label: 13,
        }
        return frame

    def _build_nav_panel(self) -> QFrame:
        frame = self._panel_frame("Navigation")
        frame.setObjectName("sidebar")
        frame.setMinimumWidth(170)
        frame.setMaximumWidth(210)
        layout = frame.layout()
        assert layout is not None
        self._search_nav_button = QPushButton("Search")
        self._liked_nav_button = QPushButton("My Tracks")
        self._liked_albums_nav_button = QPushButton("My Albums")
        self._liked_artists_nav_button = QPushButton("My Artists")
        self._playlists_nav_button = QPushButton("Playlists")
        library_label = QLabel("Library")
        library_label.setObjectName("nav-section")
        layout.addWidget(library_label)
        for button in (
            self._liked_nav_button,
            self._liked_albums_nav_button,
            self._liked_artists_nav_button,
            self._playlists_nav_button,
        ):
            layout.addWidget(button)
        layout.addSpacing(8)
        discovery_label = QLabel("Discovery")
        discovery_label.setObjectName("nav-section")
        layout.addWidget(discovery_label)
        layout.addWidget(self._search_nav_button)
        return frame

    def _build_sidebar_popup(self) -> None:
        self._sidebar_popup = self._build_nav_panel()
        self._sidebar_popup.setParent(self)
        self._sidebar_popup.adjustSize()
        self._sidebar_popup.hide()
        self._sidebar_popup.move(14, 54)
        self._sidebar_popup.raise_()

    def _build_settings_popup(self) -> None:
        self._settings_popup = QFrame(
            None,
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint,
        )
        self._settings_popup.setObjectName("settings-popup")
        self._settings_popup.installEventFilter(self)
        layout = QHBoxLayout(self._settings_popup)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        self._quality_buttons: dict[AudioQuality, QPushButton] = {}
        for quality in (AudioQuality.HQ, AudioQuality.SD, AudioQuality.LQ):
            button = QPushButton(quality.name)
            button.setObjectName("quality-option")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, selected=quality: self._set_audio_quality(selected)
            )
            self._quality_buttons[quality] = button
            layout.addWidget(button)
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

    def _build_browser_panel(self) -> QFrame:
        frame = self._panel_frame("Search / Library")
        base_layout = frame.layout()
        assert base_layout is not None
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search Yandex Music")
        self._search_button = QPushButton("Search")
        self._recent_searches_combo = QComboBox()
        self._recent_searches_combo.setPlaceholderText("Recent searches")
        self._recent_searches_combo.addItem("Recent searches")
        self._browser_title_label = self._panel_label("Search")
        self._browser_title_label.setObjectName("browser-title")
        self._browser_back_button = QPushButton("‹")
        self._browser_back_button.setObjectName("panel-back-button")
        self._browser_back_button.setToolTip("Back")
        self._browser_back_button.setFixedSize(32, 30)
        self._browser_back_button.setEnabled(False)
        self._browser_close_button = QPushButton("×")
        self._browser_close_button.setObjectName("panel-close-button")
        self._browser_close_button.setToolTip("Close")
        self._browser_close_button.setFixedSize(32, 30)
        self._browser_tabs = QTabWidget()
        self._browser_tabs.setVisible(False)
        self._content_list = QListWidget()
        self._content_list.setAlternatingRowColors(True)
        self._content_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._content_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._play_all_button = QPushButton("Play all")
        self._play_all_button.setIcon(create_icon("play.svg"))
        self._append_all_button = QPushButton("Append all")
        self._append_all_button.setIcon(create_icon("add_to_playlist.svg"))
        header_row.addWidget(self._browser_back_button)
        header_row.addWidget(self._browser_title_label, 1)
        header_row.addWidget(self._browser_close_button)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self._search_input, 1)
        search_row.addWidget(self._search_button)
        search_row.addWidget(self._recent_searches_combo)
        like_row = QHBoxLayout()
        like_row.setSpacing(8)
        like_row.addWidget(self._play_all_button)
        like_row.addWidget(self._append_all_button)
        like_row.addStretch(1)
        base_layout.addLayout(header_row)
        base_layout.addLayout(search_row)
        base_layout.addWidget(self._browser_tabs)
        base_layout.addWidget(self._content_list, 1)
        base_layout.addLayout(like_row)
        return frame

    def _build_browser_dialog(self) -> None:
        self._browser_dialog = QDialog(self)
        self._browser_dialog.setWindowTitle("YAYMP Library")
        self._browser_dialog.setModal(False)
        self._browser_dialog.resize(860, 560)
        dialog_layout = QVBoxLayout(self._browser_dialog)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        self._browser_panel = self._build_browser_panel()
        dialog_layout.addWidget(self._browser_panel)
        self._browser_dialog.setStyleSheet(self.styleSheet())

    def _build_queue_panel(self) -> QFrame:
        frame = self._panel_frame("Queue")
        frame.setObjectName("queue-panel")
        layout = frame.layout()
        assert layout is not None
        self._queue_separator = QFrame()
        self._queue_separator.setObjectName("queue-separator")
        self._queue_separator.setFixedHeight(1)
        layout.addWidget(self._queue_separator)
        self._queue_list = QListWidget()
        self._queue_list.setObjectName("queue-list")
        self._queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._queue_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addWidget(
            self._queue_status_label,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        footer.addWidget(self._audio_info_label, 0, Qt.AlignmentFlag.AlignVCenter)
        footer.addStretch(1)
        self._queue_shuffle_button = QPushButton()
        self._queue_shuffle_button.setObjectName("queue-icon-button")
        self._queue_shuffle_button.setToolTip("Shuffle queue")
        self._queue_shuffle_button.setFixedSize(34, 32)
        self._queue_shuffle_button.setCheckable(True)
        self._queue_shuffle_button.setIcon(create_icon("shuffle_playlist.svg"))
        self._clear_queue_button = QPushButton()
        self._clear_queue_button.setObjectName("queue-icon-button")
        self._clear_queue_button.setToolTip("Clear queue")
        self._clear_queue_button.setFixedSize(34, 32)
        self._clear_queue_button.setIcon(create_icon("clear_playlist.svg"))
        footer.addWidget(self._queue_shuffle_button)
        footer.addWidget(self._clear_queue_button)
        layout.addWidget(self._queue_list)
        layout.addLayout(footer)
        return frame

    def _wire_controller(self) -> None:
        self._controller.playback_changed.connect(self._render_snapshot)
        self._controller.playback_failed.connect(self._render_error)
        self._library_controller.content_changed.connect(self._render_content)
        self._library_controller.content_failed.connect(self._render_library_error)
        self._library_controller.track_liked.connect(self._render_track_liked)
        self._library_controller.track_unliked.connect(self._render_track_unliked)
        self._library_controller.album_liked.connect(self._render_album_liked)
        self._library_controller.album_unliked.connect(self._render_album_unliked)
        self._library_controller.artist_liked.connect(self._render_artist_liked)
        self._library_controller.artist_unliked.connect(self._render_artist_unliked)
        self._library_controller.playlist_liked.connect(self._render_playlist_liked)
        self._library_controller.playlist_unliked.connect(self._render_playlist_unliked)
        self._sidebar_toggle_button.clicked.connect(self._toggle_sidebar)
        self._previous_button.clicked.connect(self._controller.previous)
        self._play_pause_button.clicked.connect(self._toggle_play_pause)
        self._next_button.clicked.connect(self._controller.next)
        self._seek_slider.sliderReleased.connect(self._apply_seek)
        self._volume_slider.valueChanged.connect(self._apply_volume)
        self._queue_list.itemClicked.connect(self._select_queue_highlight)
        self._queue_list.itemDoubleClicked.connect(self._select_queue_item)
        self._queue_list.currentRowChanged.connect(self._select_queue_highlight_row)
        self._clear_queue_button.clicked.connect(self._controller.clear_queue)
        self._queue_shuffle_button.toggled.connect(self._controller.set_shuffle_enabled)
        self._browser_back_button.clicked.connect(self._library_controller.go_back)
        self._browser_close_button.clicked.connect(self._hide_browser_panel)
        self._content_list.itemDoubleClicked.connect(self._open_content_item)
        self._content_list.customContextMenuRequested.connect(self._show_content_context_menu)
        self._content_list.verticalScrollBar().valueChanged.connect(self._maybe_load_more_content)
        self._queue_list.customContextMenuRequested.connect(self._show_queue_context_menu)
        self._search_button.clicked.connect(self._run_search)
        self._search_input.returnPressed.connect(self._run_search)
        self._recent_searches_combo.activated.connect(self._apply_recent_search)
        self._search_nav_button.clicked.connect(self._show_search)
        self._liked_nav_button.clicked.connect(self._library_controller.load_liked_tracks)
        self._liked_albums_nav_button.clicked.connect(self._library_controller.load_liked_albums)
        self._liked_artists_nav_button.clicked.connect(
            self._library_controller.load_liked_artists
        )
        self._playlists_nav_button.clicked.connect(self._library_controller.load_playlists)
        self._my_wave_top_button.clicked.connect(self._start_my_wave)
        self._like_track_button.clicked.connect(self._toggle_current_track_like)
        self._play_all_button.clicked.connect(self._play_current_source)
        self._append_all_button.clicked.connect(self._append_current_source)
        self._browser_tabs.currentChanged.connect(self._change_browser_tab)
        self._quality_combo.currentIndexChanged.connect(self._apply_audio_quality)
        self._playback_poll_timer.timeout.connect(self._controller.refresh)
        self._artwork_manager.finished.connect(self._handle_artwork_downloaded)

    def _apply_seek(self) -> None:
        self._controller.seek(self._seek_slider.value())

    def _toggle_sidebar(self) -> None:
        if self._sidebar_popup is None:
            return
        if self._sidebar_popup.isVisible():
            self._sidebar_popup.hide()
            return
        position = self._sidebar_toggle_button.mapTo(
            self,
            QPoint(0, self._sidebar_toggle_button.height() + 6),
        )
        self._sidebar_popup.move(position)
        self._sidebar_popup.show()
        self._sidebar_popup.raise_()

    def _show_browser_panel(self) -> None:
        if self._browser_dialog is None:
            return
        self._browser_dialog.show()
        self._browser_dialog.raise_()
        self._browser_dialog.activateWindow()

    def _hide_browser_panel(self) -> None:
        if self._browser_dialog is not None:
            self._browser_dialog.hide()

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

    def _toggle_play_pause(self) -> None:
        if self._play_pause_button.property("playback_status") == PlaybackStatus.PLAYING.value:
            self._controller.pause()
            return
        self._controller.play()

    def _toggle_current_track_like(self) -> None:
        if self._current_track is None:
            self._status_label.setText("Select or play a track first")
            return
        self._toggle_track_like(self._current_track)

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

    def _apply_volume(self, volume: int) -> None:
        self._controller.set_volume(volume)
        self._container.services.settings_service.save_volume(volume)

    def _apply_saved_settings_to_ui(self) -> None:
        quality = self._container.services.settings_service.load_audio_quality()
        quality_index = self._quality_combo.findData(quality.value)
        if quality_index >= 0:
            self._quality_combo.setCurrentIndex(quality_index)
        for candidate, button in self._quality_buttons.items():
            button.setChecked(candidate is quality)

    def _select_queue_item(self, item: QListWidgetItem) -> None:
        self._select_queue_highlight(item)
        row = self._queue_list.row(item)
        self._controller.select_index(row)

    def _select_queue_highlight(self, item: QListWidgetItem) -> None:
        self._queue_selected_index = self._queue_list.row(item)
        self._update_queue_active_row(self._rendered_active_index)

    def _select_queue_highlight_row(self, row: int) -> None:
        if not self._queue_list.hasFocus():
            return
        self._queue_selected_index = row if row >= 0 else None
        self._update_queue_active_row(self._rendered_active_index)

    def _open_content_item(self, item: QListWidgetItem) -> None:
        browser_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(browser_item, BrowserItem):
            return

        payload = browser_item.payload
        if browser_item.kind == "track" and isinstance(payload, Track):
            if browser_item.source_type == "station" and browser_item.source_id:
                self._controller.play_station(browser_item.source_id)
                return
            if (
                browser_item.source_tracks
                and browser_item.source_type
                and browser_item.source_id
                and browser_item.source_index is not None
            ):
                self._controller.play_tracks(
                    browser_item.source_tracks,
                    start_index=browser_item.source_index,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                )
                return
            self._controller.play_track(payload)
            return
        if browser_item.kind == "album" and isinstance(payload, Album):
            self._library_controller.open_album(payload)
            return
        if (
            browser_item.kind in {"playlist", "generated_playlist", "collection"}
            and isinstance(payload, Playlist)
        ):
            self._library_controller.open_playlist(payload)
            return
        if browser_item.kind == "station" and isinstance(payload, Station):
            self._library_controller.open_station(payload)
            return
        if browser_item.kind == "artist_radio" and isinstance(payload, Station):
            self._controller.play_station(payload.id)
            return
        if browser_item.kind == "artist" and isinstance(payload, Artist):
            self._library_controller.open_artist(payload)
            return

    def _run_search(self) -> None:
        self._show_browser_panel()
        self._library_controller.search_tracks(self._search_input.text())

    def _show_search(self) -> None:
        self._show_browser_panel()
        self._library_controller.show_search_page()
        self._search_input.setFocus()

    def _change_browser_tab(self, index: int) -> None:
        if self._updating_browser_tabs:
            return
        if index < 0 or index >= len(self._browser_tab_ids):
            return
        self._library_controller.show_browser_tab(self._browser_tab_ids[index])

    def _start_my_wave(self) -> None:
        self._controller.play_station("user:onyourwave")

    def _apply_recent_search(self, index: int) -> None:
        if index <= 0:
            return
        query = self._recent_searches_combo.itemText(index)
        self._search_input.setText(query)
        self._show_browser_panel()
        self._library_controller.search_tracks(query)

    def _render_snapshot(self, snapshot) -> None:
        current_item = snapshot.current_item
        queue = snapshot.queue
        state = snapshot.state

        if current_item is not None:
            current_track = self._track_with_like_override(current_item.track)
            self._current_track = current_track
            artists = ", ".join(current_track.artists)
            album_text = (
                f"{current_track.album_title or 'Single'}"
                f"{self._format_year(current_track.album_year)}"
            )
            self._track_title_label.setText(current_track.title)
            self._track_title_label.setToolTip(current_track.title)
            self._track_meta_label.setText(artists or "Unknown artist")
            self._track_meta_label.setToolTip(artists)
            self._track_album_label.setText(
                album_text
            )
            self._track_album_label.setToolTip(album_text)
            self._fit_track_text_labels()
            self._render_current_track_like_button(current_track.is_liked)
            self._render_artwork(current_track)
        else:
            self._current_track = None
            self._track_title_label.setText("No track selected")
            self._track_meta_label.setText("Choose music from My Wave, library, or search")
            self._track_album_label.setText("")
            self._fit_track_text_labels()
            self._render_current_track_like_button(False)
            self._clear_artwork()
            self._set_accent_color("#526ee8")

        self._render_play_pause_button(state.status)
        self._seek_slider.blockSignals(True)
        self._seek_slider.setMaximum(state.duration_ms or 300_000)
        self._seek_slider.setValue(state.position_ms)
        self._seek_slider.blockSignals(False)
        self._seek_label.setText(
            f"{self._format_ms(state.position_ms)} / {self._format_ms(state.duration_ms)}"
        )
        self._volume_slider.blockSignals(True)
        self._volume_slider.setValue(state.volume)
        self._volume_slider.blockSignals(False)
        self._volume_label.setText(f"{state.volume}%")
        self._queue_shuffle_button.blockSignals(True)
        self._queue_shuffle_button.setChecked(state.shuffle_enabled)
        self._queue_shuffle_button.blockSignals(False)
        self._queue_status_label.setText(
            f"{len(queue)} tracks | {self._format_ms(self._queue_duration_ms(queue))}"
        )
        self._audio_info_label.setText(
            self._format_audio_info(state.audio_codec, state.audio_bitrate)
        )
        self._render_queue(snapshot)
        self._render_auth_state()

    def _track_with_like_override(self, track: Track) -> Track:
        liked = self._track_like_overrides.get(track.id)
        if liked is None or liked == track.is_liked:
            return track
        return replace(track, is_liked=liked)

    def _render_current_track_like_button(self, is_liked: bool) -> None:
        self._like_track_button.setIcon(
            create_icon("heart.svg", color=self._accent_color)
            if is_liked
            else create_icon("heart_outline.svg")
        )
        self._like_track_button.setToolTip(
            "Unlike current track" if is_liked else "Like current track"
        )

    def _render_play_pause_button(self, status: PlaybackStatus) -> None:
        self._play_pause_button.setProperty("playback_status", status.value)
        if status is PlaybackStatus.PLAYING:
            self._play_pause_button.setIcon(create_icon("pause.svg"))
            self._play_pause_button.setToolTip("Pause")
            self._play_pause_button.setAccessibleName("Pause")
            return
        self._play_pause_button.setIcon(create_icon("play.svg"))
        self._play_pause_button.setToolTip("Play")
        self._play_pause_button.setAccessibleName("Play")

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

    def _render_error(self, message: str) -> None:
        self._status_label.setText(f"Playback error: {message}")

    def _render_auth_state(self) -> None:
        session = self._container.services.auth_service.current_session()
        if session is None:
            self._auth_label.setText("Login required")
            return
        username = session.display_name or session.user_id
        self._auth_label.setText(username)

    def _render_content(self, content: BrowserContent) -> None:
        if self._browser_auto_open_enabled:
            self._show_browser_panel()
        self._current_browser_content = content
        self._loading_more_content = False
        self._browser_title_label.setText(content.title)
        self._browser_back_button.setEnabled(self._library_controller.can_go_back())
        self._render_browser_tabs(content.tabs, active_tab=content.active_tab)
        self._recent_searches_combo.blockSignals(True)
        self._recent_searches_combo.clear()
        self._recent_searches_combo.addItem("Recent searches")
        for query in content.recent_searches:
            self._recent_searches_combo.addItem(query)
        self._recent_searches_combo.blockSignals(False)

        self._content_list.blockSignals(True)
        self._content_list.clear()
        if not content.items:
            empty_item = QListWidgetItem("No items")
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._content_list.addItem(empty_item)
        for browser_item in content.items:
            text = browser_item.title
            if browser_item.subtitle:
                text = f"{browser_item.title}\n{browser_item.subtitle}"
            widget_item = QListWidgetItem(text)
            widget_item.setData(Qt.ItemDataRole.UserRole, browser_item)
            if browser_item.kind == "section":
                widget_item.setFlags(widget_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            elif self._browser_item_uses_art(browser_item):
                widget = self._browser_art_row_widget(browser_item)
                widget_item.setSizeHint(widget.sizeHint())
                widget_item.setText("")
            self._content_list.addItem(widget_item)
            if browser_item.kind != "section" and self._browser_item_uses_art(browser_item):
                self._content_list.setItemWidget(widget_item, widget)
        self._content_list.blockSignals(False)
        can_play_source = bool(
            content.source_tracks
            and content.source_type in {"album", "artist", "playlist"}
            and content.source_id
        )
        self._play_all_button.setEnabled(can_play_source)
        self._append_all_button.setEnabled(can_play_source)

    def _browser_item_uses_art(self, item: BrowserItem) -> bool:
        return item.kind in {
            "album",
            "artist",
        }

    def _browser_art_row_widget(self, item: BrowserItem) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(9)
        artwork_ref = getattr(item.payload, "artwork_ref", None)
        layout.addWidget(self._art_thumb_label(artwork_ref, size=46))
        text_container = QWidget()
        text_container.setObjectName("browser-art-text")
        text_container.setMinimumWidth(0)
        text_container.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        title = QLabel(item.title)
        title.setObjectName("browser-art-title")
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        subtitle = QLabel(item.subtitle or "")
        subtitle.setObjectName("browser-art-subtitle")
        subtitle.setMinimumWidth(0)
        subtitle.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)
        layout.addWidget(text_container, 1)
        return row

    def _art_thumb_label(self, artwork_ref: str | None, *, size: int) -> QLabel:
        label = QLabel()
        label.setObjectName("art-thumb")
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not artwork_ref:
            label.setText("♪")
            return label
        artwork_url = self._container.services.artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            label.setText("♪")
            return label
        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        if not cache_path.exists():
            label.setText("♪")
            self._queue_thumb_download(artwork_url, cache_path, label)
            return label
        pixmap = QPixmap(str(cache_path))
        if pixmap.isNull():
            label.setText("♪")
            return label
        self._set_thumb_pixmap(label, pixmap)
        return label

    def _queue_thumb_download(self, artwork_url: str, cache_path: Path, label: QLabel) -> None:
        labels = self._pending_thumb_labels.setdefault(artwork_url, [])
        labels.append(label)
        if len(labels) > 1:
            return
        self._queued_thumb_downloads.append((artwork_url, cache_path))
        self._start_next_thumb_downloads()

    def _start_next_thumb_downloads(self) -> None:
        while (
            self._queued_thumb_downloads
            and self._active_thumb_downloads < self._max_active_thumb_downloads
        ):
            artwork_url, cache_path = self._queued_thumb_downloads.pop(0)
            self._start_thumb_download(artwork_url, cache_path)

    def _start_thumb_download(self, artwork_url: str, cache_path: Path) -> None:
        request = QNetworkRequest(QUrl(artwork_url))
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setAttribute(QNetworkRequest.Attribute.HttpPipeliningAllowedAttribute, False)
        reply = self._artwork_manager.get(request)
        reply.setProperty("thumb_artwork_url", artwork_url)
        reply.setProperty("cache_path", str(cache_path))
        self._active_thumb_downloads += 1

    def _set_thumb_pixmap(self, label: QLabel, pixmap: QPixmap) -> None:
        if not shiboken6.isValid(label):
            return
        label.setText("")
        label.setPixmap(
            pixmap.scaled(
                label.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _maybe_load_more_content(self, value: int) -> None:
        content = self._current_browser_content
        if self._loading_more_content or content is None:
            return
        if content.list_key != "liked_tracks" or not content.has_more:
            return
        scroll_bar = self._content_list.verticalScrollBar()
        if value < scroll_bar.maximum() - 2:
            return
        self._loading_more_content = True
        self._library_controller.load_more_current_list()

    def _render_browser_tabs(
        self,
        tabs: tuple[BrowserTab, ...],
        *,
        active_tab: str | None = None,
    ) -> None:
        self._updating_browser_tabs = True
        self._browser_tabs.clear()
        self._browser_tab_ids = tuple(tab.id for tab in tabs)
        for tab in tabs:
            self._browser_tabs.addTab(QWidget(), tab.title)
        active_index = (
            self._browser_tab_ids.index(active_tab)
            if active_tab in self._browser_tab_ids
            else 0
        )
        if self._browser_tab_ids:
            self._browser_tabs.setCurrentIndex(active_index)
        self._browser_tabs.setVisible(bool(self._browser_tab_ids))
        self._updating_browser_tabs = False

    def _render_library_error(self, message: str) -> None:
        self._status_label.setText(f"Library error: {message}")

    def _render_track_liked(self, track: Track) -> None:
        self._track_like_overrides[track.id] = True
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
            self._render_current_track_like_button(True)
        self._replace_content_track(track)
        self._update_queue_track_like(track)
        self._status_label.setText(f"Liked: {track.title}")

    def _render_track_unliked(self, track: Track) -> None:
        self._track_like_overrides[track.id] = False
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
            self._render_current_track_like_button(False)
        self._replace_content_track(track)
        self._update_queue_track_like(track)
        self._status_label.setText(f"Unliked: {track.title}")

    def _render_album_liked(self, album: Album) -> None:
        self._replace_content_entity(album)
        self._status_label.setText(f"Liked album: {album.title}")

    def _render_album_unliked(self, album: Album) -> None:
        self._replace_content_entity(album)
        self._status_label.setText(f"Unliked album: {album.title}")

    def _render_artist_liked(self, artist: Artist) -> None:
        self._replace_content_entity(artist)
        self._status_label.setText(f"Liked artist: {artist.name}")

    def _render_artist_unliked(self, artist: Artist) -> None:
        self._replace_content_entity(artist)
        self._status_label.setText(f"Unliked artist: {artist.name}")

    def _render_playlist_liked(self, playlist: Playlist) -> None:
        self._replace_content_entity(playlist)
        self._status_label.setText(f"Liked playlist: {playlist.title}")

    def _render_playlist_unliked(self, playlist: Playlist) -> None:
        self._replace_content_entity(playlist)
        self._status_label.setText(f"Unliked playlist: {playlist.title}")

    def _like_selected_or_current_track(self) -> None:
        track = self._selected_or_current_track()
        if track is None:
            self._status_label.setText("Library error: select or play a track first")
            return
        self._library_controller.like_track(track)

    def _unlike_selected_or_current_track(self) -> None:
        track = self._selected_or_current_track()
        if track is None:
            self._status_label.setText("Library error: select or play a track first")
            return
        self._library_controller.unlike_track(track)

    def _selected_or_current_track(self) -> Track | None:
        item = self._content_list.currentItem()
        if item is not None:
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(browser_item, BrowserItem) and isinstance(browser_item.payload, Track):
                return browser_item.payload
        return self._current_track

    def _play_current_source(self) -> None:
        content = self._current_browser_content
        if (
            content is None
            or not content.source_tracks
            or not content.source_type
            or not content.source_id
        ):
            return
        self._controller.play_tracks(
            content.source_tracks,
            start_index=0,
            source_type=content.source_type,
            source_id=content.source_id,
        )

    def _append_current_source(self) -> None:
        content = self._current_browser_content
        if (
            content is None
            or not content.source_tracks
            or not content.source_type
            or not content.source_id
        ):
            return
        self._controller.append_tracks(
            content.source_tracks,
            source_type=content.source_type,
            source_id=content.source_id,
        )

    def _replace_content_track(self, track: Track) -> None:
        for index in range(self._content_list.count()):
            item = self._content_list.item(index)
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(browser_item, BrowserItem):
                continue
            if not isinstance(browser_item.payload, Track):
                continue
            if browser_item.payload.id != track.id:
                continue
            title = track.title
            text = title
            subtitle = ", ".join(track.artists)
            if track.album_title:
                subtitle = f"{subtitle} | {track.album_title}" if subtitle else track.album_title
            if subtitle:
                text = f"{title}\n{subtitle}"
            item.setText(text)
            item.setData(
                Qt.ItemDataRole.UserRole,
                BrowserItem(
                    kind=browser_item.kind,
                    title=title,
                    subtitle=subtitle,
                    payload=track,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                    source_tracks=browser_item.source_tracks,
                    source_index=browser_item.source_index,
                ),
            )
            break

    def _update_queue_track_like(self, track: Track) -> None:
        for index in range(self._queue_list.count()):
            item = self._queue_list.item(index)
            queue_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(queue_item, QueueItem):
                continue
            if queue_item.track.id != track.id:
                continue
            item.setData(
                Qt.ItemDataRole.UserRole,
                replace(queue_item, track=track),
            )
        self._update_queue_active_row(self._rendered_active_index)

    def _replace_content_entity(self, entity: Album | Artist | Playlist) -> None:
        for index in range(self._content_list.count()):
            item = self._content_list.item(index)
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(browser_item, BrowserItem):
                continue
            payload = browser_item.payload
            if type(payload) is not type(entity):
                continue
            if getattr(payload, "id", None) != getattr(entity, "id", None):
                continue
            item.setData(
                Qt.ItemDataRole.UserRole,
                BrowserItem(
                    kind=browser_item.kind,
                    title=browser_item.title,
                    subtitle=browser_item.subtitle,
                    payload=entity,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                    source_tracks=browser_item.source_tracks,
                    source_index=browser_item.source_index,
                ),
            )
            break

    def _show_content_context_menu(self, position: QPoint) -> None:
        item = self._content_list.itemAt(position)
        if item is None:
            return
        self._content_list.setCurrentItem(item)
        browser_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(browser_item, BrowserItem):
            return
        menu = QMenu(self)
        if not self._populate_browser_item_menu(menu, browser_item):
            return
        menu.exec(self._content_list.viewport().mapToGlobal(position))

    def _show_queue_context_menu(self, position: QPoint) -> None:
        item = self._queue_list.itemAt(position)
        if item is None:
            return
        self._queue_list.setCurrentItem(item)
        self._select_queue_highlight(item)
        queue_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(queue_item, QueueItem):
            return
        menu = QMenu(self)
        queue_index = self._queue_list.row(item)
        if not self._populate_queue_item_menu(menu, queue_item, queue_index):
            return
        menu.exec(self._queue_list.viewport().mapToGlobal(position))

    def _populate_browser_item_menu(self, menu: QMenu, browser_item: BrowserItem) -> bool:
        payload = browser_item.payload
        if isinstance(payload, Track):
            return self._populate_track_menu(menu, payload)
        if isinstance(payload, Album):
            self._add_copy_share_link_action(menu, self._album_share_link(payload))
            self._add_album_like_action(menu, payload)
            self._add_album_radio_action(menu, payload)
            self._add_go_to_artist_actions(menu, payload.artist_ids, payload.artists)
            return not menu.isEmpty()
        if isinstance(payload, Artist):
            self._add_copy_share_link_action(menu, self._artist_share_link(payload))
            self._add_artist_like_action(menu, payload)
            self._add_artist_radio_action(menu, payload)
            return not menu.isEmpty()
        if isinstance(payload, Playlist):
            self._add_copy_share_link_action(menu, self._playlist_share_link(payload))
            self._add_playlist_like_action(menu, payload)
            return not menu.isEmpty()
        if isinstance(payload, Station):
            self._add_copy_share_link_action(menu, self._station_share_link(payload))
            return not menu.isEmpty()
        return False

    def _populate_track_menu(
        self,
        menu: QMenu,
        track: Track,
        *,
        include_queue_actions: bool = True,
    ) -> bool:
        self._add_copy_share_link_action(menu, self._track_share_link(track))
        action_text = "Unlike" if track.is_liked else "Like"
        toggle_like = QAction(action_text, self)
        toggle_like.triggered.connect(
            lambda checked=False, selected_track=track: self._toggle_track_like(selected_track)
        )
        menu.addAction(toggle_like)
        if include_queue_actions:
            add_to_queue = QAction("Add to queue", self)
            add_to_queue.triggered.connect(
                lambda checked=False, selected_track=track: self._controller.append_tracks(
                    (selected_track,),
                    source_type="track",
                    source_id=selected_track.id,
                )
            )
            menu.addAction(add_to_queue)
            play_next = QAction("Play next", self)
            play_next.triggered.connect(
                lambda checked=False, selected_track=track: self._controller.play_track_next(
                    selected_track,
                    source_type="track",
                    source_id=selected_track.id,
                )
            )
            menu.addAction(play_next)
        self._add_track_radio_action(menu, track)
        self._add_go_to_artist_actions(menu, track.artist_ids, track.artists)
        if track.album_id:
            go_to_album = QAction("Go to album", self)
            album_id = track.album_id
            go_to_album.triggered.connect(
                lambda checked=False, selected_album_id=album_id: (
                    self._library_controller.open_album_by_id(selected_album_id)
                )
            )
            menu.addAction(go_to_album)
        return not menu.isEmpty()

    def _populate_queue_item_menu(
        self,
        menu: QMenu,
        queue_item: QueueItem,
        queue_index: int,
    ) -> bool:
        self._populate_track_menu(menu, queue_item.track, include_queue_actions=False)
        play_next = QAction("Play next", self)
        play_next.triggered.connect(
            lambda checked=False, index=queue_index: self._controller.move_queue_item_next(index)
        )
        menu.addAction(play_next)
        remove_action = QAction("Remove from queue", self)
        remove_action.triggered.connect(
            lambda checked=False, index=queue_index: self._controller.remove_queue_index(index)
        )
        menu.addAction(remove_action)
        return not menu.isEmpty()

    def _toggle_track_like(self, track: Track) -> None:
        if track.is_liked:
            self._library_controller.unlike_track(track)
            return
        self._library_controller.like_track(track)

    def _add_album_like_action(self, menu: QMenu, album: Album) -> None:
        action = QAction("Unlike" if album.is_liked else "Like", self)
        action.triggered.connect(
            lambda checked=False, selected_album=album: self._toggle_album_like(selected_album)
        )
        menu.addAction(action)

    def _add_artist_like_action(self, menu: QMenu, artist: Artist) -> None:
        action = QAction("Unlike" if artist.is_liked else "Like", self)
        action.triggered.connect(
            lambda checked=False, selected_artist=artist: self._toggle_artist_like(selected_artist)
        )
        menu.addAction(action)

    def _add_playlist_like_action(self, menu: QMenu, playlist: Playlist) -> None:
        action = QAction("Unlike" if playlist.is_liked else "Like", self)
        action.triggered.connect(
            lambda checked=False, selected_playlist=playlist: self._toggle_playlist_like(
                selected_playlist
            )
        )
        menu.addAction(action)

    def _toggle_album_like(self, album: Album) -> None:
        if album.is_liked:
            self._library_controller.unlike_album(album)
            return
        self._library_controller.like_album(album)

    def _toggle_artist_like(self, artist: Artist) -> None:
        if artist.is_liked:
            self._library_controller.unlike_artist(artist)
            return
        self._library_controller.like_artist(artist)

    def _toggle_playlist_like(self, playlist: Playlist) -> None:
        if playlist.is_liked:
            self._library_controller.unlike_playlist(playlist)
            return
        self._library_controller.like_playlist(playlist)

    def _add_copy_share_link_action(self, menu: QMenu, link: str | None) -> None:
        if not link:
            return
        action = QAction("Copy share link", self)
        action.triggered.connect(
            lambda checked=False, share_link=link: self._copy_share_link(share_link)
        )
        menu.addAction(action)

    def _add_track_radio_action(self, menu: QMenu, track: Track) -> None:
        action = QAction("Start track radio", self)
        action.triggered.connect(
            lambda checked=False, selected_track=track: self._open_and_play_station(
                Station(id=f"track:{selected_track.id}", title=f"{selected_track.title} Radio")
            )
        )
        menu.addAction(action)

    def _add_album_radio_action(self, menu: QMenu, album: Album) -> None:
        action = QAction("Start album radio", self)
        action.triggered.connect(
            lambda checked=False, selected_album=album: self._open_and_play_station(
                Station(id=f"album:{selected_album.id}", title=f"{selected_album.title} Radio")
            )
        )
        menu.addAction(action)

    def _add_artist_radio_action(self, menu: QMenu, artist: Artist) -> None:
        action = QAction("Start artist radio", self)
        action.triggered.connect(
            lambda checked=False, selected_artist=artist: self._open_and_play_station(
                Station(id=f"artist:{selected_artist.id}", title=f"{selected_artist.name} Radio")
            )
        )
        menu.addAction(action)

    def _add_go_to_artist_actions(
        self,
        menu: QMenu,
        artist_ids: tuple[str, ...],
        artist_names: tuple[str, ...],
    ) -> None:
        artists = [
            Artist(id=artist_id, name=artist_name)
            for artist_id, artist_name in zip(artist_ids, artist_names, strict=False)
        ]
        if not artists:
            return
        if len(artists) == 1:
            artist = artists[0]
            action = QAction("Go to artist", self)
            action.triggered.connect(
                lambda checked=False, selected_artist=artist: self._library_controller.open_artist(
                    selected_artist
                )
            )
            menu.addAction(action)
            return
        submenu = menu.addMenu("Go to artist")
        for artist in artists:
            action = QAction(artist.name, self)
            action.triggered.connect(
                lambda checked=False, selected_artist=artist: self._library_controller.open_artist(
                    selected_artist
                )
            )
            submenu.addAction(action)

    def _open_and_play_station(self, station: Station) -> None:
        self._controller.play_station(station.id)

    def _copy_share_link(self, link: str) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(link)
        self._status_label.setText(f"Copied share link: {link}")

    def _track_share_link(self, track: Track) -> str | None:
        if track.album_id:
            return f"https://music.yandex.ru/album/{track.album_id}/track/{track.id}"
        return None

    def _album_share_link(self, album: Album) -> str:
        return f"https://music.yandex.ru/album/{album.id}"

    def _artist_share_link(self, artist: Artist) -> str:
        return f"https://music.yandex.ru/artist/{artist.id}"

    def _playlist_share_link(self, playlist: Playlist) -> str | None:
        if playlist.owner_id:
            return f"https://music.yandex.ru/users/{playlist.owner_id}/playlists/{playlist.id}"
        return f"https://music.yandex.ru/playlist/{playlist.id}"

    def _station_share_link(self, station: Station) -> str | None:
        if station.id.startswith("artist:"):
            return f"https://music.yandex.ru/artist/{station.id.split(':', 1)[1]}"
        if station.id.startswith("album:"):
            return f"https://music.yandex.ru/album/{station.id.split(':', 1)[1]}"
        if station.id.startswith("track:"):
            return None
        return None

    def _render_artwork(self, track: Track) -> None:
        if not track.artwork_ref:
            self._clear_artwork()
            self._set_accent_color("#526ee8")
            return

        artwork_url = self._container.services.artwork_cache.normalize_url(track.artwork_ref)
        if artwork_url is None:
            self._clear_artwork()
            self._set_accent_color("#526ee8")
            return

        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        cached_accent = self._container.services.artwork_cache.load_accent_color(cache_path)
        if cached_accent:
            self._set_accent_color(cached_accent)
        if cache_path.exists():
            self._set_artwork_pixmap(cache_path)
            return

        self._pending_artwork_track_id = track.id
        request = QNetworkRequest(QUrl(artwork_url))
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setAttribute(QNetworkRequest.Attribute.HttpPipeliningAllowedAttribute, False)
        reply = self._artwork_manager.get(request)
        reply.setProperty("track_id", track.id)
        reply.setProperty("cache_path", str(cache_path))

    def _handle_artwork_downloaded(self, reply: QNetworkReply) -> None:
        thumb_artwork_url = reply.property("thumb_artwork_url")
        if isinstance(thumb_artwork_url, str) and thumb_artwork_url:
            self._handle_thumb_downloaded(reply, thumb_artwork_url)
            return

        track_id = reply.property("track_id")
        cache_path = Path(str(reply.property("cache_path")))
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return

        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data:
            return
        try:
            self._container.services.artwork_cache.save_bytes(cache_path, data)
        except DomainError as exc:
            self._container.logger.warning("Artwork cache write failed: %s", exc)
            return
        if track_id == self._pending_artwork_track_id:
            self._set_artwork_pixmap(cache_path)

    def _handle_thumb_downloaded(self, reply: QNetworkReply, artwork_url: str) -> None:
        cache_path = Path(str(reply.property("cache_path")))
        labels = self._pending_thumb_labels.pop(artwork_url, [])
        self._active_thumb_downloads = max(0, self._active_thumb_downloads - 1)
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            self._start_next_thumb_downloads()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data:
            self._start_next_thumb_downloads()
            return
        try:
            self._container.services.artwork_cache.save_bytes(cache_path, data)
        except DomainError as exc:
            self._container.logger.warning("Artwork thumb cache write failed: %s", exc)
            self._start_next_thumb_downloads()
            return
        pixmap = QPixmap(str(cache_path))
        if pixmap.isNull():
            self._start_next_thumb_downloads()
            return
        for label in labels:
            if shiboken6.isValid(label):
                self._set_thumb_pixmap(label, pixmap)
        self._start_next_thumb_downloads()

    def _set_artwork_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._clear_artwork()
            return
        accent = self._container.services.artwork_cache.load_accent_color(path)
        if accent is None:
            accent = self._extract_accent_color(pixmap)
            try:
                self._container.services.artwork_cache.save_accent_color(path, accent)
            except DomainError as exc:
                self._container.logger.warning("Artwork accent cache write failed: %s", exc)
        self._set_accent_color(accent)
        self._artwork_label.setPixmap(
            pixmap.scaled(
                self._artwork_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _clear_artwork(self) -> None:
        self._pending_artwork_track_id = None
        self._artwork_label.clear()
        self._artwork_label.setText("No cover")

    def _extract_accent_color(self, pixmap: QPixmap) -> str:
        image = pixmap.toImage().scaled(
            24,
            24,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        samples: list[tuple[float, float, float]] = []
        for y in range(image.height()):
            for x in range(image.width()):
                color = QColor(image.pixel(x, y))
                if color.alpha() < 180:
                    continue
                r, g, b = color.redF(), color.greenF(), color.blueF()
                h, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
                if saturation < 0.12 or lightness < 0.12 or lightness > 0.88:
                    continue
                samples.append((h, lightness, saturation))
        if not samples:
            return "#526ee8"
        hue, lightness, saturation = max(samples, key=lambda item: item[2] * 1.4 + item[1])
        saturation = min(0.65, max(0.25, saturation))
        lightness = min(0.70, max(0.35, lightness))
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        candidate = QColor.fromRgbF(r, g, b).name()
        return candidate if self._has_usable_accent_contrast(candidate) else "#526ee8"

    def _has_usable_accent_contrast(self, color: str) -> bool:
        qcolor = QColor(color)
        luminance = (
            0.2126 * qcolor.redF()
            + 0.7152 * qcolor.greenF()
            + 0.0722 * qcolor.blueF()
        )
        background = 0.055
        contrast = (max(luminance, background) + 0.05) / (min(luminance, background) + 0.05)
        return contrast >= 2.2

    def _set_accent_color(self, color: str) -> None:
        if color == self._accent_color:
            return
        self._accent_color = color
        self._apply_theme()

    def _accent_text_color(self) -> str:
        accent = QColor(self._accent_color)
        luminance = (
            0.2126 * accent.redF()
            + 0.7152 * accent.greenF()
            + 0.0722 * accent.blueF()
        )
        return "#101116" if luminance > 0.58 else "#ffffff"

    def _format_year(self, year: int | None) -> str:
        return f" ({year})" if year else ""

    def _format_audio_info(self, codec: str | None, bitrate: int | None) -> str:
        if not codec or bitrate is None:
            return ""
        codec_label = self._compact_codec(codec)
        kbps = bitrate if bitrate < 1000 else round(bitrate / 1000)
        return f"{codec_label}:{max(1, kbps)}"

    def _compact_codec(self, codec: str | None) -> str:
        if not codec:
            return "?"
        normalized = codec.lower()
        for label in ("mp3", "aac", "flac", "opus", "vorbis", "alac"):
            if label in normalized:
                return label
        if "mpeg" in normalized and "layer 3" in normalized:
            return "mp3"
        return normalized.split(" ", 1)[0].split(",", 1)[0]

    def _queue_duration_ms(self, queue: tuple[QueueItem, ...]) -> int:
        return sum(item.track.duration_ms or 0 for item in queue)

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
        accent = self._accent_color
        accent_text = self._accent_text_color()
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background: #101116;
                color: #eceef7;
                font-family: "Avenir Next", "Segoe UI", sans-serif;
                font-size: 12px;
            }}
            QDialog {{
                background: #101116;
            }}
            QFrame#top-bar {{
                background: transparent;
                border: 0;
            }}
            QFrame {{
                background: transparent;
                border: 0;
                border-radius: 0;
            }}
            QFrame#sidebar {{
                background: #121520;
                border-radius: 14px;
            }}
            QLabel {{
                border: 0;
                background: transparent;
            }}
            QLabel#now-playing {{
                color: #aeb6d6;
                font-weight: 600;
            }}
            QLabel#track-title {{
                color: #ffffff;
                font-size: 28px;
                font-weight: 800;
            }}
            QLabel#track-artist {{
                color: #d8dceb;
                font-size: 16px;
                font-weight: 600;
            }}
            QLabel#track-album, QLabel#track-tech, QLabel#playback-state,
            QLabel#inline-status, QLabel#queue-summary {{
                color: #9ba4c2;
            }}
            QLabel#track-tech {{
                font-size: 11px;
                font-weight: 650;
                color: #7f88a8;
                font-family: "Menlo", "Monaco", "Courier New", monospace;
            }}
            QLabel#queue-audio-info, QLabel#seek-label {{
                color: #d7dcea;
                font-family: "Menlo", "Monaco", "Courier New", monospace;
                font-size: 11px;
            }}
            QLabel#queue-audio-info {{
                color: #9ba4c2;
            }}
            QLabel#auth-label {{
                color: #aeb6d6;
                font-size: 11px;
                font-weight: 650;
            }}
            QLabel#browser-title {{
                color: #ffffff;
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#nav-section {{
                color: #7f88a8;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 1px;
                text-transform: uppercase;
            }}
            QLabel#album-art {{
                background: #0b0c11;
                border: 0;
                border-radius: 16px;
                color: #737b99;
            }}
            QLabel#art-thumb {{
                background: #1a1e2b;
                border-radius: 6px;
                color: #737b99;
            }}
            QLabel#queue-title, QLabel#browser-art-title {{
                color: #eef1fb;
                font-weight: 650;
            }}
            QLabel#queue-title {{
                qproperty-wordWrap: false;
            }}
            QLabel#queue-subtitle, QLabel#browser-art-subtitle {{
                color: #8f98b5;
                font-size: 11px;
            }}
            QLabel#queue-subtitle {{
                qproperty-wordWrap: false;
            }}
            QLabel#queue-duration {{
                color: #d7dcea;
                font-family: "Menlo", "Monaco", "Courier New", monospace;
                font-size: 11px;
            }}
            QWidget#queue-row-active {{
                background: rgba(82, 110, 232, 0.22);
                border-radius: 8px;
            }}
            QWidget#queue-row-selected {{
                background: {accent};
                border-radius: 8px;
            }}
            QWidget#queue-row-selected QLabel#queue-title,
            QWidget#queue-row-selected QLabel#queue-subtitle,
            QWidget#queue-row-selected QLabel#queue-duration {{
                color: {accent_text};
            }}
            QWidget#queue-row {{
                background: transparent;
            }}
            QWidget#queue-text, QWidget#browser-art-text {{
                background: transparent;
            }}
            QFrame#queue-separator {{
                background: #2b2f3d;
                border: 0;
            }}
            QFrame#settings-popup, QFrame#volume-popup {{
                background: #101116;
                border: 0;
                border-radius: 12px;
            }}
            QFrame#settings-popup {{
                background: #101116;
                border: 1px solid {accent};
                border-radius: 12px;
            }}
            QFrame#volume-popup {{
                background: #101116;
                border: 1px solid {accent};
                border-radius: 14px;
            }}
            QPushButton {{
                background: #222637;
                border: 1px solid #33394e;
                border-radius: 9px;
                color: #eef1fb;
                padding: 4px 8px;
                font-weight: 650;
            }}
            QPushButton:hover {{
                border-color: {accent};
                background: #2a3044;
            }}
            QPushButton:checked {{
                background: {accent};
                color: {accent_text};
            }}
            QPushButton#play-button {{
                background: qradialgradient(cx:0.5, cy:0.45, radius:0.8,
                    fx:0.5, fy:0.4, stop:0 {accent}, stop:1 #252a3f);
                border: 1px solid {accent};
                border-radius: 16px;
            }}
            QPushButton#my-wave-button {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent}, stop:1 #2c355f);
                border-color: {accent};
                font-size: 13px;
                padding: 8px;
            }}
            QPushButton#panel-close-button {{
                padding: 0;
                border-radius: 10px;
                font-size: 18px;
            }}
            QPushButton#queue-icon-button {{
                padding: 0;
                border-radius: 10px;
                font-size: 16px;
            }}
            QPushButton#quality-option {{
                background: #222637;
                border: 1px solid #33394e;
                color: #eef1fb;
                padding: 6px 11px;
                border-radius: 10px;
                min-width: 38px;
            }}
            QPushButton#quality-option:hover {{
                border-color: {accent};
                background: #2a3044;
            }}
            QPushButton#quality-option:checked {{
                background: {accent};
                border-color: {accent};
                color: {accent_text};
            }}
            QLineEdit, QComboBox {{
                background: #0f1118;
                border: 1px solid #30364a;
                border-radius: 8px;
                color: #eef1fb;
                padding: 4px 7px;
            }}
            QListWidget {{
                background: #0f1118;
                border: 0;
                border-radius: 10px;
                alternate-background-color: #131723;
                padding: 4px;
            }}
            QListWidget::item {{
                border-radius: 7px;
                padding: 5px;
            }}
            QListWidget#queue-list::item {{
                padding: 0px;
            }}
            QListWidget::item:selected {{
                background: {accent};
                color: {accent_text};
            }}
            QTabWidget::pane {{
                border: 0;
                border-radius: 8px;
            }}
            QTabBar::tab {{
                background: #171a25;
                color: #b7bfd8;
                padding: 5px 9px;
                border-top-left-radius: 9px;
                border-top-right-radius: 9px;
            }}
            QTabBar::tab:selected {{
                color: {accent_text};
                background: {accent};
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: #252a3a;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: #ffffff;
                border: 2px solid {accent};
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider#volume-slider {{
                background: transparent;
                border: 0;
            }}
            QSlider#volume-slider:hover {{
                background: transparent;
                border: 0;
            }}
            QSlider#volume-slider::groove:vertical {{
                width: 8px;
                background: #222637;
                border-radius: 4px;
            }}
            QSlider#volume-slider::sub-page:vertical {{
                background: #222637;
                border-radius: 4px;
            }}
            QSlider#volume-slider::add-page:vertical {{
                background: {accent};
                border-radius: 4px;
            }}
            QSlider#volume-slider::handle:vertical {{
                background: {accent};
                border: 2px solid #101116;
                height: 16px;
                margin: 0 -7px;
                border-radius: 9px;
            }}
            QSlider#volume-slider:focus {{
                outline: 0;
                border: 0;
                background: transparent;
            }}
            QScrollBar {{
                width: 0;
                height: 0;
                background: transparent;
            }}
            """
        )
        if self._browser_dialog is not None:
            self._browser_dialog.setStyleSheet(self.styleSheet())
        if self._settings_popup is not None:
            self._settings_popup.setStyleSheet(self.styleSheet())
        if self._volume_popup is not None:
            self._volume_popup.setStyleSheet(self.styleSheet())

    def _plain_frame(self, name: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(name)
        return frame

    def _panel_frame(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setObjectName(title.lower().replace(" ", "-"))

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 0, 8, 2)
        layout.setSpacing(2)
        return frame

    def _panel_label(self, text: str, *, align_right: bool = False) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(
            Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft
        )
        return label

    def _icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(create_icon(icon_name))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(34, 32)
        return button

    def _format_ms(self, value: int | None) -> str:
        if value is None:
            return "0:00"
        minutes, remainder = divmod(value // 1000, 60)
        return f"{minutes}:{remainder:02d}"

    def _fit_track_text_labels(self) -> None:
        self._fit_track_text_label(self._track_title_label, min_point_size=20, max_lines=3)
        self._fit_track_text_label(self._track_meta_label, min_point_size=12, max_lines=3)
        self._fit_track_text_label(self._track_album_label, min_point_size=11, max_lines=3)

    def _fit_track_text_label(
        self,
        label: QLabel,
        *,
        min_point_size: int,
        max_lines: int,
    ) -> None:
        base_size = self._track_label_base_sizes.get(label)
        if base_size is None:
            return
        text = label.text().strip()
        font = QFont(label.font())
        font.setPointSize(base_size)
        label.setFont(font)
        if not text:
            return

        available_width = max(80, label.contentsRect().width() or label.width())
        available_height = max(1, label.maximumHeight())
        flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap)

        for point_size in range(base_size, min_point_size - 1, -1):
            font.setPointSize(point_size)
            metrics = label.fontMetrics() if point_size == font.pointSize() else None
            label.setFont(font)
            metrics = label.fontMetrics() if metrics is None else metrics
            rect = metrics.boundingRect(0, 0, available_width, 4096, flags, text)
            fits_height = rect.height() <= available_height
            fits_lines = rect.height() <= metrics.lineSpacing() * max_lines
            if fits_height and fits_lines:
                return

        font.setPointSize(min_point_size)
        label.setFont(font)
