import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage, QPainter

from app.presentation.qt.waveform_seek_bar import WaveformSeekBar


def _render(widget):
    image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    widget.render(painter, QPoint())
    painter.end()
    return image


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_cached_geometry_matches_fresh_render_after_state_changes(qtbot, theme):
    cached = WaveformSeekBar()
    qtbot.addWidget(cached)
    for width, maximum, bins, known in (
        (320, 300000, (), 0),
        (700, 300000, (.1, .5, .9), 150000),
        (320, 200000, (.1, .5, .9), 200000),
        (320, 200000, (.9, .1, .4), 200000),
        (500, 200000, (.7,), 100000),
    ):
        fresh = WaveformSeekBar()
        qtbot.addWidget(fresh)
        for widget in (cached, fresh):
            widget.resize(width, 40)
            widget.setMaximum(maximum)
            widget.set_waveform_enabled(True)
            widget.set_visuals(accent="#526ee8", theme_mode=theme, rounded=True)
            widget.set_waveform_state(
                buffered_position_ms=maximum, waveform_bins=bins,
                waveform_known_position_ms=known, waveform_mode="loading",
            )
        for position in (0, maximum // 2, maximum):
            cached.setValue(position)
            fresh.setValue(position)
            assert _render(cached) == _render(fresh)
        cached.set_waveform_enabled(False)
        fresh.set_waveform_enabled(False)
        assert _render(cached) == _render(fresh)
