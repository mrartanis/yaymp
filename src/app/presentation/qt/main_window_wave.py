from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QModelIndex, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QPainter, QPaintEvent, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from app.domain import WaveSettings


class _WaveSettingsItemDelegate(QStyledItemDelegate):
    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        styled_option = QStyleOptionViewItem(option)
        self.initStyleOption(styled_option, index)
        active_states = QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Selected
        if styled_option.state & active_states:
            painter.save()
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(styled_option.palette.brush(QPalette.ColorRole.Highlight))
                painter.drawRoundedRect(styled_option.rect.adjusted(4, 1, -4, -1), 6, 6)
            finally:
                painter.restore()
            highlighted_text = styled_option.palette.brush(QPalette.ColorRole.HighlightedText)
            styled_option.palette.setBrush(QPalette.ColorRole.Text, highlighted_text)
            styled_option.palette.setBrush(QPalette.ColorRole.WindowText, highlighted_text)
            styled_option.state &= ~active_states
        super().paint(painter, styled_option, index)


class _WaveSettingsComboBox(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("wave-settings-combo")
        self.setItemDelegate(_WaveSettingsItemDelegate(self))
        self._prepare_popup_view()

    def showPopup(self) -> None:  # noqa: N802
        self._prepare_popup_view()
        super().showPopup()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        color = self.palette().color(self.foregroundRole())
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        center_x = self.width() - 16.0
        center_y = self.height() / 2.0
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(center_x - 4.0, center_y - 2.0),
                QPointF(center_x, center_y + 2.0),
            )
            painter.drawLine(
                QPointF(center_x, center_y + 2.0),
                QPointF(center_x + 4.0, center_y - 2.0),
            )
        finally:
            painter.end()

    def _prepare_popup_view(self) -> None:
        view: QAbstractItemView = self.view()
        view.setObjectName("wave-settings-combo-view")
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setMouseTracking(True)
        view.viewport().setMouseTracking(True)
        popup = view.window()
        popup.setObjectName("wave-settings-combo-popup")
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        popup.setAutoFillBackground(False)
        popup_palette = popup.palette()
        popup_palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.transparent)
        popup.setPalette(popup_palette)
        if popup.layout() is not None:
            popup.layout().setContentsMargins(0, 0, 0, 0)
            popup.layout().setSpacing(0)
        popup.style().unpolish(popup)
        popup.style().polish(popup)


