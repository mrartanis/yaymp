from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget

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

    def shutdown(self) -> None:
        return None


class _ShutdownStub:
    def shutdown(self) -> None:
        return None


class _NavigationHarness(MainWindowWindowingMixin, QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._system_media = _ShutdownStub()
        self._controller = _ShutdownStub()
        self._library_controller = _LibraryControllerStub()
        self._current_track = None
        self._pending_system_move = False
        self._system_move_calls = 0
        self._manual_window_drag_active = False
        self._manual_window_drag_origin = QPointF()
        self._title_bar = QLabel("title", self)
        self._title_drag_handle = QLabel("drag", self)
        self._player_panel_frame = QLabel("panel", self)
        self._track_metadata_zone = QLabel("meta-zone", self)
        self._artwork_label = QLabel("art", self)
        self._track_title_label = QLabel("title-label", self)
        self._track_meta_label = QLabel("artist", self)
        self._track_album_label = QLabel("album", self)
        self._title_bar.installEventFilter(self)
        self._title_drag_handle.installEventFilter(self)
        self._player_panel_frame.installEventFilter(self)
        self._track_metadata_zone.installEventFilter(self)
        self._artwork_label.installEventFilter(self)
        self._track_title_label.installEventFilter(self)
        self._track_meta_label.installEventFilter(self)
        self._track_album_label.installEventFilter(self)

    def _handle_frame_resize_event(self, watched: object, event) -> bool:
        del watched, event
        return False

    def _start_system_move(self) -> None:
        self._system_move_calls += 1

    def _open_current_track_primary_artist(self) -> bool:
        return MainWindow._open_current_track_primary_artist(self)

    def _open_current_track_album(self) -> bool:
        return MainWindow._open_current_track_album(self)


def _mouse_event(
    event_type: QEvent.Type,
    *,
    position: tuple[float, float] = (10, 10),
    global_position: tuple[float, float] = (10, 10),
    button: Qt.MouseButton = Qt.MouseButton.NoButton,
    buttons: Qt.MouseButton = Qt.MouseButton.NoButton,
) -> QMouseEvent:
    local = QPointF(*position)
    global_pos = QPointF(*global_position)
    return QMouseEvent(
        event_type,
        local,
        global_pos,
        global_pos,
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


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


def test_dragging_player_header_starts_system_move_on_mouse_move(qtbot) -> None:
    window = _NavigationHarness()
    qtbot.addWidget(window)
    threshold = QApplication.startDragDistance()

    press_event = _mouse_event(
        QEvent.Type.MouseButtonPress,
        global_position=(10, 10),
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.LeftButton,
    )
    small_move_event = _mouse_event(
        QEvent.Type.MouseMove,
        global_position=(10 + max(1, threshold - 1), 10),
        buttons=Qt.MouseButton.LeftButton,
    )
    move_event = _mouse_event(
        QEvent.Type.MouseMove,
        global_position=(10 + threshold + 2, 10),
        buttons=Qt.MouseButton.LeftButton,
    )
    release_event = _mouse_event(
        QEvent.Type.MouseButtonRelease,
        global_position=(10 + threshold + 2, 10),
        button=Qt.MouseButton.LeftButton,
        buttons=Qt.MouseButton.NoButton,
    )

    assert window.eventFilter(window._artwork_label, press_event) is True
    assert window._pending_system_move is True
    assert window._system_move_calls == 0

    assert window.eventFilter(window._artwork_label, small_move_event) is True
    assert window._pending_system_move is True
    assert window._system_move_calls == 0

    assert window.eventFilter(window._artwork_label, move_event) is True
    assert window._pending_system_move is False
    assert window._system_move_calls == 1

    assert window.eventFilter(window._artwork_label, release_event) is False
    assert window._pending_system_move is False
