from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialogButtonBox

from app.domain import Playlist, PlaylistSaveMode, PlaylistSaveRequest, Track
from app.presentation.qt import playlist_save_dialog
from app.presentation.qt.dialog_chrome import WindowTitleBar
from app.presentation.qt.playlist_save_dialog import SavePlaylistDialog


def _translate(key: str, **params: object) -> str:
    del params
    return key


def _dialog(qtbot) -> SavePlaylistDialog:
    dialog = SavePlaylistDialog(
        tracks=(Track(id="track-1", title="Track", artists=("Artist",)),),
        translate=_translate,
    )
    qtbot.addWidget(dialog)
    return dialog


def test_dialog_highlights_duplicate_name_before_submit(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.set_destinations((Playlist(id="1", title="Road Trip", owner_id="7"),))

    dialog._title_input.setText("  road trip  ")

    save_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Save)
    assert save_button.isEnabled() is False
    assert dialog._title_input.property("validation_error") is True
    assert dialog._error_label.text() == "dialog.save_playlist.name_exists"


def test_dialog_uses_custom_frame_and_text_only_action_buttons(qtbot) -> None:
    dialog = _dialog(qtbot)

    save_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Save)
    cancel_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
    assert dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert dialog._dialog_root.objectName() == "dialog-root"
    assert isinstance(dialog._title_bar, WindowTitleBar)
    assert dialog._title_bar.objectName() == "top-bar"
    assert save_button.icon().isNull()
    assert cancel_button.icon().isNull()


def test_dialog_fields_expand_with_window(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.show()
    dialog.resize(400, dialog.height())
    qtbot.wait(1)
    narrow_title_width = dialog._title_input.width()
    narrow_destination_width = dialog._destination_combo.width()

    dialog.resize(700, dialog.height())
    qtbot.wait(1)

    assert dialog.minimumWidth() == 360
    assert dialog._title_input.width() > narrow_title_width
    assert dialog._destination_combo.width() > narrow_destination_width


def test_dialog_places_close_button_on_left_on_macos(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(playlist_save_dialog, "_macos_window_controls_on_left", lambda: True)

    dialog = _dialog(qtbot)

    assert dialog._title_bar.controls_layout.itemAt(0).widget() is dialog._close_button


def test_dialog_places_close_button_on_right_elsewhere(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(playlist_save_dialog, "_macos_window_controls_on_left", lambda: False)

    dialog = _dialog(qtbot)

    layout = dialog._title_bar.controls_layout
    assert layout.itemAt(layout.count() - 1).widget() is dialog._close_button


def test_dialog_builds_replace_request_for_existing_playlist(qtbot) -> None:
    dialog = _dialog(qtbot)
    playlist = Playlist(id="1", title="Existing", owner_id="7")
    requests: list[PlaylistSaveRequest] = []
    dialog.save_requested.connect(requests.append)
    dialog.set_destinations((playlist,))
    dialog._destination_combo.setCurrentIndex(1)
    dialog._replace_radio.setChecked(True)

    dialog._submit()

    assert len(requests) == 1
    assert requests[0].mode is PlaylistSaveMode.REPLACE
    assert requests[0].target == playlist
