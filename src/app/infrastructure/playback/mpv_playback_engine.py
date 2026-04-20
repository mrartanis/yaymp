from __future__ import annotations

from app.domain import PlaybackEngine, PlaybackState, PlaybackStatus, Track
from app.domain.errors import PlaybackBackendError
from app.infrastructure.playback.mpv_loader import ensure_mpv_available


class MpvPlaybackEngine(PlaybackEngine):
    def __init__(self) -> None:
        mpv_module, library_path = ensure_mpv_available()
        del library_path
        self._player = mpv_module.MPV()
        self._state = PlaybackState()

    def load(self, track: Track, *, stream_ref: str) -> None:
        if not stream_ref:
            raise PlaybackBackendError("MPV backend requires a stream reference")

        try:
            self._player.play(stream_ref)
            self._player.pause = True
        except Exception as exc:  # noqa: BLE001
            raise PlaybackBackendError(f"Failed to load track {track.id}") from exc

        self._state = PlaybackState(
            status=PlaybackStatus.PAUSED,
            position_ms=0,
            duration_ms=track.duration_ms,
            volume=int(getattr(self._player, "volume", 100)),
        )

    def play(self) -> None:
        try:
            self._player.pause = False
        except Exception as exc:  # noqa: BLE001
            raise PlaybackBackendError("Failed to resume playback") from exc
        self._state = PlaybackState(
            status=PlaybackStatus.PLAYING,
            position_ms=self._state.position_ms,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
        )

    def pause(self) -> None:
        try:
            self._player.pause = True
        except Exception as exc:  # noqa: BLE001
            raise PlaybackBackendError("Failed to pause playback") from exc
        self._state = PlaybackState(
            status=PlaybackStatus.PAUSED,
            position_ms=self._state.position_ms,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
        )

    def stop(self) -> None:
        try:
            self._player.stop()
        except Exception as exc:  # noqa: BLE001
            raise PlaybackBackendError("Failed to stop playback") from exc
        self._state = PlaybackState(
            status=PlaybackStatus.STOPPED,
            position_ms=0,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
        )

    def seek(self, position_ms: int) -> None:
        try:
            self._player.seek(position_ms / 1000.0, reference="absolute")
        except Exception as exc:  # noqa: BLE001
            raise PlaybackBackendError("Failed to seek playback") from exc
        self._state = PlaybackState(
            status=self._state.status,
            position_ms=position_ms,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
        )

    def set_volume(self, volume: int) -> None:
        try:
            self._player.volume = volume
        except Exception as exc:  # noqa: BLE001
            raise PlaybackBackendError("Failed to change volume") from exc
        self._state = PlaybackState(
            status=self._state.status,
            position_ms=self._state.position_ms,
            duration_ms=self._state.duration_ms,
            volume=volume,
        )

    def get_state(self) -> PlaybackState:
        try:
            paused = bool(getattr(self._player, "pause", False))
            idle_active = bool(getattr(self._player, "idle_active", False))
            time_pos = getattr(self._player, "time_pos", None)
            duration = getattr(self._player, "duration", None)
            volume = int(getattr(self._player, "volume", self._state.volume))
        except Exception as exc:  # noqa: BLE001
            raise PlaybackBackendError("Failed to query playback state") from exc

        if idle_active:
            status = PlaybackStatus.STOPPED
        elif paused:
            status = PlaybackStatus.PAUSED
        else:
            status = PlaybackStatus.PLAYING

        self._state = PlaybackState(
            status=status,
            position_ms=int((time_pos or 0) * 1000),
            duration_ms=int(duration * 1000) if duration is not None else self._state.duration_ms,
            volume=volume,
        )
        return self._state
