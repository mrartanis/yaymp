from __future__ import annotations

import logging
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache
from app.presentation.qt.main_window_artwork import MainWindowArtworkMixin


class _ArtworkHarness(MainWindowArtworkMixin, QWidget):
    def __init__(self, *, cache_dir: Path) -> None:
        super().__init__()
        self._container = SimpleNamespace(
            services=SimpleNamespace(artwork_cache=FileArtworkCache(cache_dir=cache_dir)),
            logger=logging.getLogger("test-artwork"),
        )
        self._accent_color = "#526ee8"
        self._artwork_label = QLabel()
        self._pending_artwork_track_id = None
        self._thumb_source_pixmap_cache = OrderedDict()
        self._thumb_scaled_pixmap_cache = OrderedDict()

    def _apply_theme(self) -> None:
        return


def _write_image(path: Path, fill: str, *, center_fill: str | None = None) -> None:
    image = QImage(180, 180, QImage.Format.Format_ARGB32)
    image.fill(QColor(fill))
    if center_fill is not None:
        for y in range(45, 135):
            for x in range(45, 135):
                image.setPixelColor(x, y, QColor(center_fill))
    assert image.save(str(path))


def test_artwork_prefers_pixel_accent_over_api_color(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "pixel-first.png"
    _write_image(image_path, "#202020", center_fill="#db2f2f")

    window._set_artwork_pixmap(image_path, preferred_accent="#22aaee")

    assert window._accent_color != "#22aaee"
    assert window._accent_color != "#526ee8"
    cached = window._container.services.artwork_cache.load_accent_color(image_path)
    assert cached == window._accent_color


def test_artwork_falls_back_to_api_accent_when_pixels_are_unusable(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "api-fallback.png"
    _write_image(image_path, "#ffffff")

    window._set_artwork_pixmap(image_path, preferred_accent="#22aaee")

    assert window._accent_color == "#22aaee"
    assert window._container.services.artwork_cache.load_accent_color(image_path) == "#22aaee"


def test_artwork_falls_back_to_default_when_pixels_and_api_are_unusable(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "default-fallback.png"
    _write_image(image_path, "#ffffff")

    window._set_artwork_pixmap(image_path, preferred_accent="#111111")

    assert window._accent_color == "#526ee8"
    assert window._container.services.artwork_cache.load_accent_color(image_path) == "#526ee8"


def test_artwork_cache_has_priority_over_pixels_and_api(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "cache-priority.png"
    _write_image(image_path, "#202020", center_fill="#db2f2f")
    window._container.services.artwork_cache.save_accent_color(image_path, "#556677")

    window._set_artwork_pixmap(image_path, preferred_accent="#22aaee")

    assert window._accent_color == "#556677"


def test_thumb_source_pixmap_is_normalized_before_caching(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "large-thumb.png"
    image = QImage(512, 256, QImage.Format.Format_ARGB32)
    image.fill(QColor("#224466"))
    assert image.save(str(image_path))
    artwork_url = "https://example.test/large-thumb"

    cache_path = window._container.services.artwork_cache.cache_path_for_url(artwork_url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.replace(cache_path)

    pixmap = window._thumb_source_pixmap(artwork_url)

    assert pixmap is not None
    assert pixmap.width() == 64
    assert pixmap.height() == 32
    assert window._thumb_source_pixmap_cache[artwork_url].width() == 64


def test_thumb_source_pixmap_cache_evicts_oldest_entries(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    window._THUMB_SOURCE_PIXMAP_CACHE_LIMIT = 2

    for index in range(3):
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(f"#{index + 1:02x}{index + 1:02x}{index + 1:02x}"))
        window._store_thumb_source_pixmap(f"url-{index}", pixmap)

    assert list(window._thumb_source_pixmap_cache) == ["url-1", "url-2"]


def test_thumb_scaled_pixmap_cache_evicts_oldest_entries(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    window._THUMB_SCALED_PIXMAP_CACHE_LIMIT = 2
    artwork_url = "https://example.test/thumb"
    pixmap = QPixmap(128, 128)
    pixmap.fill(QColor("#336699"))
    window._store_thumb_source_pixmap(artwork_url, pixmap)

    window._thumb_pixmap_for_url(artwork_url, size=32)
    window._thumb_pixmap_for_url(artwork_url, size=48)
    window._thumb_pixmap_for_url(artwork_url, size=64)

    assert list(window._thumb_scaled_pixmap_cache) == [
        (artwork_url, 48),
        (artwork_url, 64),
    ]
