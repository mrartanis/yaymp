from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap

from app.presentation.qt.artwork_label import ArtworkLabel


def test_cover_resizes_from_original_and_does_not_return_after_clear(qtbot):
    label = ArtworkLabel()
    qtbot.addWidget(label)
    image = QImage(600, 600, QImage.Format.Format_RGB32)
    image.fill(QColor("#2288ff"))
    # Fine details must survive shrinking and expanding the label again.
    for x in range(0, 600, 3):
        image.setPixelColor(x, 300, QColor("#ff0000"))
    source = QPixmap.fromImage(image)
    label.resize(300, 300)
    label.show()
    label.setPixmap(source)
    qtbot.waitUntil(lambda: label.pixmap().deviceIndependentSize().width() == 300)

    label.resize(512, 512)
    qtbot.waitUntil(lambda: label.pixmap().deviceIndependentSize().width() == 512)
    expected = source.scaled(
        label.pixmap().size(), Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    expected.setDevicePixelRatio(label.devicePixelRatioF())
    assert label.pixmap().toImage() == expected.toImage()

    label.clear()
    label.setText("No cover")
    label.resize(300, 300)
    assert label.pixmap().isNull()
    assert label.text() == "No cover"
