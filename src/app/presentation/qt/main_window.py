from __future__ import annotations

from os import environ

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.container import AppContainer
from app.domain import Playlist, Station, Track
from app.domain.errors import DomainError
from app.presentation.qt.auth_dialog import AuthDialog
from app.presentation.qt.library_controller import BrowserContent, BrowserItem, LibraryController
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
        self._auth_dialog: AuthDialog | None = None
        self._auth_flow_checked = False
        self._playback_poll_timer = QTimer(self)
        self._playback_poll_timer.setInterval(1000)
        self.setWindowTitle("YAYMP")
        self.resize(1280, 820)
        self._build_ui()
        self._wire_controller()
        self._controller.initialize()
        self._library_controller.initialize()
        self._render_auth_state()
        self._playback_poll_timer.start()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._auth_flow_checked:
            return
        self._auth_flow_checked = True
        QTimer.singleShot(0, self._maybe_start_auth_flow)

    def _build_ui(self) -> None:
        root = QWidget(self)
        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(16, 16, 16, 16)
        outer_layout.setSpacing(12)

        outer_layout.addWidget(self._build_title_bar())
        outer_layout.addLayout(self._build_transport_bar())
        outer_layout.addLayout(self._build_body())
        outer_layout.addWidget(self._build_status_bar())

        self.setCentralWidget(root)

    def _build_title_bar(self) -> QFrame:
        frame = self._panel_frame("Now Playing")
        layout = frame.layout()
        assert layout is not None
        self._now_playing_label = self._panel_label("Ready to play demo queue")
        layout.addWidget(self._now_playing_label)
        layout.addStretch(1)
        self._auth_label = self._panel_label("Login required", align_right=True)
        layout.addWidget(self._auth_label)
        return frame

    def _build_transport_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        self._previous_button = QPushButton("Prev")
        self._play_button = QPushButton("Play")
        self._pause_button = QPushButton("Pause")
        self._next_button = QPushButton("Next")
        for button in (
            self._previous_button,
            self._play_button,
            self._pause_button,
            self._next_button,
        ):
            layout.addWidget(button)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 300_000)
        self._seek_slider.setSingleStep(1_000)
        self._seek_slider.setPageStep(10_000)
        self._seek_label = self._panel_label("0:00 / 0:00")
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(100)
        self._volume_label = self._panel_label("Volume 100%")

        layout.addWidget(self._seek_slider, 1)
        layout.addWidget(self._seek_label)
        layout.addWidget(self._volume_slider)
        layout.addWidget(self._volume_label)
        return layout

    def _build_body(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.addWidget(self._build_nav_panel(), 1)
        layout.addWidget(self._build_content_panel(), 3)
        layout.addWidget(self._build_queue_panel(), 1)
        return layout

    def _build_nav_panel(self) -> QFrame:
        frame = self._panel_frame("Navigation")
        layout = frame.layout()
        assert layout is not None
        self._search_nav_button = QPushButton("Search")
        self._liked_nav_button = QPushButton("My Tracks")
        self._playlists_nav_button = QPushButton("Playlists")
        self._my_wave_nav_button = QPushButton("My Wave")
        for button in (
            self._search_nav_button,
            self._liked_nav_button,
            self._playlists_nav_button,
            self._my_wave_nav_button,
        ):
            layout.addWidget(button)
        layout.addStretch(1)
        return frame

    def _build_content_panel(self) -> QFrame:
        frame = self._panel_frame("Content")
        base_layout = frame.layout()
        assert base_layout is not None
        layout = QGridLayout()
        self._track_title_label = self._panel_label("Track: Starter Signal")
        self._track_meta_label = self._panel_label("Artist and album metadata will appear here")
        self._playback_state_label = self._panel_label("Playback status: stopped")
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search Yandex Music")
        self._search_button = QPushButton("Search")
        self._recent_searches_combo = QComboBox()
        self._recent_searches_combo.setPlaceholderText("Recent searches")
        self._recent_searches_combo.addItem("Recent searches")
        self._browser_title_label = self._panel_label("Search")
        self._content_list = QListWidget()
        self._content_list.setAlternatingRowColors(True)
        self._track_id_input = QLineEdit()
        self._track_id_input.setPlaceholderText("Enter Yandex track id")
        self._play_track_button = QPushButton("Play Track ID")
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self._search_input, 1)
        search_row.addWidget(self._search_button)
        search_row.addWidget(self._recent_searches_combo)
        track_id_row = QHBoxLayout()
        track_id_row.setSpacing(8)
        track_id_row.addWidget(self._track_id_input, 1)
        track_id_row.addWidget(self._play_track_button)
        layout.addWidget(self._track_title_label, 0, 0)
        layout.addWidget(self._track_meta_label, 1, 0)
        layout.addWidget(self._playback_state_label, 2, 0)
        layout.addLayout(search_row, 3, 0)
        layout.addWidget(self._browser_title_label, 4, 0)
        layout.addWidget(self._content_list, 5, 0)
        layout.addLayout(track_id_row, 6, 0)
        layout.setRowStretch(5, 1)
        base_layout.addLayout(layout)
        return frame

    def _build_queue_panel(self) -> QFrame:
        frame = self._panel_frame("Queue")
        layout = frame.layout()
        assert layout is not None
        self._queue_list = QListWidget()
        layout.addWidget(self._queue_list)
        layout.addStretch(1)
        return frame

    def _build_status_bar(self) -> QFrame:
        frame = self._panel_frame("Status")
        layout = frame.layout()
        assert layout is not None
        self._status_label = self._panel_label("Playback core ready")
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self._queue_status_label = self._panel_label("Queue idle", align_right=True)
        layout.addWidget(self._queue_status_label)
        return frame

    def _wire_controller(self) -> None:
        self._controller.playback_changed.connect(self._render_snapshot)
        self._controller.playback_failed.connect(self._render_error)
        self._library_controller.content_changed.connect(self._render_content)
        self._library_controller.content_failed.connect(self._render_library_error)
        self._previous_button.clicked.connect(self._controller.previous)
        self._play_button.clicked.connect(self._controller.play)
        self._pause_button.clicked.connect(self._controller.pause)
        self._next_button.clicked.connect(self._controller.next)
        self._seek_slider.sliderReleased.connect(self._apply_seek)
        self._volume_slider.valueChanged.connect(self._controller.set_volume)
        self._queue_list.itemDoubleClicked.connect(self._select_queue_item)
        self._content_list.itemDoubleClicked.connect(self._open_content_item)
        self._search_button.clicked.connect(self._run_search)
        self._search_input.returnPressed.connect(self._run_search)
        self._recent_searches_combo.activated.connect(self._apply_recent_search)
        self._search_nav_button.clicked.connect(self._show_search)
        self._liked_nav_button.clicked.connect(self._library_controller.load_liked_tracks)
        self._playlists_nav_button.clicked.connect(self._library_controller.load_playlists)
        self._my_wave_nav_button.clicked.connect(self._start_my_wave)
        self._play_track_button.clicked.connect(self._play_track_by_id)
        self._track_id_input.returnPressed.connect(self._play_track_by_id)
        self._playback_poll_timer.timeout.connect(self._controller.refresh)

    def _apply_seek(self) -> None:
        self._controller.seek(self._seek_slider.value())

    def _select_queue_item(self, item: QListWidgetItem) -> None:
        row = self._queue_list.row(item)
        self._controller.select_index(row)

    def _open_content_item(self, item: QListWidgetItem) -> None:
        browser_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(browser_item, BrowserItem):
            return

        payload = browser_item.payload
        if browser_item.kind == "track" and isinstance(payload, Track):
            self._controller.play_track(payload)
            return
        if (
            browser_item.kind in {"playlist", "generated_playlist"}
            and isinstance(payload, Playlist)
        ):
            self._library_controller.open_playlist(payload)
            return
        if browser_item.kind == "station" and isinstance(payload, Station):
            self._library_controller.open_station(payload)

    def _run_search(self) -> None:
        self._library_controller.search_tracks(self._search_input.text())

    def _show_search(self) -> None:
        self._browser_title_label.setText("Search")
        self._content_list.clear()
        self._search_input.setFocus()

    def _start_my_wave(self) -> None:
        station = Station(id="user:onyourwave", title="My Wave")
        self._library_controller.open_station(station)
        self._controller.play_station(station.id)

    def _apply_recent_search(self, index: int) -> None:
        if index <= 0:
            return
        query = self._recent_searches_combo.itemText(index)
        self._search_input.setText(query)
        self._library_controller.search_tracks(query)

    def _render_snapshot(self, snapshot) -> None:
        current_item = snapshot.current_item
        queue = snapshot.queue
        state = snapshot.state

        if current_item is not None:
            artists = ", ".join(current_item.track.artists)
            self._now_playing_label.setText(f"Now playing: {current_item.track.title}")
            self._track_title_label.setText(f"Track: {current_item.track.title}")
            self._track_meta_label.setText(
                f"{artists} | {current_item.track.album_title or 'Single'}"
            )
        else:
            self._now_playing_label.setText("No active track")
            self._track_title_label.setText("Track: none")
            self._track_meta_label.setText("No metadata available")

        self._playback_state_label.setText(
            f"Playback status: {state.status.value} | repeat={state.repeat_mode.value}"
        )
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
        self._volume_label.setText(f"Volume {state.volume}%")
        self._status_label.setText("Playback core active")
        self._queue_status_label.setText(
            f"{self._container.services.playback_engine.__class__.__name__} | "
            f"queue {len(queue)} | active index {state.active_index}"
        )
        self._render_queue(snapshot)
        self._render_auth_state()

    def _render_queue(self, snapshot) -> None:
        scroll_bar = self._queue_list.verticalScrollBar()
        previous_scroll = scroll_bar.value()
        self._queue_list.blockSignals(True)
        self._queue_list.clear()
        for index, item in enumerate(snapshot.queue):
            row = f"{index + 1:02d}. {item.track.title}"
            widget_item = QListWidgetItem(row)
            if snapshot.state.active_index == index:
                widget_item.setSelected(True)
            self._queue_list.addItem(widget_item)
        if snapshot.state.active_index is not None:
            self._queue_list.setCurrentRow(snapshot.state.active_index)
        self._queue_list.blockSignals(False)
        scroll_bar.setValue(previous_scroll)

    def _render_error(self, message: str) -> None:
        self._status_label.setText(f"Playback error: {message}")

    def _render_auth_state(self) -> None:
        session = self._container.services.auth_service.current_session()
        if session is None:
            self._auth_label.setText("Login required")
            return
        username = session.display_name or session.user_id
        self._auth_label.setText(f"logged as {username}")

    def _render_content(self, content: BrowserContent) -> None:
        self._browser_title_label.setText(content.title)
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
            self._content_list.addItem(widget_item)
        self._content_list.blockSignals(False)

    def _render_library_error(self, message: str) -> None:
        self._status_label.setText(f"Library error: {message}")

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
            self._status_label.setText(f"Auth error: {exc}")
            return

        username = session.display_name or session.user_id
        self._status_label.setText(f"Authenticated as {username}")
        self._render_auth_state()

    def _clear_auth_dialog(self) -> None:
        self._auth_dialog = None

    def _play_track_by_id(self) -> None:
        track_id = self._track_id_input.text().strip()
        if not track_id:
            self._status_label.setText("Playback error: enter a Yandex track id")
            return
        self._controller.play_track_by_id(track_id)

    def _is_headless_test_run(self) -> bool:
        app = QApplication.instance()
        if app is not None and app.platformName() == "offscreen":
            return True
        return environ.get("QT_QPA_PLATFORM") == "offscreen"

    def _panel_frame(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setObjectName(title.lower().replace(" ", "-"))
        frame.setStyleSheet("QFrame { border: 1px solid #626262; border-radius: 6px; }")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(title_label)
        return frame

    def _panel_label(self, text: str, *, align_right: bool = False) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setAlignment(
            Qt.AlignmentFlag.AlignRight if align_right else Qt.AlignmentFlag.AlignLeft
        )
        return label

    def _format_ms(self, value: int | None) -> str:
        if value is None:
            return "0:00"
        minutes, remainder = divmod(value // 1000, 60)
        return f"{minutes}:{remainder:02d}"
