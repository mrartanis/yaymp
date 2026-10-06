from __future__ import annotations

import base64
import time
import urllib.error
import urllib.request

import pytest

from app.domain import Track
from app.infrastructure.playback.stream_proxy_service import StreamProxyService
from tests.fakes.http_origin import HttpOrigin

_SHORT_TONE_MP3 = base64.b64decode(
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAASW5mbwAAAA8AAAAFAAAC2gBtbW1tbW1tbW1tbW1tbW1t"
    "bW1tkpKSkpKSkpKSkpKSkpKSkpKSkpK2tra2tra2tra2tra2tra2tra2ttvb29vb29vb29vb29vb"
    "29vb29vb//////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAZ4AAAA"
    "AAAAAtqZ460sAAAAAAAAAAAAAAAAAAAAAP/7EGQAAAB5BtOFMAAKAAANIKAAAQQIM0oZoQAAAAA0"
    "gwAAABLEszjOBABAGhMfu2+Hh5eYQ8JQFaVgCjDWAYaDxF0bYXXGhq//fCgPgINcKgr9igIABvGl"
    "uTRn6oCSsth2mpqbJ0DX//sSZAoD8IwG0y9oAAgAAA0g4AABAkQdVoDhIOAAADSAAAAEgAQU7+RM"
    "AZQvsO/G0AjR5Wlp0HIhBjRPA0MEZaSkkAUd/Ckia8zd3DXCErHUiEYjGCoAAC7AYDAYDAYAAAAA"
    "CIOsDesB//sQZBqP8IgHUAGbMJgAAA0gAAABAgQbSBWgACAAADSCgAAEbCNETNWaenVeQv4sWn+Q"
    "Qd/pcf/ABMNRA1VthSoNhTIyxTBQbo4BQAK8FBwJvwehCJAv/wfCcRCI2/8TlSJKTEFNRTP/+xJk"
    "K4ABShZZbjRAAAAADSDAAAAFEIFMGTOAAAAANIMAAAAuMTAwqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    "qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqr/+xBkJQ/wAABpBwAA"
    "CAAADSDgAAEAAAGkAAAAIAAANIAAAASqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"
    "qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqg=="
)


class RecordingLogger:
    def __init__(self) -> None:
        self.debug_messages: list[str] = []
        self.warning_messages: list[str] = []

    def debug(self, message: str, *args: object) -> None:
        self.debug_messages.append(message % args if args else message)

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        self.warning_messages.append(message % args if args else message)

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


class RecordingTrackCache:
    def __init__(self) -> None:
        self.saved_tracks: list[Track] = []

    def save_track_metadata(self, track: Track) -> None:
        self.saved_tracks.append(track)


def _read(url: str, *, range_header: str | None = None) -> tuple[int, bytes, object]:
    request = urllib.request.Request(url)
    if range_header:
        request.add_header("Range", range_header)
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, response.read(), response.headers


def _wait_until(predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition was not reached before timeout")
        time.sleep(0.01)


def test_proxy_forwards_get_head_and_session_lifecycle() -> None:
    body = bytes(range(256)) * 512
    logger = RecordingLogger()
    service = StreamProxyService(logger=logger)
    try:
        with HttpOrigin(body) as origin:
            track = Track("track-1", "Track", ("Artist",), duration_ms=120_000)
            proxy_url = service.create_session(track=track, stream_ref=origin.url)

            status, received, headers = _read(proxy_url)
            assert status == 200
            assert received == body
            assert headers.get_content_type() == "application/octet-stream"
            assert service.get_waveform_state(track.id).buffered_position_ms == 120_000

            head = urllib.request.Request(proxy_url, method="HEAD")
            with urllib.request.urlopen(head, timeout=3) as response:
                assert response.status == 200
                assert response.read() == b""
                assert int(response.headers["Content-Length"]) == len(body)

            assert origin.requests == [("GET", None), ("HEAD", None)]
            with pytest.raises(urllib.error.HTTPError) as missing:
                _read(f"http://127.0.0.1:{service.port}/stream/missing")
            assert missing.value.code == 404

            service.close_track_session(track.id)
            with pytest.raises(urllib.error.HTTPError) as closed:
                _read(proxy_url)
            assert closed.value.code == 404
            assert service.get_waveform_state(track.id).buffered_position_ms is None
    finally:
        service.shutdown()


def test_proxy_reassembles_out_of_order_ranges_for_buffer_progress() -> None:
    body = b"0123456789"
    service = StreamProxyService(logger=RecordingLogger())
    try:
        with HttpOrigin(body) as origin:
            track = Track("range-track", "Ranges", ("Artist",), duration_ms=10_000)
            proxy_url = service.create_session(track=track, stream_ref=origin.url)

            status, received, headers = _read(proxy_url, range_header="bytes=5-9")
            assert (status, received, headers["Content-Range"]) == (
                206,
                b"56789",
                "bytes 5-9/10",
            )
            assert service.get_waveform_state(track.id).buffered_position_ms == 0

            status, received, _headers = _read(proxy_url, range_header="bytes=0-4")
            assert (status, received) == (206, b"01234")
            assert service.get_waveform_state(track.id).buffered_position_ms == 10_000
            assert origin.requests == [("GET", "bytes=5-9"), ("GET", "bytes=0-4")]
    finally:
        service.shutdown()


def test_proxy_propagates_origin_errors_and_recovers_with_a_new_session() -> None:
    logger = RecordingLogger()
    service = StreamProxyService(logger=logger)
    track = Track("failure-track", "Failure", ("Artist",), duration_ms=10_000)
    try:
        with HttpOrigin(b"unavailable", status=404) as failing_origin:
            failing_url = service.create_session(track=track, stream_ref=failing_origin.url)
            with pytest.raises(urllib.error.HTTPError) as response:
                _read(failing_url)
            assert response.value.code == 404

        with pytest.raises(urllib.error.HTTPError) as unavailable:
            _read(failing_url)
        assert unavailable.value.code == 502
        assert any("Stream proxy failed" in message for message in logger.warning_messages)

        with HttpOrigin(b"recovered") as recovered_origin:
            recovered_url = service.create_session(track=track, stream_ref=recovered_origin.url)
            assert _read(recovered_url)[:2] == (200, b"recovered")
    finally:
        service.shutdown()


def test_full_mp3_download_builds_and_caches_waveform() -> None:
    cache = RecordingTrackCache()
    service = StreamProxyService(
        logger=RecordingLogger(),
        library_cache_repo=cache,
    )
    try:
        with HttpOrigin(_SHORT_TONE_MP3, content_type="audio/mpeg") as origin:
            track = Track("tone", "Tone", ("Generator",), duration_ms=80)
            proxy_url = service.create_session(track=track, stream_ref=origin.url)
            assert _read(proxy_url)[1] == _SHORT_TONE_MP3

            _wait_until(
                lambda: service.get_waveform_state(track.id).waveform_mode == "ready",
                timeout=15,
            )
            state = service.get_waveform_state(track.id)
            assert len(state.waveform_bins) == 100
            assert max(state.waveform_bins) == pytest.approx(1.0)
            assert state.waveform_known_position_ms == track.duration_ms
            assert cache.saved_tracks[-1].id == track.id
            assert cache.saved_tracks[-1].waveform_bins == state.waveform_bins
    finally:
        service.shutdown()
