from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.application.demo_library import build_demo_tracks
from app.application.playback_service import PlaybackService
from app.bootstrap.config import AppConfig
from app.domain import Track
from app.domain.errors import PlaybackBackendError
from app.infrastructure.playback.fake_playback_engine import FakePlaybackEngine
from app.infrastructure.playback.mpv_playback_engine import MpvPlaybackEngine


@dataclass(slots=True)
class AppServices:
    playback_engine: FakePlaybackEngine | MpvPlaybackEngine
    playback_service: PlaybackService
    demo_tracks: tuple[Track, ...]


@dataclass(slots=True)
class AppContainer:
    config: AppConfig
    logger: logging.Logger
    services: AppServices


def build_container(config: AppConfig, logger: logging.Logger) -> AppContainer:
    logger.debug("Building application container")
    playback_engine = _build_playback_engine(logger)
    playback_service = PlaybackService(
        playback_engine=playback_engine,
        logger=logger,
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
            playback_engine=playback_engine,
            playback_service=playback_service,
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
