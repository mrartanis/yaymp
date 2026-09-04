from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from app.domain import (
    Playlist,
    PlaylistSaveMode,
    PlaylistSaveRequest,
    PlaylistVisibility,
    Track,
)


class SavePlaylistDialog(QDialog):
    save_requested = Signal(object)

    def __init__(
        self,
        *,
        tracks: tuple[Track, ...],
        translate: Callable[..., str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._tracks = tracks
        self._t = translate
        self._playlists: tuple[Playlist, ...] = ()
        self._saving = False
        self.setWindowTitle(self._t("dialog.save_playlist.title"))
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._form = form
        self._destination_combo = QComboBox()
        self._destination_combo.addItem(self._t("dialog.save_playlist.new"), None)
        self._destination_combo.setEnabled(False)
        form.addRow(self._t("dialog.save_playlist.destination"), self._destination_combo)
        self._title_input = QLineEdit()
        form.addRow(self._t("dialog.save_playlist.name"), self._title_input)
        self._public_checkbox = QCheckBox(self._t("dialog.save_playlist.public"))
        form.addRow("", self._public_checkbox)

        self._mode_widget = QWidget()
        mode_layout = QVBoxLayout(self._mode_widget)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        self._append_radio = QRadioButton(self._t("dialog.save_playlist.append"))
        self._replace_radio = QRadioButton(self._t("dialog.save_playlist.replace"))
        self._append_radio.setChecked(True)
        mode_layout.addWidget(self._append_radio)
        mode_layout.addWidget(self._replace_radio)
        form.addRow(self._t("dialog.save_playlist.mode"), self._mode_widget)
        layout.addLayout(form)

        self._error_label = QLabel(self._t("dialog.save_playlist.loading"))
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("color: #d45b67;")
        layout.addWidget(self._error_label)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(self._buttons)
        self._save_button = self._buttons.button(QDialogButtonBox.StandardButton.Save)
        self._save_button.setText(self._t("action.save_playlist"))
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            self._t("action.cancel")
        )
        self._buttons.accepted.connect(self._submit)
        self._buttons.rejected.connect(self.reject)
        self._destination_combo.currentIndexChanged.connect(self._validate)
        self._title_input.textChanged.connect(self._validate)
        self._set_new_playlist_fields(True)
        self._validate()

    def set_destinations(self, playlists: tuple[Playlist, ...]) -> None:
        self._playlists = playlists
        self._destination_combo.blockSignals(True)
        self._destination_combo.clear()
        self._destination_combo.addItem(self._t("dialog.save_playlist.new"), None)
        for playlist in playlists:
            label = (
                playlist.title
                if playlist.track_count is None
                else f"{playlist.title} ({playlist.track_count})"
            )
            self._destination_combo.addItem(label, playlist)
        self._destination_combo.blockSignals(False)
        self._destination_combo.setEnabled(True)
        self._error_label.clear()
        self._validate()

    def set_error(self, message: str, *, name_conflict: bool = False) -> None:
        self._saving = False
        self._error_label.setText(message)
        self._title_input.setProperty("validation_error", name_conflict)
        self._title_input.style().unpolish(self._title_input)
        self._title_input.style().polish(self._title_input)
        self._set_controls_enabled(True)
        self._validate()

    def complete(self) -> None:
        self._saving = False
        self.accept()

    def reject(self) -> None:
        if self._saving:
            return
        super().reject()

    def _submit(self) -> None:
        if not self._validate():
            return
        target = self._selected_playlist()
        if target is None:
            mode = PlaylistSaveMode.CREATE
        elif self._replace_radio.isChecked():
            mode = PlaylistSaveMode.REPLACE
        else:
            mode = PlaylistSaveMode.APPEND
        request = PlaylistSaveRequest(
            tracks=self._tracks,
            mode=mode,
            title=self._title_input.text().strip() if target is None else None,
            visibility=(
                PlaylistVisibility.PUBLIC
                if self._public_checkbox.isChecked()
                else PlaylistVisibility.PRIVATE
            ),
            target=target,
        )
        self._saving = True
        self._error_label.setText(self._t("dialog.save_playlist.saving"))
        self._set_controls_enabled(False)
        self.save_requested.emit(request)

    def _validate(self) -> bool:
        target = self._selected_playlist()
        is_new = target is None
        self._set_new_playlist_fields(is_new)
        title = self._title_input.text().strip()
        conflict = is_new and bool(title) and any(
            playlist.title.strip().casefold() == title.casefold()
            for playlist in self._playlists
        )
        valid = self._destination_combo.isEnabled() and (not is_new or bool(title)) and not conflict
        if conflict:
            self._error_label.setText(self._t("dialog.save_playlist.name_exists"))
        elif not self._saving and self._destination_combo.isEnabled():
            self._error_label.clear()
        self._title_input.setProperty("validation_error", conflict)
        self._title_input.style().unpolish(self._title_input)
        self._title_input.style().polish(self._title_input)
        self._save_button.setEnabled(valid and not self._saving)
        return valid

    def _selected_playlist(self) -> Playlist | None:
        value = self._destination_combo.currentData()
        return value if isinstance(value, Playlist) else None

    def _set_new_playlist_fields(self, is_new: bool) -> None:
        self._title_input.setVisible(is_new)
        self._public_checkbox.setVisible(is_new)
        self._mode_widget.setVisible(not is_new)
        title_label = self._form.labelForField(self._title_input)
        mode_label = self._form.labelForField(self._mode_widget)
        if title_label is not None:
            title_label.setVisible(is_new)
        if mode_label is not None:
            mode_label.setVisible(not is_new)

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._destination_combo.setEnabled(enabled)
        self._title_input.setEnabled(enabled)
        self._public_checkbox.setEnabled(enabled)
        self._append_radio.setEnabled(enabled)
        self._replace_radio.setEnabled(enabled)
        self._buttons.button(QDialogButtonBox.StandardButton.Cancel).setEnabled(enabled)
