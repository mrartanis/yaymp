from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QColor, QImage

from app.bootstrap.config import load_config
from app.bootstrap.startup import StartupContext, build_startup_context
from app.domain import (
    Album,
    AuthSession,
    CatalogSearchResults,
    PlaybackStatus,
    Playlist,
    Track,
)
from app.infrastructure.persistence import FileAuthRepo
from app.presentation.qt.library_controller import BrowserItem
from tests.fakes.http_origin import HttpOrigin
from tests.fakes.music_service import FakeMusicService


def _build_app(
    *,
    root: Path,
    music: FakeMusicService,
    qapp,
    qtbot,
    monkeypatch,
) -> StartupContext:
    for name in ("CONFIG", "DATA", "CACHE", "LOG"):
        monkeypatch.setenv(f"YAYMP_{name}_DIR", str(root / name.lower()))
    monkeypatch.setenv("YAYMP_PLAYBACK_BACKEND", "fake")
    config = load_config()
    if music.session is not None:
        FileAuthRepo(file_path=config.auth_session_file).save_session(music.session)
    context = build_startup_context(
        argv=["yaymp-integration-test"],
        existing_qt_app=qapp,
        music_service=music,
    )
    qtbot.addWidget(context.main_window)
    context.main_window._playback_poll_timer.stop()
    context.main_window.show()
    return context


def _visible_browser_items(context: StartupContext) -> tuple[BrowserItem, ...]:
    content_list = context.main_window._content_list
    return tuple(
        browser_item
        for row in range(content_list.count())
        if isinstance(
            browser_item := content_list.item(row).data(Qt.ItemDataRole.UserRole),
            BrowserItem,
        )
    )


def _open_browser_row(context: StartupContext, qtbot, row: int = 0) -> None:
    content_list = context.main_window._content_list
    item = content_list.item(row)
    content_list.scrollToItem(item)
    content_list.setCurrentItem(item)
    content_list.itemDoubleClicked.emit(item)
    qtbot.wait(1)


