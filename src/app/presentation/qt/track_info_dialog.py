from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

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
        additional_fields = self._additional_raw_fields(track.credits_raw_json)
        if additional_fields:
            self._add_section(self._t("track_info.additional_information"))
            for title, value in additional_fields:
                self._add_row(title, value)
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

    def _additional_raw_fields(self, raw_json: str | None) -> tuple[tuple[str, str], ...]:
        if not raw_json:
            return ()
        try:
            payload = json.loads(raw_json)
        except (TypeError, json.JSONDecodeError):
            return ((self._t("track_info.unknown_field"), raw_json),)

        fields: list[tuple[str, str]] = []
        self._flatten_raw_value(payload, path="", fields=fields)
        return tuple(fields)

    def _flatten_raw_value(
        self,
        value: object,
        *,
        path: str,
        fields: list[tuple[str, str]],
    ) -> None:
        if self._is_rendered_credit_field(path):
            return
        if isinstance(value, dict):
            if not value and path:
                fields.append((path, "{}"))
                return
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                self._flatten_raw_value(child, path=child_path, fields=fields)
            return
        if isinstance(value, list):
            if not value:
                if path != "credits":
                    fields.append((path, "[]"))
                return
            for index, child in enumerate(value):
                self._flatten_raw_value(
                    child,
                    path=f"{path}[{index}]",
                    fields=fields,
                )
            return
        fields.append((path or self._t("track_info.unknown_field"), self._raw_value_text(value)))

    def _is_rendered_credit_field(self, path: str) -> bool:
        if not path.startswith("credits["):
            return False
        return path.endswith("].title") or path.endswith("].value")

    def _raw_value_text(self, value: object) -> str:
        if value is None:
            return "—"
        if isinstance(value, bool):
            return str(value).lower()
        return str(value)
