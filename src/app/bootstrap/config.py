from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str
    app_author: str
    environment: str
    log_level: str
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    log_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "yaymp.log"

    @property
    def auth_session_file(self) -> Path:
        return self.data_dir / "auth_session.json"

    @property
    def recent_searches_file(self) -> Path:
        return self.library_cache_file

    @property
    def library_cache_file(self) -> Path:
        return self.cache_dir / "library_cache.json"

    def ensure_directories(self) -> None:
        for path in (self.config_dir, self.data_dir, self.cache_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)


def _resolve_path_override(value: str | None, fallback: Path) -> Path:
    if value:
        return Path(value).expanduser()
    return fallback


def load_config() -> AppConfig:
    app_name = os.getenv("YAYMP_APP_NAME", "YAYMP")
    app_author = os.getenv("YAYMP_APP_AUTHOR", "yaymp")
    environment = os.getenv("YAYMP_ENV", "development")
    log_level = os.getenv("YAYMP_LOG_LEVEL", "INFO").upper()

    dirs = PlatformDirs(appname=app_name, appauthor=app_author, roaming=False, ensure_exists=False)
    return AppConfig(
        app_name=app_name,
        app_author=app_author,
        environment=environment,
        log_level=log_level,
        config_dir=_resolve_path_override(
            os.getenv("YAYMP_CONFIG_DIR"),
            Path(dirs.user_config_dir),
        ),
        data_dir=_resolve_path_override(
            os.getenv("YAYMP_DATA_DIR"),
            Path(dirs.user_data_dir),
        ),
        cache_dir=_resolve_path_override(
            os.getenv("YAYMP_CACHE_DIR"),
            Path(dirs.user_cache_dir),
        ),
        log_dir=_resolve_path_override(
            os.getenv("YAYMP_LOG_DIR"),
            Path(dirs.user_log_dir),
        ),
    )
