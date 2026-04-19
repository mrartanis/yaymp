from __future__ import annotations

import logging
from dataclasses import dataclass

from app.bootstrap.config import AppConfig


@dataclass(slots=True)
class PlaceholderServices:
    music_service: object | None = None
    playback_engine: object | None = None
    settings_repo: object | None = None


@dataclass(slots=True)
class AppContainer:
    config: AppConfig
    logger: logging.Logger
    services: PlaceholderServices


def build_container(config: AppConfig, logger: logging.Logger) -> AppContainer:
    logger.debug("Building application container")
    return AppContainer(
        config=config,
        logger=logger,
        services=PlaceholderServices(),
    )
