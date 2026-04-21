from __future__ import annotations

import pytest

from app.domain import PlaybackBackendError
from app.infrastructure.playback import mpv_playback_engine
from app.infrastructure.playback.mpv_playback_engine import MpvPlaybackEngine


class MpvModuleStub:
    def __init__(self, player) -> None:
        self._player = player

    def MPV(self):
        return self._player


class PlayerStub:
    def __init__(
        self,
        *,
        fail_exact_seek: bool = False,
        fail_keyframes_seek: bool = False,
    ) -> None:
        self.fail_exact_seek = fail_exact_seek
        self.fail_keyframes_seek = fail_keyframes_seek
        self.command_calls = []
        self.volume = 100

    def command(self, name, amount, flags):
        self.command_calls.append((name, amount, flags))
        if flags == "absolute+exact" and self.fail_exact_seek:
            raise RuntimeError("exact seek rejected")
        if flags == "absolute+keyframes" and self.fail_keyframes_seek:
            raise RuntimeError("keyframes seek rejected")


def build_engine(monkeypatch: pytest.MonkeyPatch, player: PlayerStub) -> MpvPlaybackEngine:
    monkeypatch.setattr(
        mpv_playback_engine,
        "ensure_mpv_available",
        lambda: (MpvModuleStub(player), "/tmp/libmpv.dylib"),
    )
    return MpvPlaybackEngine()


def test_mpv_seek_uses_absolute_exact_seek(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerStub()
    engine = build_engine(monkeypatch, player)

    engine.seek(12_000)

    assert player.command_calls == [("seek", "12.000", "absolute+exact")]


def test_mpv_seek_falls_back_to_keyframes(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerStub(fail_exact_seek=True)
    engine = build_engine(monkeypatch, player)

    engine.seek(12_000)

    assert player.command_calls == [
        ("seek", "12.000", "absolute+exact"),
        ("seek", "12.000", "absolute+keyframes"),
    ]


def test_mpv_seek_reports_fallback_error(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerStub(fail_exact_seek=True, fail_keyframes_seek=True)
    engine = build_engine(monkeypatch, player)

    with pytest.raises(PlaybackBackendError, match="exact seek rejected"):
        engine.seek(12_000)
    with pytest.raises(PlaybackBackendError, match="keyframes seek rejected"):
        engine.seek(12_000)
