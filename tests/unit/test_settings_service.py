from __future__ import annotations

from app.application.settings_service import SettingsService
from app.domain import AudioQuality
from app.domain.errors import StorageError


class RecordingLogger:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, message: str, *args: object) -> None:
        del message, args

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        self.warnings.append(message % args)

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


class InMemorySettingsRepo:
    def __init__(self, settings=None) -> None:
        self.settings = dict(settings or {})

    def load_settings(self):
        return self.settings

    def save_settings(self, settings):
        self.settings = dict(settings)


class BrokenSettingsRepo(InMemorySettingsRepo):
    def load_settings(self):
        raise StorageError("broken")


def test_settings_service_round_trips_volume_and_audio_quality() -> None:
    repo = InMemorySettingsRepo()
    service = SettingsService(settings_repo=repo, logger=RecordingLogger())

    service.save_volume(42)
    service.save_audio_quality(AudioQuality.SD)
    service.save_theme_preference("dark")

    assert service.load_volume() == 42
    assert service.load_audio_quality() is AudioQuality.SD
    assert service.load_theme_preference() == "dark"


def test_settings_service_clamps_volume_and_defaults_invalid_quality() -> None:
    service = SettingsService(
        settings_repo=InMemorySettingsRepo(
            {"volume": 500, "audio_quality": "bad", "theme": "neon"}
        ),
        logger=RecordingLogger(),
    )

    assert service.load_volume() == 100
    assert service.load_audio_quality() is AudioQuality.HQ
    assert service.load_theme_preference() == "system"


def test_settings_service_logs_storage_failures_and_uses_defaults() -> None:
    logger = RecordingLogger()
    service = SettingsService(settings_repo=BrokenSettingsRepo(), logger=logger)

    assert service.load_volume(default=77) == 77

    service.save_volume(25)

    assert logger.warnings
