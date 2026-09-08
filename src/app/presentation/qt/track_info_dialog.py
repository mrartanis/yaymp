from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from app.domain import Track, TrackAiUsage


class TrackInfoDialog(QDialog):
    def __init__(
        self,
        *,
        track: Track,
        translate: Callable[..., str],
        format_ms: Callable[[int | None], str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._t = translate
        self._format_ms = format_ms
        self.setWindowTitle(self._t("track_info.title"))
        self.setMinimumWidth(460)
        self._layout = QVBoxLayout(self)
        self._form = QFormLayout()
        self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self._layout.addLayout(self._form)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._layout.addWidget(self._status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self._layout.addWidget(buttons)
        self.set_track(track)

    def set_track(self, track: Track) -> None:
        self._clear_form()
        rows = (
            (self._t("track_info.name"), track.title),
            (self._t("track_info.artists"), ", ".join(track.artists)),
            (self._t("track_info.album"), track.album_title or "—"),
            (self._t("track_info.year"), str(track.album_year) if track.album_year else "—"),
            (self._t("track_info.duration"), self._format_ms(track.duration_ms)),
            (self._t("track_info.version"), track.version or "—"),
            (self._t("track_info.ai_use"), self._ai_usage_text(track.ai_usage)),
        )
        for title, value in rows:
            self._add_row(title, value)
        if track.credits:
            self._add_section(self._t("track_info.credits"))
            for credit in track.credits:
                self._add_row(credit.title, credit.value)
        self._status.setText("")

    def set_loading(self) -> None:
        self._status.setText(self._t("track_info.loading"))

    def set_error(self, message: str) -> None:
        self._status.setText(self._t("track_info.error", message=message))

    def _add_row(self, title: str, value: str) -> None:
        label = QLabel(value)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._form.addRow(f"{title}:", label)

    def _add_section(self, title: str) -> None:
        label = QLabel(title)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        self._form.addRow(label)

    def _clear_form(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)

    def _ai_usage_text(self, usage: TrackAiUsage | None) -> str:
        if usage is None:
            return self._t("track_info.ai_use.none")
        return self._t(f"track_info.ai_use.{usage.value}")
