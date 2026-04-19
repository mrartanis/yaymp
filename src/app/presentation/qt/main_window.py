from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.container import AppContainer
from app.presentation.qt.playback_controller import PlaybackController


class MainWindow(QMainWindow):
    def __init__(self, *, container: AppContainer) -> None:
        super().__init__()
        self._container = container
        self._controller = PlaybackController(
            playback_service=container.services.playback_service,
            logger=container.logger,
        )
        self.setWindowTitle("YAYMP")
        self.resize(1280, 820)
        self._build_ui()
        self._wire_controller()
        self._controller.initialize()

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
        self._backend_label = self._panel_label("Backend: bootstrapping", align_right=True)
        layout.addWidget(self._backend_label)
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
        for text in ("Home", "Search", "My Tracks", "Playlists"):
            layout.addWidget(self._panel_label(text))
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
        layout.addWidget(self._track_title_label, 0, 0)
        layout.addWidget(self._track_meta_label, 1, 0)
        layout.addWidget(self._playback_state_label, 2, 0)
        layout.setRowStretch(2, 1)
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
        self._previous_button.clicked.connect(self._controller.previous)
        self._play_button.clicked.connect(self._controller.play)
        self._pause_button.clicked.connect(self._controller.pause)
        self._next_button.clicked.connect(self._controller.next)
        self._seek_slider.sliderReleased.connect(self._apply_seek)
        self._volume_slider.valueChanged.connect(self._controller.set_volume)
        self._queue_list.itemDoubleClicked.connect(self._select_queue_item)

    def _apply_seek(self) -> None:
        self._controller.seek(self._seek_slider.value())

    def _select_queue_item(self, item: QListWidgetItem) -> None:
        row = self._queue_list.row(item)
        self._controller.select_index(row)

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
        self._backend_label.setText(
            f"Backend: {self._container.services.playback_engine.__class__.__name__}"
        )
        self._status_label.setText("Playback core active")
        self._queue_status_label.setText(
            f"Queue {len(queue)} items | active index {state.active_index}"
        )
        self._render_queue(snapshot)

    def _render_queue(self, snapshot) -> None:
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

    def _render_error(self, message: str) -> None:
        self._status_label.setText(f"Playback error: {message}")

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
