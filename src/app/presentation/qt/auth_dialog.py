from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout

YANDEX_MUSIC_OAUTH_URL = (
    "https://oauth.yandex.ru/authorize"
    "?response_type=token"
    "&client_id=23cabbbdc6cd418abb4b39c32c41195d"
)


class AuthDialog(QDialog):
    token_captured = Signal(str, object)

    def __init__(self, *, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Yandex Music Login")
        self.resize(920, 720)

        layout = QVBoxLayout(self)
        self._status_label = QLabel(
            "Sign in to Yandex Music. The app will capture the OAuth token automatically."
        )
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._web_view = QWebEngineView(self)
        self._web_view.urlChanged.connect(self._handle_url_changed)
        layout.addWidget(self._web_view, 1)
        self._web_view.load(QUrl(YANDEX_MUSIC_OAUTH_URL))

    def _handle_url_changed(self, url: QUrl) -> None:
        parsed = urlparse(url.toString())
        if not parsed.netloc.startswith("music.yandex."):
            return
        if not parsed.fragment:
            return

        fragment = parse_qs(parsed.fragment, keep_blank_values=True, strict_parsing=False)
        access_token = fragment.get("access_token", [None])[0]
        expires_in_raw = fragment.get("expires_in", [None])[0]
        if not access_token:
            return

        expires_in = int(expires_in_raw) if expires_in_raw and expires_in_raw.isdigit() else None
        self.token_captured.emit(access_token, expires_in)
        self.accept()
