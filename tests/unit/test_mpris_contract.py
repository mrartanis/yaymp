from dataclasses import replace

from PySide6.QtCore import QObject
from PySide6.QtDBus import QDBusObjectPath
from PySide6.QtWidgets import QWidget
from tests.unit.test_system_media import StubLogger, StubPlaybackController
from tests.unit.test_system_media_updates import snapshot

from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache
from app.presentation.qt.system_media import LinuxMprisIntegration, _MprisPlayerAdaptor


def test_mpris_exports_64_bit_position_and_object_path_seek(qtbot, tmp_path):
    window = QWidget()
    qtbot.addWidget(window)
    controller = StubPlaybackController()
    integration = LinuxMprisIntegration(
        playback_controller=controller,
        artwork_cache=FileArtworkCache(cache_dir=tmp_path),
        window=window,
        logger=StubLogger(),
    )
    integration._root_object = QObject()
    adaptor = _MprisPlayerAdaptor(integration)
    meta = adaptor.metaObject()
    assert meta.property(meta.indexOfProperty("Position")).typeName() == "qlonglong"
    assert meta.indexOfMethod("Seek(qlonglong)") >= 0
    assert meta.indexOfMethod("SetPosition(QDBusObjectPath,qlonglong)") >= 0
    initial = snapshot(3_000_000)
    item = replace(
        initial.current_item,
        track=replace(initial.current_item.track, id="track-1:two/три", duration_ms=6_000_000),
    )
    integration.update_snapshot(replace(initial, queue=(item,), current_item=item))
    path = integration._state.metadata["mpris:trackid"]
    assert path.path()
    assert path.path() != integration._track_object_path("track_1:two/три").path()
    assert adaptor.property("Position") == 3_000_000_000
    adaptor.Seek(3_000_000_000)
    assert controller.position_ms == 6_000_000
    adaptor.SetPosition(path, 4_000_000_000)
    assert controller.position_ms == 4_000_000
    adaptor.SetPosition(QDBusObjectPath("/wrong"), 100)
    adaptor.SetPosition(path, -1)
    adaptor.SetPosition(path, 7_000_000_000)
    assert controller.position_ms == 4_000_000
