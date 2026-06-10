from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.bootstrap.config import AppConfig


def _resolve_application_icon() -> QIcon | None:
    executable = Path(sys.executable).resolve()
    candidates: list[Path] = []

    if sys.platform == "win32":
        # Reuse the icon embedded into the packaged executable for the taskbar.
        candidates.append(executable)

    candidates.extend(
        (
            executable.parent / "yaymp.ico",
            executable.parent / "icon.png",
            Path(__file__).resolve().parents[4] / "icon.png",
        )
    )

    for candidate in candidates:
        if not candidate.exists():
            continue
        icon = QIcon(str(candidate))
        if not icon.isNull():
            return icon
    return None


def create_qt_application(argv: Sequence[str], config: AppConfig) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing

    if sys.platform == "win32":
        app_id = f"{config.app_author}.{config.app_name}"
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

    qt_app = QApplication(list(argv))
    qt_app.setApplicationName(config.app_name)
    qt_app.setOrganizationName(config.app_author)
    qt_app.setApplicationDisplayName("YAYMP")
    icon = _resolve_application_icon()
    if icon is not None:
        qt_app.setWindowIcon(icon)
    return qt_app
