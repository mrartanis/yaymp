from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QPushButton, QWidget


class MyWaveButton(QPushButton):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._accent = QColor("#526ee8")
        self._accent_text = QColor("#ffffff")
        self._trailing = QColor("#d8e2f8")
        self._radius = 9
        self._animation_phase = 0.0
        self._animation_direction = 1.0
        self._animated = False
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._advance_animation)

    def set_visuals(
        self,
        *,
        accent: str,
        accent_text: str,
        trailing: str,
        rounded: bool,
    ) -> None:
        self._accent = QColor(accent)
        self._accent_text = QColor(accent_text)
        self._trailing = QColor(trailing)
        self._radius = 9 if rounded else 0
        self.update()

    def set_animated(self, animated: bool) -> None:
        if self._animated == animated:
            return
        self._animated = animated
        if animated:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._animation_phase = 0.0
            self._animation_direction = 1.0
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = self.rect().adjusted(0, 0, -1, -1)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        leading, ending = self._gradient_colors()
        gradient.setColorAt(0.0, leading)
        gradient.setColorAt(1.0, ending)

        painter.setPen(QPen(self._accent, 1))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, self._radius, self._radius)

        painter.setPen(self._accent_text)
        painter.setFont(self.font())
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())

    def _gradient_colors(self) -> tuple[QColor, QColor]:
        if self._animated:
            phase = 0.5 - 0.5 * math.cos((self._animation_phase / 100.0) * math.tau)
            leading = self._mix_colors(self._trailing, self._accent, 0.45 + phase * 0.45)
            ending = self._mix_colors(self._trailing, self._accent, 0.12 + phase * 0.36)
        else:
            leading = QColor(self._accent)
            ending = QColor(self._trailing)
        if self.isDown():
            leading = self._mix_colors(leading, QColor("#000000"), 0.12)
            ending = self._mix_colors(ending, QColor("#000000"), 0.12)
        elif self.underMouse():
            leading = self._mix_colors(leading, QColor("#ffffff"), 0.08)
            ending = self._mix_colors(ending, QColor("#ffffff"), 0.08)
        return leading, ending

    def _advance_animation(self) -> None:
        self._animation_phase += self._animation_direction * 4.0
        if self._animation_phase >= 100.0:
            self._animation_phase = 100.0
            self._animation_direction = -1.0
        elif self._animation_phase <= 0.0:
            self._animation_phase = 0.0
            self._animation_direction = 1.0
        self.update()

    def _mix_colors(self, first: QColor, second: QColor, ratio: float) -> QColor:
        ratio = max(0.0, min(1.0, ratio))
        inverse = 1.0 - ratio
        return QColor(
            round(first.red() * inverse + second.red() * ratio),
            round(first.green() * inverse + second.green() * ratio),
            round(first.blue() * inverse + second.blue() * ratio),
        )
