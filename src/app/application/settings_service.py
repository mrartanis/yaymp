from __future__ import annotations

from app.domain import AudioQuality, Logger, SettingsRepo
from app.domain.errors import StorageError


class SettingsService:
    _VOLUME_KEY = "volume"
    _AUDIO_QUALITY_KEY = "audio_quality"

    def __init__(self, *, settings_repo: SettingsRepo, logger: Logger) -> None:
        self._settings_repo = settings_repo
        self._logger = logger

    def load_volume(self, *, default: int = 100) -> int:
        value = self._load_value(self._VOLUME_KEY)
        if not isinstance(value, int):
            return default
        return max(0, min(100, value))

    def save_volume(self, volume: int) -> None:
        self._save_value(self._VOLUME_KEY, max(0, min(100, volume)))

    def load_audio_quality(self, *, default: AudioQuality = AudioQuality.HQ) -> AudioQuality:
        value = self._load_value(self._AUDIO_QUALITY_KEY)
        if not isinstance(value, str):
            return default
        try:
            return AudioQuality(value)
        except ValueError:
            return default

    def save_audio_quality(self, quality: AudioQuality) -> None:
        self._save_value(self._AUDIO_QUALITY_KEY, quality.value)

    def _load_value(self, key: str) -> object | None:
        try:
            settings = self._settings_repo.load_settings()
        except StorageError as exc:
            self._logger.warning("Failed to load setting %s: %s", key, exc)
            return None
        return settings.get(key)

    def _save_value(self, key: str, value: object) -> None:
        try:
            settings = dict(self._settings_repo.load_settings())
            settings[key] = value
            self._settings_repo.save_settings(settings)
        except StorageError as exc:
            self._logger.warning("Failed to save setting %s: %s", key, exc)