def _search_and_play(
    context: StartupContext,
    *,
    query: str,
    track_id: str,
    qtbot,
) -> None:
    window = context.main_window
    window._search_input.setText(query)
    qtbot.mouseClick(window._search_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(
        lambda: any(
            item.kind == "track" and getattr(item.payload, "id", None) == track_id
            for item in _visible_browser_items(context)
        )
    )
    row = next(
        row
        for row, item in enumerate(_visible_browser_items(context))
        if item.kind == "track" and getattr(item.payload, "id", None) == track_id
    )
    _open_browser_row(context, qtbot, row)
    qtbot.waitUntil(lambda: window._queue_model.rowCount() == 1)
    qtbot.waitUntil(
        lambda: context.container.services.playback_engine.get_state().status
        is PlaybackStatus.PLAYING
    )


def _music_with_search_result() -> tuple[FakeMusicService, Track]:
    session = AuthSession(
        user_id="listener-1",
        token="fake-token",
        display_name="Listener",
    )
    music = FakeMusicService(session=session)
    track = Track(
        id="track-1",
        title="Orbital Song",
        artists=("Example Artist",),
        artist_ids=("artist-1",),
        album_id="album-1",
        album_title="Example Album",
        duration_ms=180_000,
        stream_ref="fake://track-1",
    )
    album = Album(
        id="album-1",
        title="Example Album",
        artists=("Example Artist",),
        artist_ids=("artist-1",),
        track_count=1,
    )
    music.tracks[track.id] = track
    music.albums[album.id] = album
    music.catalog_searches["orbital"] = CatalogSearchResults(
        tracks=(track,),
        albums=(album,),
    )
    return music, track


def _png_bytes(color: str) -> bytes:
    image = QImage(96, 96, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    payload = QByteArray()
    buffer = QBuffer(payload)
    assert buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    buffer.close()
    return bytes(payload)


def test_search_play_and_like_updates_api_queue_and_persistent_cache(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    music, track = _music_with_search_result()
    context = _build_app(
        root=tmp_path,
        music=music,
        qapp=qapp,
        qtbot=qtbot,
        monkeypatch=monkeypatch,
    )
    try:
        _search_and_play(context, query="orbital", track_id=track.id, qtbot=qtbot)

        qtbot.mouseClick(context.main_window._like_track_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: track.id in music.liked_track_ids)
        qtbot.waitUntil(
            lambda: bool(context.main_window._queue_model.queue_item_at(0).track.is_liked)
        )

        cached = context.container.services.library_service.cached_track(track.id)
        assert cached is not None and cached.is_liked
        assert context.main_window._track_title_label.text() == track.title
        assert ("like_track", track.id) in music.events
    finally:
        context.main_window.close()


def test_generated_playlist_plays_and_remains_visible_from_cache_offline(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    session = AuthSession(user_id="listener-1", token="fake-token")
    online = FakeMusicService(session=session)
    tracks = (
        Track(
            id="generated-1",
            title="Generated One",
            artists=("Robot",),
            album_id="generated-album",
            duration_ms=60_000,
            stream_ref="fake://generated-1",
        ),
        Track(
            id="generated-2",
            title="Generated Two",
            artists=("Robot",),
            album_id="generated-album",
            duration_ms=70_000,
            stream_ref="fake://generated-2",
        ),
    )
    playlist = Playlist(id="generated-playlist", title="Daily Generator", is_generated=True)
    online.add_playlist(playlist, tracks=tracks, generated=True)
    first = _build_app(
        root=tmp_path,
        music=online,
        qapp=qapp,
        qtbot=qtbot,
        monkeypatch=monkeypatch,
    )
    try:
        qtbot.mouseClick(first.main_window._playlists_nav_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: any(
                item.kind == "generated_playlist" and item.payload.id == playlist.id
                for item in _visible_browser_items(first)
            )
        )
        row = next(
            row
            for row, item in enumerate(_visible_browser_items(first))
            if item.kind == "generated_playlist" and item.payload.id == playlist.id
        )
        _open_browser_row(first, qtbot, row)
        qtbot.waitUntil(lambda: first.main_window._browser_title_label.text() == playlist.title)
        qtbot.mouseClick(first.main_window._play_all_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: first.main_window._queue_model.rowCount() == len(tracks))
        current = first.container.services.playback_service.snapshot().current_item
        assert current is not None and current.track.id == tracks[0].id
    finally:
        first.main_window.close()

    offline = FakeMusicService(session=session)
    offline.offline = True
    second = _build_app(
        root=tmp_path,
        music=offline,
        qapp=qapp,
        qtbot=qtbot,
        monkeypatch=monkeypatch,
    )
    try:
        qtbot.mouseClick(second.main_window._playlists_nav_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: any(
                item.kind == "generated_playlist" and item.payload.id == playlist.id
                for item in _visible_browser_items(second)
            )
        )
        cached = second.container.services.library_service.load_cached_generated_playlists()
        assert [item.id for item in cached] == [playlist.id]
        restored = second.container.services.playback_service.snapshot().current_item
        assert restored is not None and restored.track.id == tracks[0].id
    finally:
        second.main_window.close()


def test_queue_can_be_saved_as_playlist_through_dialog(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    music, track = _music_with_search_result()
    context = _build_app(
        root=tmp_path,
        music=music,
        qapp=qapp,
        qtbot=qtbot,
        monkeypatch=monkeypatch,
    )
    try:
        _search_and_play(context, query="orbital", track_id=track.id, qtbot=qtbot)
        qtbot.waitUntil(lambda: context.main_window._save_queue_button.isEnabled())
        qtbot.mouseClick(context.main_window._save_queue_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: context.main_window._playlist_save_dialog is not None)
        dialog = context.main_window._playlist_save_dialog
        qtbot.waitUntil(dialog._destination_combo.isEnabled)
        dialog._title_input.setText("Saved from queue")
        qtbot.waitUntil(dialog._save_button.isEnabled)
        qtbot.mouseClick(dialog._save_button, Qt.MouseButton.LeftButton)

        qtbot.waitUntil(lambda: "created-1" in music.playlists)
        qtbot.waitUntil(lambda: context.main_window._playlist_save_dialog is None)
        assert music.playlists["created-1"].title == "Saved from queue"
        assert [item.id for item in music.playlist_tracks["created-1"]] == [track.id]
        assert "Saved from queue" in context.main_window._status_label.text()
    finally:
        context.main_window.close()


def test_playback_artwork_is_downloaded_and_reused_offline_after_restart(
    qapp,
    qtbot,
    tmp_path,
    monkeypatch,
) -> None:
    with HttpOrigin(_png_bytes("#336699"), content_type="image/png") as origin:
        online, original_track = _music_with_search_result()
        track = replace(original_track, artwork_ref=origin.url)
        online.tracks[track.id] = track
        online.catalog_searches["orbital"] = CatalogSearchResults(tracks=(track,))
        first = _build_app(
            root=tmp_path,
            music=online,
            qapp=qapp,
            qtbot=qtbot,
            monkeypatch=monkeypatch,
        )
        try:
            _search_and_play(first, query="orbital", track_id=track.id, qtbot=qtbot)
            artwork_cache = first.container.services.artwork_cache
            cache_path = artwork_cache.cache_path_for_url(origin.url)
            qtbot.waitUntil(cache_path.exists)
            qtbot.waitUntil(lambda: not first.main_window._artwork_label.pixmap().isNull())
            assert origin.requests
        finally:
            first.main_window.close()

    offline = FakeMusicService(session=online.session)
    offline.offline = True
    second = _build_app(
        root=tmp_path,
        music=offline,
        qapp=qapp,
        qtbot=qtbot,
        monkeypatch=monkeypatch,
    )
    try:
        qtbot.waitUntil(lambda: not second.main_window._artwork_label.pixmap().isNull())
        restored = second.container.services.playback_service.snapshot().current_item
        assert restored is not None and restored.track.id == track.id
        assert second.main_window._artwork_label.pixmap().toImage().pixelColor(1, 1).name() == (
            "#336699"
        )
    finally:
        second.main_window.close()
