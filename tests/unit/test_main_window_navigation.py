from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from app.domain import Track
from app.presentation.qt.main_window import MainWindow
from app.presentation.qt.main_window_windowing import MainWindowWindowingMixin


class _LibraryControllerStub:
    def __init__(self) -> None:
        self.opened_artist = None
        self.opened_album = None

    def open_artist(self, artist) -> None:
        self.opened_artist = artist

    def open_album(self, album) -> None:
        self.opened_album = album


class _NavigationHarness(MainWindowWindowingMixin, QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._library_controller = _LibraryControllerStub()
        self._current_track = None
        self._track_meta_label = QLabel("artist", self)
        self._track_album_label = QLabel("album", self)
        self._track_meta_label.installEventFilter(self)
        self._track_album_label.installEventFilter(self)

    def _handle_frame_resize_event(self, watched: object, event) -> bool:
        del watched, event
        return False

    def _open_current_track_primary_artist(self) -> bool:
        return MainWindow._open_current_track_primary_artist(self)

    def _open_current_track_album(self) -> bool:
        return MainWindow._open_current_track_album(self)


def test_clicking_track_meta_label_opens_primary_artist(qtbot) -> None:
    window = _NavigationHarness()
    qtbot.addWidget(window)
    window._current_track = Track(
        id="track-1",
        title="Track",
        artists=("Artist A", "Artist B"),
        artist_ids=("artist-a", "artist-b"),
        album_id="album-1",
        album_title="Album",
    )

    qtbot.mouseClick(window._track_meta_label, Qt.MouseButton.LeftButton)

    assert window._library_controller.opened_artist is not None
    assert window._library_controller.opened_artist.id == "artist-a"
    assert window._library_controller.opened_artist.name == "Artist A"


def test_clicking_track_album_label_opens_album(qtbot) -> None:
    window = _NavigationHarness()
    qtbot.addWidget(window)
    window._current_track = Track(
        id="track-1",
        title="Track",
        artists=("Artist",),
        artist_ids=("artist-1",),
        album_id="album-1",
        album_title="Album",
        album_year=2024,
    )

    qtbot.mouseClick(window._track_album_label, Qt.MouseButton.LeftButton)

    assert window._library_controller.opened_album is not None
    assert window._library_controller.opened_album.id == "album-1"
    assert window._library_controller.opened_album.title == "Album"
    assert window._library_controller.opened_album.year == 2024
