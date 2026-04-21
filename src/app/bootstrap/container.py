from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.application.auth_service import AuthService
from app.application.demo_library import build_demo_tracks
from app.application.library_service import LibraryService
from app.application.playback_service import PlaybackService
from app.application.search_service import SearchService
from app.bootstrap.config import AppConfig
from app.domain import MusicService, Track
from app.domain.errors import AuthError, PlaybackBackendError
from app.infrastructure.persistence import FileAuthRepo, FileLibraryCacheRepo
from app.infrastructure.playback.fake_playback_engine import FakePlaybackEngine
from app.infrastructure.playback.mpv_playback_engine import MpvPlaybackEngine
from app.infrastructure.yandex.yandex_music_service import YandexMusicService


@dataclass(slots=True)
class AppServices:
    auth_service: AuthService
    library_service: LibraryService
    music_service: MusicService
    playback_engine: FakePlaybackEngine | MpvPlaybackEngine
    playback_service: PlaybackService
    search_service: SearchService
    demo_tracks: tuple[Track, ...]


@dataclass(slots=True)
class AppContainer:
    config: AppConfig
    logger: logging.Logger
    services: AppServices


def build_container(config: AppConfig, logger: logging.Logger) -> AppContainer:
    logger.debug("Building application container")
    auth_service = AuthService(
        auth_repo=FileAuthRepo(file_path=config.auth_session_file),
        logger=logger,
    )
    restored_session = auth_service.restore_session()
    bootstrap_token = os.getenv("YAYMP_YANDEX_TOKEN")
    music_service = YandexMusicService(
        session=restored_session,
        token=bootstrap_token,
        logger=logger,
    )
    if restored_session is not None or bootstrap_token:
        token = restored_session.token if restored_session is not None else bootstrap_token
        assert token is not None
        try:
            auth_service.authenticate_with_token(
                token,
                music_service=music_service,
                expires_in=None,
            )
        except AuthError as exc:
            logger.warning("Failed to restore Yandex session: %s", exc)
            auth_service.clear_session()
            music_service = YandexMusicService(logger=logger)

    library_cache_repo = FileLibraryCacheRepo(file_path=config.recent_searches_file)
    search_service = SearchService(
        music_service=music_service,
        library_cache_repo=library_cache_repo,
        logger=logger,
    )
    library_service = LibraryService(
        music_service=music_service,
        library_cache_repo=library_cache_repo,
        logger=logger,
    )

    playback_engine = _build_playback_engine(logger)
    playback_service = PlaybackService(
        playback_engine=playback_engine,
        logger=logger,
        music_service=music_service,
    )
    demo_tracks = build_demo_tracks()
    playback_service.replace_queue(
        demo_tracks,
        start_index=0,
        source_type="demo",
        source_id="bootstrap-demo",
    )
    return AppContainer(
        config=config,
        logger=logger,
        services=AppServices(
            auth_service=auth_service,
            library_service=library_service,
            music_service=music_service,
            playback_engine=playback_engine,
            playback_service=playback_service,
            search_service=search_service,
            demo_tracks=demo_tracks,
        ),
    )


def _build_playback_engine(logger: logging.Logger) -> FakePlaybackEngine | MpvPlaybackEngine:
    backend_name = os.getenv("YAYMP_PLAYBACK_BACKEND", "fake").lower()
    if backend_name != "mpv":
        logger.info("Using fake playback backend")
        return FakePlaybackEngine()

    try:
        engine = MpvPlaybackEngine()
        logger.info("Using MPV playback backend")
        return engine
    except PlaybackBackendError as exc:
        logger.warning("Falling back to fake playback backend: %s", exc)
        return FakePlaybackEngine()
