from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.main_window import MainWindow
from app.presentation.qt.main_window_layout import MainWindowLayoutMixin


class _TransportHarness(MainWindowLayoutMixin, QWidget):
    _PLAYER_MIN_WIDTH = 560
    _PLAYER_MAX_WIDTH = 700
    _COMPACT_ARTWORK_SIZE = 300
    _WIDE_ARTWORK_SIZE = 512
    _PLAYER_PANEL_COMPACT_HEIGHT = 434

    def __init__(self) -> None:
        super().__init__()
        self._player_panel_frame = None
        self._sidebar_popup = None
        self._sidebar_panel = None
        self._sidebar_host = None
        self._sidebar_host_layout = None
        self._sidebar_docked = False
        self._left_zone = None
        self._left_zone_layout = None
        self._browser_host = None
        self._browser_host_layout = None
        self._browser_docked = False
        self._browser_dialog = None
        self._browser_panel = None
        self._browser_close_button = None
        self._queue_host = None
        self._queue_host_layout = None
        self._main_column_widget = None
        self._main_column_layout = None
        self._player_queue_wide = False
        self._track_label_base_sizes: dict[QLabel, int] = {}

    def _panel_frame(self, title: str):
        del title
        frame = QWidget(self)
        frame.setLayout(QVBoxLayout())
        return frame

    def _panel_label(self, text: str, *, align_right: bool = False) -> QLabel:
        del align_right
        return QLabel(text, self)

    def _build_transport_bar(self):
        return MainWindow._build_transport_bar(self)

    def _apply_transport_visual_mode(self, *, wide: bool) -> None:
        return MainWindow._apply_transport_visual_mode(self, wide=wide)

    def _render_play_pause_button(self, status) -> None:
        return MainWindow._render_play_pause_button(self, status)

    def _render_current_track_like_button(self, is_liked: bool) -> None:
        return MainWindow._render_current_track_like_button(self, is_liked)

    def _render_current_track_dislike_button(self, is_disliked: bool) -> None:
        return MainWindow._render_current_track_dislike_button(self, is_disliked)

    def _format_ms(self, value: int | None) -> str:
        return MainWindow._format_ms(self, value)

    def _icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton(self)
        button.setIconSize(QSize(20, 20))
        self._set_button_icon(button, icon_name)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(34, 32)
        return button

    def _set_button_icon(
        self,
        button: QPushButton,
        icon_name: str,
        *,
        color: str = "#ffffff",
    ) -> None:
        target_size = max(1, button.iconSize().width(), button.iconSize().height())
        button.setIcon(create_icon(icon_name, color=color, size=target_size))

    def _build_settings_popup(self) -> None:
        return None

    def _build_volume_popup(self) -> None:
        return None

    def _fit_track_text_labels(self) -> None:
        return None

    def _t(self, key: str, **params: object) -> str:
        return key.format(**params) if params else key

    def _theme_icon_color(self) -> str:
        return "#ffffff"

    def _accent_text_color(self) -> str:
        return "#ffffff"


def test_transport_row_places_dislike_and_like_around_main_controls(qtbot) -> None:
    window = _TransportHarness()
    qtbot.addWidget(window)

    transport = MainWindow._build_transport_bar(window)

    widgets = [
        transport.itemAt(index).widget()
        for index in range(transport.count())
        if isinstance(transport.itemAt(index).widget(), QPushButton)
    ]

    assert widgets == [
        window._dislike_track_button,
        window._previous_button,
        window._play_pause_button,
        window._next_button,
        window._like_track_button,
    ]
    assert window._dislike_track_button.size().width() == 32
    assert window._previous_button.size().width() == 34
    assert window._play_pause_button.size().width() == 46
    assert window._next_button.size().width() == 34
    assert window._like_track_button.size().width() == 32


def test_progress_row_keeps_only_seek_timer_and_volume(qtbot) -> None:
    window = _TransportHarness()
    qtbot.addWidget(window)

    window._build_player_panel()

    progress_layout = window._progress_widget.layout()
    widgets = [
        progress_layout.itemAt(index).widget()
        for index in range(progress_layout.count())
        if progress_layout.itemAt(index).widget() is not None
    ]

    assert widgets == [
        window._seek_slider,
        window._seek_label,
        window._volume_button,
    ]
    assert isinstance(window._like_track_button, QPushButton)
    assert isinstance(window._dislike_track_button, QPushButton)


def test_progress_row_moves_volume_left_only_in_wide_mode(qtbot) -> None:
    window = _TransportHarness()
    qtbot.addWidget(window)

    window._build_player_panel()
    window._configure_player_right_layout(wide=True)

    progress_layout = window._progress_widget.layout()
    widgets = [
        progress_layout.itemAt(index).widget()
        for index in range(progress_layout.count())
        if progress_layout.itemAt(index).widget() is not None
    ]

    assert widgets == [
        window._wide_progress_left_slot,
        window._seek_slider,
        window._wide_progress_right_slot,
    ]


def test_wide_progress_uses_symmetric_side_slots(qtbot) -> None:
    window = _TransportHarness()
    qtbot.addWidget(window)

    window._build_player_panel()
    window._configure_player_right_layout(wide=True)

    assert window._wide_progress_left_slot.width() == window._wide_progress_right_slot.width()
    assert window._wide_progress_left_slot.width() == window._seek_label.width()

    left_layout = window._wide_progress_left_slot.layout()
    right_layout = window._wide_progress_right_slot.layout()

    assert left_layout.itemAt(0).widget() is window._volume_button
    assert right_layout.itemAt(0).widget() is window._seek_label


def test_format_ms_drops_to_tens_for_very_long_tracks() -> None:
    window = _TransportHarness()

    assert window._format_ms(None) == "0:00"
    assert window._format_ms(5 * 60 * 1000 + 7 * 1000) == "5:07"
    assert window._format_ms(99 * 60 * 1000 + 59 * 1000) == "99:59"
    assert window._format_ms(100 * 60 * 1000) == "100:0"
    assert window._format_ms(123 * 60 * 1000 + 45 * 1000) == "123:4"
