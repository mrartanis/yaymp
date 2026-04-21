from __future__ import annotations

from hashlib import sha256
from os import environ
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QPixmap, QShowEvent
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.container import AppContainer
from app.domain import Album, Artist, AudioQuality, Playlist, Station, Track
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
        self._current_track: Track | None = None
        self._current_browser_content: BrowserContent | None = None
        self._artwork_manager = QNetworkAccessManager(self)
        self._pending_artwork_track_id: str | None = None
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
        self._quality_combo = QComboBox()
        self._quality_combo.addItem("HQ", AudioQuality.HQ.value)
        self._quality_combo.addItem("SD", AudioQuality.SD.value)
        self._quality_combo.addItem("LQ", AudioQuality.LQ.value)
        self._quality_combo.setCurrentIndex(0)

        layout.addWidget(self._seek_slider, 1)
        layout.addWidget(self._seek_label)
        layout.addWidget(self._volume_slider)
        layout.addWidget(self._volume_label)
        layout.addWidget(self._quality_combo)
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
        self._track_album_label = self._panel_label("Album: unknown")
        self._track_technical_label = self._panel_label("Audio: unknown")
        self._artwork_label = QLabel("No cover")
        self._artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._artwork_label.setFixedSize(180, 180)
        self._artwork_label.setStyleSheet("border: 1px solid #777; border-radius: 4px;")
        self._playback_state_label = self._panel_label("Playback status: stopped")
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search Yandex Music")
        self._search_button = QPushButton("Search")
        self._recent_searches_combo = QComboBox()
        self._recent_searches_combo.setPlaceholderText("Recent searches")
        self._recent_searches_combo.addItem("Recent searches")
        self._browser_title_label = self._panel_label("Search")
        self._search_tabs = QTabWidget()
        self._search_tabs.addTab(QWidget(), "Tracks")
        self._search_tabs.addTab(QWidget(), "Playlists")
        self._search_tabs.addTab(QWidget(), "Albums")
        self._search_tabs.addTab(QWidget(), "Singles")
        self._search_tabs.addTab(QWidget(), "Compilations")
        self._search_tabs.addTab(QWidget(), "Artists")
        self._search_tabs.addTab(QWidget(), "Artist Radio")
        self._content_list = QListWidget()
        self._content_list.setAlternatingRowColors(True)
        self._track_id_input = QLineEdit()
        self._track_id_input.setPlaceholderText("Enter Yandex track id")
        self._play_track_button = QPushButton("Play Track ID")
        self._like_track_button = QPushButton("Like")
        self._unlike_track_button = QPushButton("Unlike")
        self._play_all_button = QPushButton("Play all")
        self._append_all_button = QPushButton("Append all")
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self._search_input, 1)
        search_row.addWidget(self._search_button)
        search_row.addWidget(self._recent_searches_combo)
        like_row = QHBoxLayout()
        like_row.setSpacing(8)
        like_row.addWidget(self._play_all_button)
        like_row.addWidget(self._append_all_button)
        like_row.addWidget(self._like_track_button)
        like_row.addWidget(self._unlike_track_button)
        like_row.addStretch(1)
        track_id_row = QHBoxLayout()
        track_id_row.setSpacing(8)
        track_id_row.addWidget(self._track_id_input, 1)
        track_id_row.addWidget(self._play_track_button)
        layout.addWidget(self._artwork_label, 0, 0, 4, 1)
        layout.addWidget(self._track_title_label, 0, 1)
        layout.addWidget(self._track_meta_label, 1, 1)
        layout.addWidget(self._track_album_label, 2, 1)
        layout.addWidget(self._track_technical_label, 3, 1)
        layout.addWidget(self._playback_state_label, 4, 0, 1, 2)
        layout.addLayout(search_row, 5, 0, 1, 2)
        layout.addWidget(self._browser_title_label, 6, 0, 1, 2)
        layout.addWidget(self._search_tabs, 7, 0, 1, 2)
        layout.addWidget(self._content_list, 8, 0, 1, 2)
        layout.addLayout(like_row, 9, 0, 1, 2)
        layout.addLayout(track_id_row, 10, 0, 1, 2)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(8, 1)
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
        self._library_controller.track_liked.connect(self._render_track_liked)
        self._library_controller.track_unliked.connect(self._render_track_unliked)
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
        self._like_track_button.clicked.connect(self._like_selected_or_current_track)
        self._unlike_track_button.clicked.connect(self._unlike_selected_or_current_track)
        self._play_all_button.clicked.connect(self._play_current_source)
        self._append_all_button.clicked.connect(self._append_current_source)
        self._search_tabs.currentChanged.connect(self._change_search_tab)
        self._quality_combo.currentIndexChanged.connect(self._apply_audio_quality)
        self._playback_poll_timer.timeout.connect(self._controller.refresh)
        self._artwork_manager.finished.connect(self._handle_artwork_downloaded)

    def _apply_seek(self) -> None:
        self._controller.seek(self._seek_slider.value())

    def _apply_audio_quality(self) -> None:
        raw_quality = self._quality_combo.currentData()
        if not isinstance(raw_quality, str):
            return
        quality = AudioQuality(raw_quality)
        self._container.services.music_service.set_audio_quality(quality)
        self._status_label.setText(f"Audio quality: {quality.name}")

    def _select_queue_item(self, item: QListWidgetItem) -> None:
        row = self._queue_list.row(item)
        self._controller.select_index(row)

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
            if browser_item.kind == "generated_playlist":
                self._controller.play_generated_playlist(payload.id, owner_id=payload.owner_id)
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
        self._library_controller.search_tracks(self._search_input.text())

    def _show_search(self) -> None:
        self._browser_title_label.setText("Search")
        self._content_list.clear()
        self._current_browser_content = None
        self._play_all_button.setEnabled(False)
        self._append_all_button.setEnabled(False)
        self._search_input.setFocus()

    def _change_search_tab(self, index: int) -> None:
        tabs = (
            "tracks",
            "playlists",
            "albums",
            "singles",
            "compilations",
            "artists",
            "artist_radio",
        )
        if index < 0 or index >= len(tabs):
            return
        self._library_controller.show_search_tab(tabs[index])

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
            self._current_track = current_item.track
            artists = ", ".join(current_item.track.artists)
            self._now_playing_label.setText(f"Now playing: {current_item.track.title}")
            self._track_title_label.setText(f"Track: {current_item.track.title}")
            self._track_meta_label.setText(f"Artist: {artists}")
            self._track_album_label.setText(
                "Album: "
                f"{current_item.track.album_title or 'Single'}"
                f"{self._format_year(current_item.track.album_year)}"
            )
            self._track_technical_label.setText(
                f"Audio: {self._format_audio_info(state.audio_codec, state.audio_bitrate)} | "
                f"{'liked' if current_item.track.is_liked else 'not liked'}"
            )
            self._render_artwork(current_item.track)
        else:
            self._current_track = None
            self._now_playing_label.setText("No active track")
            self._track_title_label.setText("Track: none")
            self._track_meta_label.setText("No metadata available")
            self._track_album_label.setText("Album: unknown")
            self._track_technical_label.setText("Audio: unknown")
            self._clear_artwork()

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
        self._current_browser_content = content
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
            if browser_item.kind == "section":
                widget_item.setFlags(widget_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._content_list.addItem(widget_item)
        self._content_list.blockSignals(False)
        can_play_source = bool(
            content.source_tracks
            and content.source_type in {"album", "artist", "generated_playlist", "playlist"}
            and content.source_id
        )
        self._play_all_button.setEnabled(can_play_source)
        self._append_all_button.setEnabled(can_play_source)

    def _render_library_error(self, message: str) -> None:
        self._status_label.setText(f"Library error: {message}")

    def _render_track_liked(self, track: Track) -> None:
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
        self._replace_content_track(track)
        self._status_label.setText(f"Liked: {track.title}")

    def _render_track_unliked(self, track: Track) -> None:
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
        self._replace_content_track(track)
        self._status_label.setText(f"Unliked: {track.title}")

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
        if content.source_type == "generated_playlist":
            self._controller.play_generated_playlist(
                content.source_id,
                owner_id=content.source_owner_id,
            )
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
            title = f"{'❤️ ' if track.is_liked else ''}{track.title}"
            text = title
            subtitle = ", ".join(track.artists)
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

    def _render_artwork(self, track: Track) -> None:
        if not track.artwork_ref:
            self._clear_artwork()
            return

        artwork_url = self._normalize_artwork_url(track.artwork_ref)
        if artwork_url is None:
            self._clear_artwork()
            return

        cache_path = self._artwork_cache_path(artwork_url)
        if cache_path.exists():
            self._set_artwork_pixmap(cache_path)
            return

        self._pending_artwork_track_id = track.id
        request = QNetworkRequest(QUrl(artwork_url))
        reply = self._artwork_manager.get(request)
        reply.setProperty("track_id", track.id)
        reply.setProperty("cache_path", str(cache_path))

    def _handle_artwork_downloaded(self, reply: QNetworkReply) -> None:
        track_id = reply.property("track_id")
        cache_path = Path(str(reply.property("cache_path")))
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return

        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data:
            return
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
        if track_id == self._pending_artwork_track_id:
            self._set_artwork_pixmap(cache_path)

    def _set_artwork_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._clear_artwork()
            return
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

    def _normalize_artwork_url(self, artwork_ref: str) -> str | None:
        value = artwork_ref.strip()
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value.replace("%%", "200x200")
        if value.startswith("//"):
            return f"https:{value}".replace("%%", "200x200")
        return f"https://{value}".replace("%%", "200x200")

    def _artwork_cache_path(self, artwork_url: str) -> Path:
        digest = sha256(artwork_url.encode("utf-8")).hexdigest()
        return self._container.config.cache_dir / "artwork" / f"{digest}.img"

    def _format_year(self, year: int | None) -> str:
        return f" ({year})" if year else ""

    def _format_audio_info(self, codec: str | None, bitrate: int | None) -> str:
        codec_label = codec or "unknown codec"
        if bitrate is None:
            return codec_label
        kbps = max(1, round(bitrate / 1000))
        return f"{codec_label}, {kbps} kbps"

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
