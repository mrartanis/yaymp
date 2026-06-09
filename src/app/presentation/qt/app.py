from __future__ import annotations

import ctypes
import sys
from typing import Sequence

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.bootstrap.config import AppConfig


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
    qt_app.setWindowIcon(QIcon())
    return qt_app
