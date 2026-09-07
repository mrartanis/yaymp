from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QWidget
from tests.unit.test_system_media import StubLogger, StubPlaybackController

from app.application.playback_service import PlaybackSnapshot
from app.domain import PlaybackState, PlaybackStatus, QueueItem, Track
from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache
from app.presentation.qt.system_media import (
    LinuxMprisIntegration,
    MacOSSystemMediaIntegration,
    WindowsSystemMediaIntegration,
)


def snapshot(position=0, status=PlaybackStatus.PLAYING):
    item = QueueItem(
        Track(
            "123",
            "Title",
            ("Artist",),
            duration_ms=180_000,
            artwork_ref="https://example.test/cover",
        )
    )
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
    integration = LinuxMprisIntegration(
        playback_controller=StubPlaybackController(),
        artwork_cache=cache,
        window=window,
        logger=StubLogger(),
    )
    connection = RecordingConnection()
    integration._connection = connection
    integration.update_snapshot(snapshot())
    assert "Position" not in connection.messages[0].arguments()[1]
    connection.messages.clear()
    original_exists = Path.exists
    checks = []

    def exists(path):
        checks.append(path)
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists)
    for pos in range(1000, 31_000, 1000):
        integration.update_snapshot(snapshot(pos))
    assert connection.messages == []
    assert checks == []
    assert integration._state.position_us == 30_000_000

    paused = snapshot(30_000, PlaybackStatus.PAUSED)
    integration.update_snapshot(paused)
    assert connection.messages[-1].arguments()[1] == {"PlaybackStatus": "Paused"}
    connection.messages.clear()
    for _ in range(30):
        integration.update_snapshot(paused)
    assert connection.messages == []

    url = cache.normalize_url(paused.current_item.track.artwork_ref)
    cache.save_bytes(cache.cache_path_for_url(url), b"cover")
    integration.update_snapshot(paused)
    changed = connection.messages[-1].arguments()[1]
    assert set(changed) == {"Metadata"}
    assert changed["Metadata"]["mpris:artUrl"].startswith("file:")

    empty = PlaybackSnapshot((), PlaybackState(), None)
    integration.update_snapshot(empty)
    connection.messages.clear()
    integration.update_snapshot(empty)
    assert connection.messages == []


def test_mpris_emits_seeked_once_even_for_small_seek(qtbot, tmp_path):
    window = QWidget()
    qtbot.addWidget(window)
    integration = LinuxMprisIntegration(
        playback_controller=StubPlaybackController(),
        artwork_cache=FileArtworkCache(cache_dir=tmp_path),
        window=window,
        logger=StubLogger(),
    )
    connection = RecordingConnection()
    integration._connection = connection
    integration.update_snapshot(snapshot())
    connection.messages.clear()
    sought = replace(snapshot(100), seek_revision=1)
    integration.update_snapshot(sought)
    integration.update_snapshot(sought)
    assert [m.member() for m in connection.messages] == ["Seeked"]


def mac_integration(tmp_path):
    cache = FileArtworkCache(cache_dir=tmp_path)
    integration = MacOSSystemMediaIntegration(
        playback_controller=StubPlaybackController(), artwork_cache=cache, logger=StubLogger()
    )
    center = MagicMock()
    media = SimpleNamespace(
        **{
            key: key
            for key in (
                "MPMediaItemPropertyTitle",
                "MPMediaItemPropertyArtist",
                "MPMediaItemPropertyAlbumTitle",
                "MPMediaItemPropertyPlaybackDuration",
                "MPNowPlayingInfoPropertyElapsedPlaybackTime",
                "MPNowPlayingInfoPropertyPlaybackRate",
                "MPMediaItemPropertyArtwork",
            )
        }
    )
    media.MPNowPlayingInfoCenter = SimpleNamespace(defaultCenter=lambda: center)
    media.MPMediaItemArtwork = MagicMock()
    integration._media_player = media
    integration._foundation = MagicMock()
    integration._ns_image = MagicMock()
    integration._initialized = True
    return integration, cache, center


