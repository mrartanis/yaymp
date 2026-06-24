from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_FILL_DOUBLE_QUOTED_RE = re.compile(r'(?<!data-fixed-)fill="(?!none)([^"]*)"')
_FILL_SINGLE_QUOTED_RE = re.compile(r"(?<!data-fixed-)fill='(?!none)([^']*)'")
_STROKE_DOUBLE_QUOTED_RE = re.compile(r'(?<!data-fixed-)stroke="(?!none)([^"]*)"')
_STROKE_SINGLE_QUOTED_RE = re.compile(r"(?<!data-fixed-)stroke='(?!none)([^']*)'")
_PATH_WITHOUT_FILL_RE = re.compile(r'(<path\b(?![^>]*\bfill=)[^>]*?)(\s*/?>)')
_FIXED_FILL_DOUBLE_QUOTED_RE = re.compile(r'data-fixed-fill="([^"]*)"')
_FIXED_FILL_SINGLE_QUOTED_RE = re.compile(r"data-fixed-fill='([^']*)'")
_FIXED_STROKE_DOUBLE_QUOTED_RE = re.compile(r'data-fixed-stroke="([^"]*)"')
_FIXED_STROKE_SINGLE_QUOTED_RE = re.compile(r"data-fixed-stroke='([^']*)'")


@lru_cache(maxsize=128)
def create_icon(name: str, color: str = "#ffffff", size: int = 20) -> QIcon:
    svg_text = _recolor_svg(_read_icon_svg(name), color)
    renderer = QSvgRenderer(bytes(svg_text, "utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return QIcon(pixmap)


def _read_icon_svg(name: str) -> str:
    icon_path = resources.files("app.presentation.qt").joinpath("icons_svg", name)
    return icon_path.read_text(encoding="utf-8")


def _recolor_svg(svg_text: str, color: str) -> str:
    svg_text = _FILL_DOUBLE_QUOTED_RE.sub(f'fill="{color}"', svg_text)
    svg_text = _FILL_SINGLE_QUOTED_RE.sub(f"fill='{color}'", svg_text)
    svg_text = _STROKE_DOUBLE_QUOTED_RE.sub(f'stroke="{color}"', svg_text)
    svg_text = _STROKE_SINGLE_QUOTED_RE.sub(f"stroke='{color}'", svg_text)
    svg_text = _PATH_WITHOUT_FILL_RE.sub(rf'\1 fill="{color}"\2', svg_text)
    svg_text = _FIXED_FILL_DOUBLE_QUOTED_RE.sub(r'fill="\1"', svg_text)
    svg_text = _FIXED_FILL_SINGLE_QUOTED_RE.sub(r"fill='\1'", svg_text)
    svg_text = _FIXED_STROKE_DOUBLE_QUOTED_RE.sub(r'stroke="\1"', svg_text)
    svg_text = _FIXED_STROKE_SINGLE_QUOTED_RE.sub(r"stroke='\1'", svg_text)
    return svg_text
