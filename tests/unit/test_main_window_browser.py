from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QListView, QVBoxLayout, QWidget

from app.domain import Album, Artist
from app.presentation.qt.library_controller import BrowserContent, BrowserItem
from app.presentation.qt.main_window_browser import (
    MainWindowBrowserMixin,
    _ElidedSingleLineLabel,
    _ElidedWrapLabel,
)


class _BrowserHarness(MainWindowBrowserMixin, QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.thumb_requests: list[tuple[str, int, int | None]] = []
        self.saved_browser_view_modes: list[str] = []
        self._container = SimpleNamespace(
            services=SimpleNamespace(
                artwork_cache=SimpleNamespace(
                    normalize_url=lambda artwork_ref: f"url:{artwork_ref}" if artwork_ref else None,
                    cache_path_for_url=lambda artwork_url: None,
                ),
                settings_service=SimpleNamespace(
                    save_browser_view_mode=self.saved_browser_view_modes.append
                ),
            )
        )
        self._library_controller = SimpleNamespace(can_go_back=lambda: False)
        self._browser_auto_open_enabled = False
        self._browser_view_mode = self._BROWSER_VIEW_MODE_CARDS
        self._current_browser_content = None
        self._loading_more_content = False
        self._updating_browser_tabs = False
        self._browser_tab_ids = ()
        self._pending_thumb_labels = {}
        self._pending_thumb_callbacks = {}
        self._queued_thumb_downloads = []
        self._active_thumb_downloads = 0
        self._max_active_thumb_downloads = 4
        self._browser_panel = self._build_browser_panel()

    def _panel_frame(self, title: str) -> QFrame:
        del title
        frame = QFrame(self)
        frame.setLayout(QVBoxLayout())
        return frame

    def _panel_label(self, text: str, *, align_right: bool = False) -> QLabel:
        del align_right
        return QLabel(text, self)

    def _show_browser_panel(self) -> None:
        return

    def _thumb_pixmap_for_url(
        self,
        artwork_url: str,
        *,
        size: int,
        source_max_edge: int | None = None,
    ):
        self.thumb_requests.append((artwork_url, size, source_max_edge))
        return None

    def _queue_thumb_download(self, artwork_url, cache_path, label=None, *, on_ready=None) -> None:
        del artwork_url, cache_path, label, on_ready
        return

    def _t(self, key: str, **params: object) -> str:
        return key.format(**params) if params else key


def test_render_content_uses_card_grid_for_album_lists(qtbot) -> None:
    window = _BrowserHarness()
    qtbot.addWidget(window)
    content = BrowserContent(
        title="Albums",
        items=(
            BrowserItem(
                kind="album",
                title="A",
                subtitle="1999",
                payload=Album(id="1", title="A", artwork_ref="art-a"),
            ),
            BrowserItem(
                kind="album",
                title="B",
                subtitle="2000",
                payload=Album(id="2", title="B", artwork_ref="art-b"),
            ),
        ),
    )

    window._render_content(content)

    assert window._content_list.viewMode() == QListView.ViewMode.IconMode
    assert window._content_list.flow() == QListView.Flow.LeftToRight
    assert window._content_list.verticalScrollMode() == QListView.ScrollMode.ScrollPerPixel
    assert window._content_list.alternatingRowColors() is False
    assert window._content_list.uniformItemSizes() is True
    assert "padding: 0px" in window._content_list.styleSheet()
    card = window._content_list.itemWidget(window._content_list.item(0))
    assert card.objectName() == "browser-album-card"
    assert card.size() == window._content_list.gridSize()
    title = card.findChild(_ElidedWrapLabel, "browser-album-card-title")
    assert title is not None
    assert title.height() == 48
    assert title.alignment() == Qt.AlignmentFlag.AlignCenter
    subtitle = card.findChild(_ElidedSingleLineLabel, "browser-album-card-subtitle")
    assert subtitle is not None
    assert subtitle.alignment() == Qt.AlignmentFlag.AlignCenter
    assert window.thumb_requests[0] == ("url:art-a", 176, 256)


def test_render_content_keeps_list_mode_for_artist_lists(qtbot) -> None:
    window = _BrowserHarness()
    qtbot.addWidget(window)
    content = BrowserContent(
        title="Artists",
        items=(
            BrowserItem(
                kind="artist",
                title="Artist",
                subtitle="library.artist",
                payload=Artist(id="1", name="Artist"),
            ),
        ),
    )

    window._render_content(content)

    assert window._content_list.viewMode() == QListView.ViewMode.IconMode
    assert window._content_list.verticalScrollMode() == QListView.ScrollMode.ScrollPerPixel
    assert window._content_list.alternatingRowColors() is False
    assert "padding: 0px" in window._content_list.styleSheet()
    card = window._content_list.itemWidget(window._content_list.item(0))
    assert card.objectName() == "browser-album-card"
    assert window._content_list.item(0).sizeHint() == window._content_list.gridSize()
    subtitle = card.findChild(_ElidedSingleLineLabel, "browser-album-card-subtitle")
    assert subtitle is not None
    assert subtitle.text() == ""


def test_centered_grid_adds_balanced_side_insets(qtbot) -> None:
    window = _BrowserHarness()
    window.resize(900, 600)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    content = BrowserContent(
        title="Albums",
        items=tuple(
            BrowserItem(
                kind="album",
                title=f"A{index}",
                subtitle="1999",
                payload=Album(id=str(index), title=f"A{index}", artwork_ref=f"art-{index}"),
            )
            for index in range(4)
        ),
    )

    window._render_content(content)

    assert window._content_list.width() < window._content_list_host.width()
    assert window._content_list.width() >= window._content_list.gridSize().width()


def test_non_card_content_uses_item_scroll_mode(qtbot) -> None:
    window = _BrowserHarness()
    window.resize(900, 600)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    content = BrowserContent(
        title="Tracks",
        items=(
            BrowserItem(kind="track", title="Track 1", subtitle="Artist", payload=None),
        ),
    )

    window._render_content(content)

    assert window._content_list.viewMode() == QListView.ViewMode.ListMode
    assert window._content_list.verticalScrollMode() == QListView.ScrollMode.ScrollPerItem
    assert window._content_list.width() == window._content_list_host.width()
    assert window._browser_view_mode_widget.isHidden()


def test_browser_view_mode_toggle_switches_supported_pages(qtbot) -> None:
    window = _BrowserHarness()
    qtbot.addWidget(window)
    content = BrowserContent(
        title="Albums",
        items=(
            BrowserItem(
                kind="album",
                title="A",
                subtitle="1999",
                payload=Album(id="1", title="A", artwork_ref="art-a"),
            ),
        ),
    )

    window._render_content(content)

    assert not window._browser_view_mode_widget.isHidden()
    assert window._browser_view_cards_button.isChecked()
    assert window._content_list.viewMode() == QListView.ViewMode.IconMode

    window._set_browser_view_mode(window._BROWSER_VIEW_MODE_LIST)

    assert window._browser_view_list_button.isChecked()
    assert window._content_list.viewMode() == QListView.ViewMode.ListMode
    assert window.saved_browser_view_modes == ["list"]

    window._set_browser_view_mode(window._BROWSER_VIEW_MODE_CARDS)

    assert window._browser_view_cards_button.isChecked()
    assert window._content_list.viewMode() == QListView.ViewMode.IconMode
    assert window.saved_browser_view_modes == ["list", "cards"]


def test_elided_wrap_label_truncates_long_word_horizontally(qtbot) -> None:
    label = _ElidedWrapLabel(
        "pesnitrushchebnadezhdrazbitykhserdets - chast 1. Dnevniki odinochki",
        max_lines=2,
    )
    label.setFixedWidth(120)
    qtbot.addWidget(label)
    label.show()
    qtbot.waitExposed(label)

    assert "..." in label.text()
    assert len(label.text().splitlines()) <= 2


def test_elided_wrap_label_truncates_overflowing_multiline_text(qtbot) -> None:
    label = _ElidedWrapLabel(
        "Tribyut Egoru Letovu i ochen dlinnoe prodolzhenie nazvaniya alboma",
        max_lines=2,
    )
    label.setFixedWidth(150)
    qtbot.addWidget(label)
    label.show()
    qtbot.waitExposed(label)

    assert "..." in label.text()
    assert len(label.text().splitlines()) <= 2


def test_elided_single_line_label_truncates_long_text(qtbot) -> None:
    label = _ElidedSingleLineLabel("1999 | artist one, artist two, artist three | 42 tracks")
    label.setFixedWidth(120)
    qtbot.addWidget(label)
    label.show()
    qtbot.waitExposed(label)

    assert "..." in label.text()
