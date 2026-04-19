from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.bootstrap.container import AppContainer


class MainWindow(QMainWindow):
    def __init__(self, *, container: AppContainer) -> None:
        super().__init__()
        self._container = container
        self.setWindowTitle("YAYMP")
        self.resize(1280, 820)
        self._build_ui()

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
        layout.addWidget(self._panel_label("Classic desktop player shell"))
        layout.addStretch(1)
        layout.addWidget(
            self._panel_label(
                self._container.config.environment.upper(),
                align_right=True,
            )
        )
        return frame

    def _build_transport_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(8)
        for label in ("Prev", "Play", "Pause", "Next"):
            button = QPushButton(label)
            button.setEnabled(False)
            layout.addWidget(button)
        layout.addStretch(1)
        layout.addWidget(self._panel_label("Seek / Volume placeholders"))
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
        layout.addWidget(self._panel_label("Search results / library content placeholder"), 0, 0)
        layout.addWidget(self._panel_label("Artwork / metadata placeholder"), 1, 0)
        layout.setRowStretch(2, 1)
        base_layout.addLayout(layout)
        return frame

    def _build_queue_panel(self) -> QFrame:
        frame = self._panel_frame("Queue")
        layout = frame.layout()
        assert layout is not None
        layout.addWidget(self._panel_label("Upcoming tracks placeholder"))
        layout.addStretch(1)
        return frame

    def _build_status_bar(self) -> QFrame:
        frame = self._panel_frame("Status")
        layout = frame.layout()
        assert layout is not None
        layout.addWidget(self._panel_label("Bootstrap completed"))
        layout.addStretch(1)
        layout.addWidget(self._panel_label("No backend connected yet", align_right=True))
        return frame

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
