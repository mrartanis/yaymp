from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import QWidget
from tests.unit.test_system_media import StubLogger, StubPlaybackController

from app.application.playback_service import PlaybackSnapshot
from app.domain import PlaybackState, PlaybackStatus, QueueItem, Track
from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache
from app.presentation.qt.system_media import LinuxMprisIntegration


def snapshot(position=0, status=PlaybackStatus.PLAYING):
    item = QueueItem(Track('123', 'Title', ('Artist',), duration_ms=180_000,
                           artwork_ref='https://example.test/cover'))
    return PlaybackSnapshot((item,), PlaybackState(status=status, position_ms=position), item)


class RecordingConnection:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True


def test_mpris_only_publishes_changes_and_refreshes_downloaded_art(qtbot, tmp_path, monkeypatch):
    window = QWidget()
    qtbot.addWidget(window)
    cache = FileArtworkCache(cache_dir=tmp_path)
    integration = LinuxMprisIntegration(playback_controller=StubPlaybackController(),
                                       artwork_cache=cache, window=window, logger=StubLogger())
    connection = RecordingConnection()
    integration._connection = connection
    integration.update_snapshot(snapshot())
    assert 'Position' not in connection.messages[0].arguments()[1]
    connection.messages.clear()
    original_exists = Path.exists
    checks = []

    def exists(path):
        checks.append(path)
        return original_exists(path)

    monkeypatch.setattr(Path, 'exists', exists)
    for pos in range(1000, 31_000, 1000):
        integration.update_snapshot(snapshot(pos))
    assert connection.messages == []
    assert checks == []
    assert integration._state.position_us == 30_000_000

    paused = snapshot(30_000, PlaybackStatus.PAUSED)
    integration.update_snapshot(paused)
    assert connection.messages[-1].arguments()[1] == {'PlaybackStatus': 'Paused'}
    connection.messages.clear()
    for _ in range(30):
        integration.update_snapshot(paused)
    assert connection.messages == []

    url = cache.normalize_url(paused.current_item.track.artwork_ref)
    cache.save_bytes(cache.cache_path_for_url(url), b'cover')
    integration.update_snapshot(paused)
    changed = connection.messages[-1].arguments()[1]
    assert set(changed) == {'Metadata'}
    assert changed['Metadata']['mpris:artUrl'].startswith('file:')

    empty = PlaybackSnapshot((), PlaybackState(), None)
    integration.update_snapshot(empty)
    connection.messages.clear()
    integration.update_snapshot(empty)
    assert connection.messages == []


def test_mpris_emits_seeked_once_even_for_small_seek(qtbot, tmp_path):
    window = QWidget()
    qtbot.addWidget(window)
    integration = LinuxMprisIntegration(playback_controller=StubPlaybackController(),
        artwork_cache=FileArtworkCache(cache_dir=tmp_path), window=window, logger=StubLogger())
    connection = RecordingConnection()
    integration._connection = connection
    integration.update_snapshot(snapshot())
    connection.messages.clear()
    sought = replace(snapshot(100), seek_revision=1)
    integration.update_snapshot(sought)
    integration.update_snapshot(sought)
    assert [m.member() for m in connection.messages] == ['Seeked']

