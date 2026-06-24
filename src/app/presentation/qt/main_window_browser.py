from __future__ import annotations

from pathlib import Path

import shiboken6
from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QFontMetrics, QPixmap, QTextLayout, QTextOption
from PySide6.QtNetwork import QNetworkRequest
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.domain import Album, Artist, Playlist, Station, Track
from app.presentation.qt.icon_utils import create_icon
from app.presentation.qt.library_controller import BrowserContent, BrowserItem, BrowserTab
from app.presentation.qt.preference_markers import (
    preference_marker_icon_name,
    preference_marker_kind,
)


class _CenteredGridListWidget(QListWidget):
    def set_centered_grid_metrics(
        self,
        *,
        enabled: bool,
        cell_width: int = 0,
        spacing: int = 0,
    ) -> None:
        del enabled, cell_width, spacing

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)


class _BrowserContentHost(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._resize_callback = None

    def set_resize_callback(self, callback) -> None:
        self._resize_callback = callback

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._resize_callback is not None:
            self._resize_callback()


class _ElidedWrapLabel(QLabel):
    def __init__(
        self,
        text: str = "",
        *,
        max_lines: int = 1,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._max_lines = max_lines
        self._full_text = ""
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text
        self._update_elided_text()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self) -> None:
        width = self.contentsRect().width()
        if width <= 0:
            super().setText(self._full_text)
            return
        super().setText(self._elide_wrapped_text(self._full_text, width))

    def _elide_wrapped_text(self, text: str, width: int) -> str:
        if not text:
            return ""
        metrics = QFontMetrics(self.font())
        layout = QTextLayout(text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        lines: list[tuple[int, int]] = []
        has_more = False
        while len(lines) < self._max_lines:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            lines.append((line.textStart(), line.textLength()))
        overflow_probe = layout.createLine()
        if overflow_probe.isValid():
            has_more = True
        layout.endLayout()
        if not lines:
            return metrics.elidedText(text, Qt.TextElideMode.ElideRight, width)

        rendered_lines: list[str] = []
        for index, (start, length) in enumerate(lines):
            chunk = text[start:start + length].strip()
            if index == len(lines) - 1 and has_more:
                rendered_lines.append(self._force_ellipsis(chunk, width, metrics))
            else:
                rendered_lines.append(chunk)
        return "\n".join(rendered_lines)

    def _force_ellipsis(self, text: str, width: int, metrics: QFontMetrics) -> str:
        if not text:
            return "..."
        candidate = text.rstrip()
        while candidate and metrics.horizontalAdvance(f"{candidate}...") > width:
            candidate = candidate[:-1].rstrip()
        return f"{candidate}..." if candidate else "..."


class _ElidedSingleLineLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = ""
        self.setText(text)

    def setText(self, text: str) -> None:
        self._full_text = text
        self._update_elided_text()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_elided_text()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_elided_text()

    def _update_elided_text(self) -> None:
        width = self.contentsRect().width()
        if width <= 0:
            super().setText(self._full_text)
            return
        metrics = QFontMetrics(self.font())
        super().setText(self._elide_text(self._full_text, width, metrics))

    def _elide_text(self, text: str, width: int, metrics: QFontMetrics) -> str:
        if metrics.horizontalAdvance(text) <= width:
            return text
        candidate = text.rstrip()
        while candidate and metrics.horizontalAdvance(f"{candidate}...") > width:
            candidate = candidate[:-1].rstrip()
        return f"{candidate}..." if candidate else "..."


class MainWindowBrowserMixin:
    _BROWSER_VIEW_MODE_LIST = "list"
    _BROWSER_VIEW_MODE_CARDS = "cards"
    _ALBUM_CARD_WIDTH = 196
    _ALBUM_CARD_HEIGHT = 284
    _ALBUM_CARD_ART_SIZE = 176
    _ALBUM_CARD_SOURCE_MAX_EDGE = 256
    _ART_CARD_SCROLL_STEP = 28

    def _build_browser_panel(self) -> QFrame:
        frame = self._panel_frame("Search / Library")
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        base_layout = frame.layout()
        assert base_layout is not None
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(self._t("browser.placeholder.search"))
        self._search_button = QPushButton(self._t("action.search"))
        self._search_loading = QProgressBar()
        self._search_loading.setRange(0, 0)
        self._search_loading.setTextVisible(False)
        self._search_loading.setFixedWidth(30)
        self._search_loading.setFixedHeight(12)
        self._search_loading.hide()
        self._browser_title_label = self._panel_label(self._t("library.search"))
        self._browser_title_label.setObjectName("browser-title")
        self._browser_back_button = QPushButton("‹")
        self._browser_back_button.setObjectName("panel-back-button")
        self._browser_back_button.setToolTip(self._t("action.back"))
        self._browser_back_button.setFixedSize(32, 30)
        self._browser_back_button.setEnabled(False)
        self._browser_close_button = QPushButton("×")
        self._browser_close_button.setObjectName("panel-close-button")
        self._browser_close_button.setToolTip(self._t("action.close"))
        self._browser_close_button.setFixedSize(32, 30)
        self._browser_view_mode_group = QButtonGroup(self)
        self._browser_view_mode_group.setExclusive(True)
        self._browser_view_mode_widget = QWidget()
        browser_view_layout = QHBoxLayout(self._browser_view_mode_widget)
        browser_view_layout.setContentsMargins(0, 0, 0, 0)
        browser_view_layout.setSpacing(6)
        self._browser_view_list_button = self._browser_view_button(
            self._t("browser.view.list"),
            mode=self._BROWSER_VIEW_MODE_LIST,
        )
        self._browser_view_cards_button = self._browser_view_button(
            self._t("browser.view.cards"),
            mode=self._BROWSER_VIEW_MODE_CARDS,
        )
        browser_view_layout.addWidget(self._browser_view_list_button)
        browser_view_layout.addWidget(self._browser_view_cards_button)
        self._browser_view_mode_widget.hide()
        self._browser_tabs = QTabWidget()
        self._browser_tabs.setVisible(False)
        self._content_list = _CenteredGridListWidget()
        self._content_list.setObjectName("browser-content-list")
        self._content_list.setAlternatingRowColors(True)
        self._content_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._content_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_list.setMovement(QListView.Movement.Static)
        self._content_list.setResizeMode(QListView.ResizeMode.Adjust)
        self._content_list_host = _BrowserContentHost()
        self._content_list_host.set_resize_callback(self._update_art_card_content_width)
        self._content_list_host_layout = QHBoxLayout(self._content_list_host)
        self._content_list_host_layout.setContentsMargins(0, 0, 0, 0)
        self._content_list_host_layout.setSpacing(0)
        self._content_list_host_layout.addStretch(1)
        self._content_list_host_layout.addWidget(self._content_list, 0)
        self._content_list_host_layout.addStretch(1)
        self._apply_browser_content_layout(use_album_cards=False)
        self._play_all_button = QPushButton(self._t("action.play_all"))
        self._play_all_button.setIcon(create_icon("play.svg"))
        self._play_all_button.setFixedHeight(32)
        self._append_all_button = QPushButton(self._t("action.append_all"))
        self._append_all_button.setIcon(create_icon("add_to_playlist.svg"))
        self._append_all_button.setFixedHeight(32)
        header_row.addWidget(self._browser_back_button)
        header_row.addWidget(self._browser_title_label, 1)
        header_row.addWidget(self._browser_view_mode_widget, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(self._browser_close_button)
        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        search_row.addWidget(self._search_input, 1)
        search_row.addWidget(self._search_button)
        search_row.addWidget(self._search_loading, 0, Qt.AlignmentFlag.AlignVCenter)
        browser_footer = QWidget()
        browser_footer.setFixedHeight(32)
        like_row = QHBoxLayout(browser_footer)
        like_row.setSpacing(8)
        like_row.setContentsMargins(0, 0, 0, 0)
        like_row.addWidget(self._play_all_button, 0, Qt.AlignmentFlag.AlignVCenter)
        like_row.addWidget(self._append_all_button, 0, Qt.AlignmentFlag.AlignVCenter)
        like_row.addStretch(1)
        base_layout.addLayout(header_row)
        base_layout.addLayout(search_row)
        base_layout.addWidget(self._browser_tabs)
        base_layout.addWidget(self._content_list_host, 1)
        base_layout.addWidget(browser_footer, 0, Qt.AlignmentFlag.AlignBottom)
        return frame

    def _build_browser_dialog(self) -> None:
        self._browser_dialog = QDialog(self)
        self._browser_dialog.setWindowTitle(self._t("window.search_library"))
        self._browser_dialog.setModal(False)
        self._browser_dialog.resize(860, 560)
        dialog_layout = QVBoxLayout(self._browser_dialog)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(self._browser_panel)
        self._browser_dialog.setStyleSheet(self.styleSheet())

    def _show_browser_panel(self) -> None:
        if self._browser_docked:
            if self._browser_host is not None:
                self._browser_host.show()
            return
        if self._browser_dialog is None:
            return
        self._browser_dialog.show()
        self._browser_dialog.raise_()
        self._browser_dialog.activateWindow()

    def _hide_browser_panel(self) -> None:
        if self._browser_docked:
            return
        if self._browser_dialog is not None:
            self._browser_dialog.hide()

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

    def _filter_browser_content_from_input(self) -> None:
        if self._current_browser_content is None:
            return
        self._apply_filtered_browser_content(self._current_browser_content)

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

    def _render_content(self, content: BrowserContent) -> None:
        if self._browser_auto_open_enabled:
            self._show_browser_panel()
        self._current_browser_content = content
        self._loading_more_content = False
        if content.search_query is not None:
            self._search_input.setText(content.search_query)
        self._apply_filtered_browser_content(content)

    def _apply_filtered_browser_content(self, content: BrowserContent) -> None:
        filtered_content = self._filtered_browser_content(content, self._search_input.text())
        use_art_cards = self._browser_view_uses_cards(content)
        self._browser_title_label.setText(content.title)
        self._browser_back_button.setEnabled(self._library_controller.can_go_back())
        self._render_browser_tabs(content.tabs, active_tab=content.active_tab)
        self._search_loading.setVisible(content.is_loading)
        self._search_button.setEnabled(not content.is_loading)
        self._sync_browser_view_mode_controls(content)
        self._apply_browser_content_layout(use_album_cards=use_art_cards)

        self._content_list.blockSignals(True)
        self._content_list.clear()
        if not filtered_content.items:
            empty_item = QListWidgetItem(self._t("browser.empty"))
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._content_list.addItem(empty_item)
        for browser_item in filtered_content.items:
            text = browser_item.title
            if browser_item.subtitle:
                text = f"{browser_item.title}\n{browser_item.subtitle}"
            widget_item = QListWidgetItem(text)
            widget_item.setData(Qt.ItemDataRole.UserRole, browser_item)
            if browser_item.kind == "section":
                widget_item.setFlags(widget_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            elif self._browser_item_uses_art(browser_item):
                widget = (
                    self._browser_album_card_widget(browser_item)
                    if use_art_cards and browser_item.kind in {"album", "artist"}
                    else self._browser_art_row_widget(browser_item)
                )
                if use_art_cards and browser_item.kind in {"album", "artist"}:
                    widget_item.setSizeHint(
                        QSize(self._ALBUM_CARD_WIDTH, self._ALBUM_CARD_HEIGHT)
                    )
                else:
                    widget_item.setSizeHint(widget.sizeHint())
                widget_item.setText("")
            self._content_list.addItem(widget_item)
            if browser_item.kind != "section" and self._browser_item_uses_art(browser_item):
                added_item = self._content_list.item(self._content_list.count() - 1)
                if added_item is not None:
                    self._content_list.setItemWidget(added_item, widget)
        self._content_list.blockSignals(False)
        can_play_source = bool(
            content.source_type
            and content.source_id
            and (
                content.bulk_mode == "load_all"
                or bool(content.source_tracks)
            )
        )
        self._play_all_button.setEnabled(can_play_source)
        self._append_all_button.setEnabled(can_play_source)

    def _filtered_browser_content(self, content: BrowserContent, query: str) -> BrowserContent:
        normalized_query = query.strip().casefold()
        if not normalized_query:
            return content

        filtered_items: list[BrowserItem] = []
        pending_section: BrowserItem | None = None
        section_matched = False
        has_sections = False

        for item in content.items:
            if item.kind == "section":
                has_sections = True
                if pending_section is not None and section_matched:
                    filtered_items.append(pending_section)
                pending_section = item
                section_matched = False
                continue
            if not self._browser_item_matches_query(item, normalized_query):
                continue
            if pending_section is not None and not section_matched:
                filtered_items.append(pending_section)
                section_matched = True
            filtered_items.append(item)

        if has_sections:
            return BrowserContent(
                title=content.title,
                items=tuple(filtered_items),
                recent_searches=content.recent_searches,
                tabs=content.tabs,
                active_tab=content.active_tab,
                search_query=content.search_query,
                source_type=content.source_type,
                source_id=content.source_id,
                source_tracks=content.source_tracks,
                bulk_mode=content.bulk_mode,
                list_key=content.list_key,
                has_more=content.has_more,
                is_loading=content.is_loading,
            )

        return BrowserContent(
            title=content.title,
            items=tuple(
                item
                for item in content.items
                if self._browser_item_matches_query(item, normalized_query)
            ),
            recent_searches=content.recent_searches,
            tabs=content.tabs,
            active_tab=content.active_tab,
            search_query=content.search_query,
            source_type=content.source_type,
            source_id=content.source_id,
            source_tracks=content.source_tracks,
            bulk_mode=content.bulk_mode,
            list_key=content.list_key,
            has_more=content.has_more,
            is_loading=content.is_loading,
        )

    def _browser_item_matches_query(self, item: BrowserItem, normalized_query: str) -> bool:
        haystacks = [item.title]
        if item.subtitle:
            haystacks.append(item.subtitle)
        return any(normalized_query in value.casefold() for value in haystacks)

    def _browser_item_uses_art(self, item: BrowserItem) -> bool:
        return item.kind in {
            "track",
            "album",
            "artist",
        }

    def _content_uses_art_cards(self, content: BrowserContent) -> bool:
        items = tuple(item for item in content.items if item.kind != "section")
        return bool(items) and all(item.kind in {"album", "artist"} for item in items)

    def _browser_view_button(self, text: str, *, mode: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("quality-option")
        button.setCheckable(True)
        button.setFixedHeight(26)
        button.setProperty("browser_view_mode", mode)
        self._browser_view_mode_group.addButton(button)
        return button

    def _browser_view_uses_cards(self, content: BrowserContent) -> bool:
        supports_cards = self._content_uses_art_cards(content)
        if not supports_cards:
            return False
        return self._browser_view_mode == self._BROWSER_VIEW_MODE_CARDS

    def _sync_browser_view_mode_controls(self, content: BrowserContent | None = None) -> None:
        if content is None:
            content = self._current_browser_content
        supports_cards = bool(content) and self._content_uses_art_cards(content)
        self._browser_view_mode_widget.setVisible(supports_cards)
        if supports_cards:
            for button, mode in (
                (self._browser_view_list_button, self._BROWSER_VIEW_MODE_LIST),
                (self._browser_view_cards_button, self._BROWSER_VIEW_MODE_CARDS),
            ):
                button.blockSignals(True)
                button.setChecked(self._browser_view_mode == mode)
                button.blockSignals(False)

    def _set_browser_view_mode(self, mode: str, *, persist: bool = True) -> None:
        if mode not in {
            self._BROWSER_VIEW_MODE_LIST,
            self._BROWSER_VIEW_MODE_CARDS,
        }:
            mode = self._BROWSER_VIEW_MODE_CARDS
        if self._browser_view_mode == mode:
            return
        self._browser_view_mode = mode
        if persist:
            self._container.services.settings_service.save_browser_view_mode(mode)
        self._sync_browser_view_mode_controls()
        if self._current_browser_content is not None:
            self._render_content(self._current_browser_content)

    def _apply_browser_content_layout(self, *, use_album_cards: bool) -> None:
        if use_album_cards:
            self._content_list.setAlternatingRowColors(False)
            self._content_list.setViewMode(QListView.ViewMode.IconMode)
            self._content_list.setFlow(QListView.Flow.LeftToRight)
            self._content_list.setWrapping(True)
            self._content_list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
            self._content_list.verticalScrollBar().setSingleStep(self._ART_CARD_SCROLL_STEP)
            self._content_list.setSpacing(12)
            self._content_list.setGridSize(
                QSize(self._ALBUM_CARD_WIDTH, self._ALBUM_CARD_HEIGHT)
            )
            self._content_list.setWordWrap(True)
            self._content_list.setUniformItemSizes(True)
            self._content_list.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Expanding,
            )
            self._content_list.setStyleSheet(
                "QListWidget::item, QListView::item { padding: 0px; margin: 0px; }"
            )
            self._content_list_host_layout.setStretch(0, 1)
            self._content_list_host_layout.setStretch(1, 0)
            self._content_list_host_layout.setStretch(2, 1)
            self._update_art_card_content_width()
            return
        self._content_list.setAlternatingRowColors(True)
        self._content_list.setViewMode(QListView.ViewMode.ListMode)
        self._content_list.setFlow(QListView.Flow.TopToBottom)
        self._content_list.setWrapping(False)
        self._content_list.setVerticalScrollMode(QListView.ScrollMode.ScrollPerItem)
        self._content_list.setSpacing(0)
        self._content_list.setGridSize(QSize())
        self._content_list.setWordWrap(False)
        self._content_list.setUniformItemSizes(False)
        self._content_list.setMinimumWidth(0)
        self._content_list.setMaximumWidth(16_777_215)
        self._content_list.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._content_list.setStyleSheet(
            "QListWidget::item, QListView::item { padding: 5px; margin: 0px; }"
        )
        self._content_list_host_layout.setStretch(0, 0)
        self._content_list_host_layout.setStretch(1, 1)
        self._content_list_host_layout.setStretch(2, 0)
        self._content_list.set_centered_grid_metrics(enabled=False)

    def _update_art_card_content_width(self) -> None:
        if self._content_list.viewMode() != QListView.ViewMode.IconMode:
            return
        available_width = self._content_list_host.contentsRect().width()
        if available_width <= 0:
            return
        spacing = self._content_list.spacing()
        stride = self._ALBUM_CARD_WIDTH + spacing
        columns = max(1, (available_width + spacing) // stride)
        used_width = (
            columns * self._ALBUM_CARD_WIDTH
            + max(0, columns - 1) * spacing
        )
        self._content_list.setFixedWidth(min(used_width, available_width))

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
        marker = self._preference_marker_label(
            item.payload,
            size=16,
            object_name="browser-preference-marker",
        )
        if marker is not None:
            layout.addWidget(marker, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _browser_album_card_widget(self, item: BrowserItem) -> QWidget:
        card = QWidget()
        card.setObjectName("browser-album-card")
        card.setFixedSize(self._ALBUM_CARD_WIDTH, self._ALBUM_CARD_HEIGHT)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 8, 0, 14)
        layout.setSpacing(8)
        artwork_ref = getattr(item.payload, "artwork_ref", None)
        art = self._album_card_art_widget(item, artwork_ref, size=self._ALBUM_CARD_ART_SIZE)
        title = _ElidedWrapLabel(item.title, max_lines=2)
        title.setObjectName("browser-album-card-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFixedHeight(48)
        subtitle_text = "" if item.kind == "artist" else (item.subtitle or "")
        subtitle = _ElidedSingleLineLabel(subtitle_text)
        subtitle.setObjectName("browser-album-card-subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(False)
        subtitle.setFixedHeight(16)
        layout.addWidget(art, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card

    def _album_card_art_widget(
        self,
        item: BrowserItem,
        artwork_ref: str | None,
        *,
        size: int,
    ) -> QWidget:
        container = QWidget()
        container.setFixedSize(size, size)
        art = self._album_card_art_label(artwork_ref, size=size, parent=container)
        art.setObjectName("browser-album-card-art")
        art.move(0, 0)
        marker = self._preference_marker_label(
            item.payload,
            size=18,
            object_name="browser-preference-badge",
            parent=container,
        )
        if marker is not None:
            marker.move(size - marker.width() - 4, 4)
            marker.raise_()
        return container

    def _album_card_art_label(
        self,
        artwork_ref: str | None,
        *,
        size: int,
        parent: QWidget | None = None,
    ) -> QLabel:
        label = QLabel(parent)
        label.setObjectName("browser-album-card-art")
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not artwork_ref:
            label.setText("♪")
            return label
        artwork_url = self._container.services.artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            label.setText("♪")
            return label
        pixmap = self._thumb_pixmap_for_url(
            artwork_url,
            size=size,
            source_max_edge=self._ALBUM_CARD_SOURCE_MAX_EDGE,
        )
        if pixmap is None:
            label.setText("♪")
            cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
            self._queue_thumb_download(artwork_url, cache_path, label)
            return label
        label.setText("")
        label.setPixmap(pixmap)
        return label

    def _preference_marker_label(
        self,
        payload: object,
        *,
        size: int,
        object_name: str,
        parent: QWidget | None = None,
    ) -> QLabel | None:
        marker_kind = preference_marker_kind(payload)
        if marker_kind is None:
            return None
        icon_name = preference_marker_icon_name(
            marker_kind,
            theme_mode=self._resolved_theme_mode(),
        )
        color = self._accent_color if marker_kind == "liked" else self._theme_muted_icon_color()
        label = QLabel(parent)
        label.setObjectName(object_name)
        label.setFixedSize(size, size)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(create_icon(icon_name, color=color, size=size).pixmap(size, size))
        return label

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
        pixmap = self._thumb_pixmap_for_url(artwork_url, size=size)
        if pixmap is None:
            label.setText("♪")
            cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
            self._queue_thumb_download(artwork_url, cache_path, label)
            return label
        label.setText("")
        label.setPixmap(pixmap)
        return label

    def _queue_thumb_download(
        self,
        artwork_url: str,
        cache_path: Path,
        label: QLabel | None = None,
        *,
        on_ready=None,
    ) -> None:
        labels = self._pending_thumb_labels.setdefault(artwork_url, [])
        if label is not None:
            labels.append(label)
        callbacks = self._pending_thumb_callbacks.setdefault(artwork_url, [])
        if on_ready is not None:
            callbacks.append(on_ready)
        if len(labels) + len(callbacks) > 1:
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
