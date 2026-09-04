from math import sin, tau

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter

from app.domain.playback import PlaybackStatus

IDLE_LEVELS = (0.42, 0.68, 0.54, 0.78, 0.62, 0.38)


def animated_levels(seconds: float) -> tuple[float, ...]:
    """Continuous decorative motion, independent of timer delivery jitter."""
    return tuple(
        0.55 + 0.25 * sin(tau * (seconds * (0.8 + index * 0.11) + index * 0.19))
        + 0.12 * sin(tau * (seconds * 1.7 + index * 0.31))
        for index in range(len(IDLE_LEVELS))
    )


def normalize_playback_status(value: object) -> PlaybackStatus:
    try:
        return PlaybackStatus(value)
    except (ValueError, TypeError):
        return PlaybackStatus.STOPPED


def paint_indicator(
    painter: QPainter,
    rect: QRect,
    color: QColor,
    levels: tuple[float, ...] = IDLE_LEVELS,
) -> None:
    """Draw the same bars for the static delegate and animated overlay."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    step = (rect.width() - 2.0) / max(1, len(levels))
    for index, factor in enumerate(levels):
        height = max(2.0, (rect.height() - 1) * factor)
        x = rect.left() + index * step + 1
        painter.drawRoundedRect(QRectF(x, rect.bottom() - height, step * 0.65, height), .6, .6)
    painter.restore()