class WaveSettingsPopup(QFrame):
    play_requested = Signal(object)
    reset_requested = Signal()

    def __init__(
        self,
        *,
        translate: Callable[..., str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self._t = translate
        self._settings: WaveSettings | None = None
        self._setting_combos: list[QComboBox] = []
        self.setObjectName("wave-settings-popup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(320)
        self.setMaximumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        self._title_label = QLabel()
        self._title_label.setObjectName("wave-settings-title")
        layout.addWidget(self._title_label)

        self._status_label = QLabel()
        self._status_label.setObjectName("wave-settings-status")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._controls = QWidget()
        self._controls_layout = QVBoxLayout(self._controls)
        self._controls_layout.setContentsMargins(0, 0, 0, 0)
        self._controls_layout.setSpacing(7)
        layout.addWidget(self._controls)

        self._station_label = QLabel()
        self._station_label.setObjectName("settings-section")
        self._station_combo = _WaveSettingsComboBox()
        self._station_combo.currentIndexChanged.connect(self._update_description)
        self._description_label = QLabel()
        self._description_label.setObjectName("wave-settings-description")
        self._description_label.setWordWrap(True)
        self._controls_layout.addWidget(self._station_label)
        self._controls_layout.addWidget(self._station_combo)
        self._controls_layout.addWidget(self._description_label)

        self._dynamic_controls = QWidget()
        self._dynamic_layout = QVBoxLayout(self._dynamic_controls)
        self._dynamic_layout.setContentsMargins(0, 0, 0, 0)
        self._dynamic_layout.setSpacing(7)
        self._controls_layout.addWidget(self._dynamic_controls)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        self._reset_button = QPushButton()
        self._play_button = QPushButton()
        self._play_button.setObjectName("wave-settings-play")
        actions.addWidget(self._reset_button)
        actions.addStretch(1)
        actions.addWidget(self._play_button)
        layout.addLayout(actions)

        self._reset_button.clicked.connect(self.reset_requested.emit)
        self._play_button.clicked.connect(self._emit_play_requested)
        self.apply_texts()
        self.set_loading()

    def apply_texts(self) -> None:
        self._title_label.setText(self._t("wave.settings.title"))
        self._station_label.setText(self._t("wave.settings.station"))
        self._reset_button.setText(self._t("action.reset"))
        self._play_button.setText(self._t("wave.settings.play"))
        if self._settings is None:
            self._status_label.setText(self._t("wave.settings.loading"))

    def set_loading(self) -> None:
        self._settings = None
        self._status_label.setText(self._t("wave.settings.loading"))
        self._status_label.show()
        self._controls.hide()
        self._reset_button.setEnabled(False)
        self._play_button.setEnabled(False)

    def set_error(self, message: str) -> None:
        self._settings = None
        self._status_label.setText(self._t("wave.settings.error", message=message))
        self._status_label.show()
        self._controls.hide()
        self._reset_button.setEnabled(True)
        self._play_button.setEnabled(False)

    def set_settings(self, settings: WaveSettings) -> None:
        self._settings = settings
        self._clear_dynamic_controls()
        selected = set(settings.selected_seeds)

        self._station_combo.clear()
        for option in settings.stations:
            self._station_combo.addItem(option.title, option.seed)
        station_index = next(
            (
                index
                for index in range(self._station_combo.count())
                if self._station_combo.itemData(index) in selected
            ),
            0,
        )
        self._station_combo.setCurrentIndex(station_index)

        for setting in settings.settings:
            label = QLabel(setting.title)
            label.setObjectName("settings-section")
            combo = _WaveSettingsComboBox()
            if setting.optional:
                combo.addItem(self._t("wave.settings.any"), "")
            for option in sorted(setting.options, key=lambda item: not item.unspecified):
                combo.addItem(option.title, option.seed)
            selected_index = next(
                (index for index in range(combo.count()) if combo.itemData(index) in selected),
                0,
            )
            combo.setCurrentIndex(selected_index)
            self._dynamic_layout.addWidget(label)
            self._dynamic_layout.addWidget(combo)
            self._setting_combos.append(combo)

        self._status_label.hide()
        self._controls.show()
        self._reset_button.setEnabled(True)
        self._play_button.setEnabled(bool(settings.stations))
        self._update_description()
        self.adjustSize()

    def selected_seeds(self) -> tuple[str, ...]:
        station_seed = self._station_combo.currentData()
        seeds = [station_seed] if isinstance(station_seed, str) and station_seed else []
        for combo in self._setting_combos:
            seed = combo.currentData()
            if isinstance(seed, str) and seed:
                seeds.append(seed)
        return tuple(seeds)

    def _emit_play_requested(self) -> None:
        seeds = self.selected_seeds()
        if seeds:
            self.play_requested.emit(seeds)

    def _update_description(self) -> None:
        if self._settings is None:
            self._description_label.clear()
            return
        seed = self._station_combo.currentData()
        description = next(
            (
                option.description
                for option in self._settings.stations
                if option.seed == seed and option.description
            ),
            None,
        )
        self._description_label.setText(description or "")
        self._description_label.setVisible(bool(description))

    def _clear_dynamic_controls(self) -> None:
        self._setting_combos = []
        while self._dynamic_layout.count():
            item = self._dynamic_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class MainWindowWaveMixin:
    def _build_wave_settings_popup(self) -> None:
        self._wave_settings_popup = WaveSettingsPopup(translate=self._t, parent=self)
        self._wave_settings_popup.play_requested.connect(self._play_configured_wave)
        self._wave_settings_popup.reset_requested.connect(self._reset_wave_settings)
        self._wave_settings_popup.hide()

    def _show_wave_settings_popup(self) -> None:
        popup = self._wave_settings_popup
        if popup.isVisible():
            popup.hide()
            return
        if self._wave_settings is None:
            popup.set_loading()
        else:
            popup.set_settings(self._wave_settings)
        popup.setStyleSheet(self.styleSheet())
        popup.adjustSize()
        anchor = self._my_wave_settings_button.mapToGlobal(
            QPoint(0, self._my_wave_settings_button.height() + 6)
        )
        screen = self.screen().availableGeometry()
        x = min(anchor.x(), screen.right() - popup.width() - 8)
        y = min(anchor.y(), screen.bottom() - popup.height() - 8)
        popup.move(QPoint(max(screen.left() + 8, x), max(screen.top() + 8, y)))
        popup.show()
        popup.raise_()
        self._request_wave_settings()

    def _request_wave_settings(self, *, force: bool = False) -> None:
        if self._container.services.auth_service.current_session() is None:
            return
        if self._wave_settings_task_id is not None:
            if not force:
                return
            self._library_task_runner.cancel(self._wave_settings_task_id)
        self._wave_settings_task_id = self._library_task_runner.submit(
            self._container.services.music_service.get_wave_settings
        )

    def _handle_wave_task_completed(self, task_id: int, result: object) -> None:
        if task_id == self._wave_settings_task_id:
            self._wave_settings_task_id = None
            if isinstance(result, WaveSettings):
                self._apply_wave_settings(result)
            return
        if task_id == self._wave_reset_task_id:
            self._wave_reset_task_id = None
            if isinstance(result, WaveSettings):
                self._apply_wave_settings(result)

    def _handle_wave_task_failed(self, task_id: int, error: object) -> None:
        if task_id not in {self._wave_settings_task_id, self._wave_reset_task_id}:
            return
        if task_id == self._wave_settings_task_id:
            self._wave_settings_task_id = None
        if task_id == self._wave_reset_task_id:
            self._wave_reset_task_id = None
        if self._wave_settings_popup.isVisible():
            self._wave_settings_popup.set_error(str(error))

    def _apply_wave_settings(self, settings: WaveSettings) -> None:
        self._wave_settings = settings
        if settings.selected_seeds:
            self._wave_selected_seeds = settings.selected_seeds
            self._container.services.settings_service.save_my_wave_seeds(settings.selected_seeds)
        self._refresh_wave_button_text()
        if self._wave_settings_popup.isVisible():
            self._wave_settings_popup.set_settings(settings)
            self._show_wave_settings_popup_at_current_position()

    def _show_wave_settings_popup_at_current_position(self) -> None:
        popup = self._wave_settings_popup
        anchor = self._my_wave_settings_button.mapToGlobal(
            QPoint(0, self._my_wave_settings_button.height() + 6)
        )
        screen = self.screen().availableGeometry()
        popup.adjustSize()
        popup.move(
            QPoint(
                max(screen.left() + 8, min(anchor.x(), screen.right() - popup.width() - 8)),
                max(screen.top() + 8, min(anchor.y(), screen.bottom() - popup.height() - 8)),
            )
        )

    def _play_configured_wave(self, seeds: object) -> None:
        if not isinstance(seeds, tuple) or not all(isinstance(seed, str) for seed in seeds):
            return
        self._wave_selected_seeds = seeds
        self._container.services.settings_service.save_my_wave_seeds(seeds)
        self._refresh_wave_button_text()
        self._wave_settings_popup.hide()
        self._start_my_wave()

    def _reset_wave_settings(self) -> None:
        if self._wave_reset_task_id is not None:
            return
        self._wave_settings_popup.set_loading()

        def reset_and_reload() -> WaveSettings:
            service = self._container.services.music_service
            service.reset_last_wave()
            return service.get_wave_settings()

        self._wave_reset_task_id = self._library_task_runner.submit(reset_and_reload)

    def _invalidate_wave_settings_for_language(self) -> None:
        if self._wave_reset_task_id is not None:
            self._library_task_runner.cancel(self._wave_reset_task_id)
            self._wave_reset_task_id = None
        self._wave_settings = None
        self._refresh_wave_button_text()
        self._wave_settings_popup.apply_texts()
        self._wave_settings_popup.set_loading()
        self._request_wave_settings(force=True)

    def _refresh_wave_button_text(self) -> None:
        base_title = self._t("nav.my_wave")
        settings = self._wave_settings
        if settings is None:
            self._my_wave_top_button.setText(base_title)
            self._my_wave_top_button.setToolTip(self._t("wave.settings.configure"))
            return
        selected = set(self._wave_selected_seeds)
        labels: list[str] = []
        station = next((item for item in settings.stations if item.seed in selected), None)
        if station is not None and not station.unspecified:
            labels.append(station.title)
        for setting in settings.settings:
            option = next((item for item in setting.options if item.seed in selected), None)
            if option is not None and not option.unspecified:
                labels.append(option.title)
        summary = " · ".join(labels[:2])
        self._my_wave_top_button.setText(
            self._t("wave.settings.button_summary", summary=summary) if summary else base_title
        )
        tooltip = " · ".join([base_title, *labels]) if labels else base_title
        self._my_wave_top_button.setToolTip(tooltip)