def test_macos_reuses_art_and_only_publishes_meaningful_changes(tmp_path, monkeypatch):
    integration, cache, center = mac_integration(tmp_path)
    clock = [0.0]
    monkeypatch.setattr(
        "app.presentation.qt.system_media.monotonic", lambda: clock[0], raising=False
    )
    url = snapshot().current_item.track.artwork_ref
    cache.save_bytes(cache.cache_path_for_url(url), b"cover")
    integration.update_snapshot(snapshot())
    for pos in range(1000, 31_000, 1000):
        clock[0] = pos / 1000
        integration.update_snapshot(snapshot(pos))
    assert center.setNowPlayingInfo_.call_count == 1
    assert integration._ns_image.alloc.return_value.initWithContentsOfFile_.call_count == 1
    paused = snapshot(30_000, PlaybackStatus.PAUSED)
    integration.update_snapshot(paused)
    for _ in range(30):
        integration.update_snapshot(paused)
    assert center.setNowPlayingInfo_.call_count == 2
    sought = replace(paused, state=replace(paused.state, position_ms=30_100), seek_revision=1)
    integration.update_snapshot(sought)
    assert center.setNowPlayingInfo_.call_count == 3
    assert integration._ns_image.alloc.return_value.initWithContentsOfFile_.call_count == 1
    empty = PlaybackSnapshot((), PlaybackState(), None)
    integration.update_snapshot(empty)
    integration.update_snapshot(empty)
    integration.shutdown()
    assert center.setNowPlayingInfo_.call_count == 4
    integration.update_snapshot(sought)
    assert center.setNowPlayingInfo_.call_count == 5


def test_macos_publishes_late_art_and_metadata_changes(tmp_path):
    integration, cache, center = mac_integration(tmp_path)
    initial = snapshot(status=PlaybackStatus.PAUSED)
    integration.update_snapshot(initial)
    url = initial.current_item.track.artwork_ref
    cache.save_bytes(cache.cache_path_for_url(url), b"cover")
    integration.update_snapshot(initial)
    assert center.setNowPlayingInfo_.call_count == 2
    assert integration._ns_image.alloc.return_value.initWithContentsOfFile_.call_count == 1
    item = replace(
        initial.current_item, track=replace(initial.current_item.track, title="New title")
    )
    integration.update_snapshot(replace(initial, current_item=item, queue=(item,)))
    assert center.setNowPlayingInfo_.call_count == 3
    assert integration._ns_image.alloc.return_value.initWithContentsOfFile_.call_count == 1


def test_windows_updates_metadata_separately_from_timeline(tmp_path):
    from tests.unit.test_system_media import StubWindowsPlaybackStatus, StubWindowsRepeatMode

    integration = WindowsSystemMediaIntegration(
        playback_controller=StubPlaybackController(),
        artwork_cache=FileArtworkCache(cache_dir=tmp_path),
        window=None,
        logger=StubLogger(),
    )
    integration._smtc = MagicMock()
    display = integration._display_updater = MagicMock()
    integration._media_playback_status = StubWindowsPlaybackStatus
    integration._media_playback_type = SimpleNamespace(MUSIC="music")
    integration._media_repeat_mode = StubWindowsRepeatMode
    integration._timeline_properties_cls = SimpleNamespace
    integration.update_snapshot(snapshot())
    for pos in range(1000, 31_000, 1000):
        integration.update_snapshot(snapshot(pos))
    assert display.update.call_count == 1
    assert integration._smtc.update_timeline_properties.call_count == 31
    paused = snapshot(30_000, PlaybackStatus.PAUSED)
    for _ in range(30):
        integration.update_snapshot(paused)
    assert display.update.call_count == 1
    assert integration._smtc.update_timeline_properties.call_count == 31
    assert integration._smtc.playback_status == "paused"
    item = replace(paused.current_item, track=replace(paused.current_item.track, title="New"))
    integration.update_snapshot(replace(paused, current_item=item, queue=(item,)))
    assert display.update.call_count == 2
    assert display.music_properties.title == "New"
    empty = PlaybackSnapshot((), PlaybackState(), None)
    for _ in range(30):
        integration.update_snapshot(empty)
    assert display.clear_all.call_count == 1
    assert display.update.call_count == 3
    integration.update_snapshot(paused)
    assert display.update.call_count == 4
