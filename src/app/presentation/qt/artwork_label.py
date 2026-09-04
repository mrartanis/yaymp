from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel


class ArtworkLabel(QLabel):
    """Retain the original cover and rescale it when the display geometry changes."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self._source = QPixmap()
        self._scaled_key: tuple | None = None

    def setPixmap(self, pixmap: QPixmap) -> None:  # noqa: N802
        self._source = QPixmap(pixmap)
        self._scaled_key = None
        self._rescale()

    def clear(self) -> None:
        self._source = QPixmap()
        self._scaled_key = None
        super().clear()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._rescale()

    def event(self, event: QEvent) -> bool:
        result = super().event(event)
        if event.type() == QEvent.Type.DevicePixelRatioChange:
            self._rescale()
        return result

    def _rescale(self) -> None:
        source = getattr(self, "_source", None)
        if source is None or source.isNull():
            return
        size = self.contentsRect().size()
        dpr = self.devicePixelRatioF()
        key = (size.width(), size.height(), dpr)
        if key == self._scaled_key or size.isEmpty():
            return
        self._scaled_key = key
        pixels = QSize(max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr)))
        scaled = source.scaled(
            pixels, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        super().setPixmap(scaled)
