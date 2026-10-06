from __future__ import annotations

import http.server
import os
import ssl
import struct
import threading
import urllib.error
import urllib.request
from collections.abc import Sequence
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass, field
from socketserver import ThreadingMixIn
from uuid import uuid4

import certifi
import miniaudio

from app.domain import LibraryCacheRepo, Logger, Track, WaveformState

_WAVEFORM_BIN_COUNT = 100
_PROXY_CHUNK_SIZE = 64 * 1024


@dataclass(slots=True)
class _ByteRange:
    start: int
    end: int


@dataclass(slots=True)
class _ProxySession:
    session_id: str
    track: Track
    track_id: str
    track_duration_ms: int | None
    upstream_url: str
    lock: threading.Lock = field(default_factory=threading.Lock)
    byte_ranges: list[_ByteRange] = field(default_factory=list)
    contiguous_data: bytearray = field(default_factory=bytearray)
    pending_chunks: dict[int, bytes] = field(default_factory=dict)
    total_size_bytes: int | None = None
    content_type: str | None = None
    contiguous_bytes: int = 0
    waveform_bins: tuple[float, ...] = ()
    waveform_known_position_ms: int = 0
    waveform_mode: str = "plain"
    analysis_in_flight: bool = False
    closed: bool = False

    def local_url(self, *, port: int) -> str:
        return f"http://127.0.0.1:{port}/stream/{self.session_id}"


class _ThreadingHTTPServer(ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class StreamProxyService:
    def __init__(
        self,
        *,
        logger: Logger,
        library_cache_repo: LibraryCacheRepo | None = None,
    ) -> None:
        self._logger = logger
        self._library_cache_repo = library_cache_repo
        self._sessions_by_id: dict[str, _ProxySession] = {}
        self._sessions_by_track_id: dict[str, _ProxySession] = {}
        self._lock = threading.Lock()
        self._server: _ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._ssl_context = self._build_ssl_context()
        self._waveform_executor = ProcessPoolExecutor(max_workers=1)

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("stream proxy server is not running")
        return int(self._server.server_port)

    def create_session(self, *, track: Track, stream_ref: str) -> str:
        if not self._ensure_server_started():
            return stream_ref
        self.close_track_session(track.id)
        session = _ProxySession(
            session_id=str(uuid4()),
            track=track,
            track_id=track.id,
            track_duration_ms=track.duration_ms,
            upstream_url=stream_ref,
        )
        if track.waveform_bins and track.duration_ms:
            session.waveform_bins = track.waveform_bins
            session.waveform_known_position_ms = track.duration_ms
            session.waveform_mode = "cached"
        with self._lock:
            self._sessions_by_id[session.session_id] = session
            self._sessions_by_track_id[track.id] = session
        return session.local_url(port=self.port)

    def close_track_session(self, track_id: str) -> None:
        with self._lock:
            session = self._sessions_by_track_id.pop(track_id, None)
            if session is None:
                return
            self._sessions_by_id.pop(session.session_id, None)
        self._close_session(session)

    def get_waveform_state(self, track_id: str | None) -> WaveformState:
        if track_id is None:
            return WaveformState()
        with self._lock:
            session = self._sessions_by_track_id.get(track_id)
        if session is None:
            return WaveformState()
        with session.lock:
            buffered_position_ms = self._scaled_position_ms(
                contiguous_bytes=session.contiguous_bytes,
                total_size_bytes=session.total_size_bytes,
                duration_ms=session.track_duration_ms,
            )
            return WaveformState(
                buffered_position_ms=buffered_position_ms,
                waveform_bins=session.waveform_bins,
                waveform_known_position_ms=session.waveform_known_position_ms,
                waveform_mode=session.waveform_mode,
            )

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions_by_id.values())
            self._sessions_by_id.clear()
            self._sessions_by_track_id.clear()
        for session in sessions:
            self._close_session(session)
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        self._waveform_executor.shutdown(wait=False, cancel_futures=True)

    def _ensure_server_started(self) -> bool:
        if self._server is not None:
            return True
        try:
            self._server = _ThreadingHTTPServer(("127.0.0.1", 0), self._build_handler())
        except OSError as exc:
            self._logger.warning("Failed to start local stream proxy: %s", exc)
            self._server = None
            return False
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="yaymp-stream-proxy",
            daemon=True,
        )
        self._server_thread.start()
        return True

    def _build_ssl_context(self) -> ssl.SSLContext:
        if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
            return ssl.create_default_context()
        return ssl.create_default_context(cafile=certifi.where())

    def _build_handler(self):
        service = self

        class ProxyHandler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_HEAD(self) -> None:  # noqa: N802
                service._handle_proxy_request(self, send_body=False)

            def do_GET(self) -> None:  # noqa: N802
                service._handle_proxy_request(self, send_body=True)

            def log_message(self, format: str, *args) -> None:  # noqa: A003
                del format, args

        return ProxyHandler

    def _handle_proxy_request(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        *,
        send_body: bool,
    ) -> None:
        session = self._session_for_path(handler.path)
        if session is None:
            handler.send_error(404)
            return

        request = urllib.request.Request(session.upstream_url, method=handler.command)
        range_header = handler.headers.get("Range")
        if range_header:
            request.add_header("Range", range_header)

        try:
            with urllib.request.urlopen(
                request,
                timeout=20,
                context=self._ssl_context,
            ) as response:
                self._forward_headers(handler, response)
                if not send_body:
                    return
                start_offset = _range_start(range_header)
                bytes_written = 0
                while True:
                    chunk = response.read(_PROXY_CHUNK_SIZE)
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    self._record_download(
                        session,
                        start_offset=start_offset + bytes_written,
                        chunk=chunk,
                        content_type=response.headers.get("Content-Type"),
                        total_size_bytes=_response_total_size(response.headers, start_offset),
                    )
                    bytes_written += len(chunk)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            handler.send_response(exc.code)
            for header_name, header_value in exc.headers.items():
                if header_name.lower() == "transfer-encoding":
                    continue
                handler.send_header(header_name, header_value)
            handler.end_headers()
            if send_body and body:
                handler.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            self._logger.debug("Stream proxy client disconnected for %s", session.track_id)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Stream proxy failed for %s: %s", session.track_id, exc)
            if not handler.wfile.closed:
                handler.send_error(502)

    def _session_for_path(self, path: str) -> _ProxySession | None:
        _, _, suffix = path.partition("/stream/")
        if not suffix:
            return None
        session_id = suffix.split("?", 1)[0]
        with self._lock:
            return self._sessions_by_id.get(session_id)

    def _forward_headers(
        self,
        handler: http.server.BaseHTTPRequestHandler,
        response,
    ) -> None:
        handler.send_response(getattr(response, "status", 200))
        for header_name, header_value in response.headers.items():
            if header_name.lower() in {"connection", "transfer-encoding"}:
                continue
            handler.send_header(header_name, header_value)
        handler.end_headers()

    def _record_download(
        self,
        session: _ProxySession,
        *,
        start_offset: int,
        chunk: bytes,
        content_type: str | None,
        total_size_bytes: int | None,
    ) -> None:
        with session.lock:
            if session.closed:
                return
            if total_size_bytes is not None and total_size_bytes > 0:
                session.total_size_bytes = total_size_bytes
            if content_type:
                session.content_type = content_type
            session.byte_ranges = _merge_ranges(
                session.byte_ranges,
                _ByteRange(start=start_offset, end=start_offset + len(chunk)),
            )
            _append_contiguous_data(session, start_offset, chunk)
            session.contiguous_bytes = _contiguous_prefix_length(session.byte_ranges)
            if session.waveform_mode == "plain" and _looks_like_waveform_audio(session):
                session.waveform_mode = "loading"
            self._maybe_schedule_full_analysis(session)

    def _maybe_schedule_full_analysis(self, session: _ProxySession) -> None:
        if session.waveform_mode not in {"loading", "plain"}:
            return
        if session.track_duration_ms is None or session.track_duration_ms <= 0:
            return
        if session.analysis_in_flight:
            return
        if not _looks_like_waveform_audio(session):
            return
        contiguous_size = len(session.contiguous_data)
        if session.total_size_bytes is None or contiguous_size < session.total_size_bytes:
            return

        session.analysis_in_flight = True
        session.waveform_mode = "loading"
        self._logger.debug(
            ("Waveform analysis scheduled track=%s contiguous=%s total=%s duration_ms=%s"),
            session.track_id,
            contiguous_size,
            session.total_size_bytes,
            session.track_duration_ms,
        )
        future = self._waveform_executor.submit(
            _decode_complete_audio_bins,
            bytes(session.contiguous_data),
            session.track_duration_ms,
            _WAVEFORM_BIN_COUNT,
        )
        future.add_done_callback(
            lambda completed, session_id=session.session_id, size=contiguous_size: (
                self._apply_waveform_analysis_result(
                    session_id=session_id,
                    contiguous_size=size,
                    future=completed,
                )
            )
        )

    def _apply_waveform_analysis_result(
        self,
        *,
        session_id: str,
        contiguous_size: int,
        future: Future[tuple[tuple[float, ...], int]],
    ) -> None:
        with self._lock:
            session = self._sessions_by_id.get(session_id)
        if session is None:
            return
        try:
            with session.lock:
                if session.closed:
                    return
                duration_ms = session.track_duration_ms or 0
            bins, known_position_ms = future.result()
            with session.lock:
                if not session.closed:
                    session.waveform_bins = bins
                    session.waveform_known_position_ms = known_position_ms
                    session.waveform_mode = "ready"
                    if self._library_cache_repo is not None:
                        self._library_cache_repo.save_track_metadata(
                            Track(
                                id=session.track.id,
                                title=session.track.title,
                                artists=session.track.artists,
                                version=session.track.version,
                                artist_ids=session.track.artist_ids,
                                album_id=session.track.album_id,
                                album_title=session.track.album_title,
                                album_year=session.track.album_year,
                                duration_ms=session.track.duration_ms,
                                stream_ref=session.track.stream_ref,
                                stream_ref_cached_at=session.track.stream_ref_cached_at,
                                artwork_ref=session.track.artwork_ref,
                                accent_color=session.track.accent_color,
                                waveform_bins=tuple(bins),
                                available=session.track.available,
                                is_liked=session.track.is_liked,
                                is_disliked=session.track.is_disliked,
                            )
                        )
                    self._logger.debug(
                        (
                            "Waveform analysis complete track=%s contiguous=%s total=%s "
                            "known_ms=%s duration_ms=%s bins=%s"
                        ),
                        session.track_id,
                        contiguous_size,
                        session.total_size_bytes,
                        known_position_ms,
                        duration_ms,
                        len(bins),
                    )
        except Exception as exc:  # noqa: BLE001
            self._logger.debug(
                (
                    "Waveform analysis deferred track=%s contiguous=%s total=%s "
                    "duration_ms=%s error=%s"
                ),
                session.track_id,
                contiguous_size,
                session.total_size_bytes if session is not None else None,
                duration_ms if "duration_ms" in locals() else None,
                exc,
            )
        finally:
            with session.lock:
                session.analysis_in_flight = False

    def _close_session(self, session: _ProxySession) -> None:
        with session.lock:
            session.closed = True
            session.pending_chunks.clear()
            session.contiguous_data.clear()

    def _scaled_position_ms(
        self,
        *,
        contiguous_bytes: int,
        total_size_bytes: int | None,
        duration_ms: int | None,
    ) -> int | None:
        if total_size_bytes is None or total_size_bytes <= 0 or duration_ms is None:
            return None
        ratio = max(0.0, min(1.0, contiguous_bytes / total_size_bytes))
        return int(duration_ms * ratio)


def _merge_ranges(ranges: Sequence[_ByteRange], new_range: _ByteRange) -> list[_ByteRange]:
    merged = sorted((*ranges, new_range), key=lambda item: item.start)
    result: list[_ByteRange] = []
    for item in merged:
        if not result or item.start > result[-1].end:
            result.append(_ByteRange(start=item.start, end=item.end))
            continue
        result[-1].end = max(result[-1].end, item.end)
    return result


def _contiguous_prefix_length(ranges: Sequence[_ByteRange]) -> int:
    if not ranges or ranges[0].start > 0:
        return 0
    end = ranges[0].end
    for item in ranges[1:]:
        if item.start > end:
            break
        end = max(end, item.end)
    return end


def _range_start(range_header: str | None) -> int:
    if not range_header or "=" not in range_header:
        return 0
    _, _, value = range_header.partition("=")
    start_text, _, _ = value.partition("-")
    try:
        return max(0, int(start_text))
    except ValueError:
        return 0


def _response_total_size(headers, start_offset: int) -> int | None:
    content_range = headers.get("Content-Range")
    if content_range and "/" in content_range:
        _, _, total_text = content_range.partition("/")
        if total_text.isdigit():
            return int(total_text)
    content_length = headers.get("Content-Length")
    if content_length and content_length.isdigit():
        return start_offset + int(content_length)
    return None


def _looks_like_waveform_audio(session: _ProxySession) -> bool:
    if session.content_type and "mpeg" in session.content_type.lower():
        return True
    prefix = bytes(session.contiguous_data[:262_144])
    if prefix.startswith(b"fLaC"):
        return True
    if len(prefix) >= 12 and prefix[4:8] == b"ftyp" and b"dfLa" in prefix:
        return True
    if prefix[:3] == b"ID3":
        return True
    frame = prefix[:2]
    if len(frame) < 2:
        return False
    return frame[0] == 0xFF and (frame[1] & 0xE0) == 0xE0


def _append_contiguous_data(session: _ProxySession, start_offset: int, chunk: bytes) -> None:
    contiguous_end = len(session.contiguous_data)
    if start_offset <= contiguous_end:
        overlap = contiguous_end - start_offset
        if overlap < len(chunk):
            session.contiguous_data.extend(chunk[overlap:])
        _drain_pending_chunks(session)
        return
    existing = session.pending_chunks.get(start_offset)
    if existing is None or len(chunk) > len(existing):
        session.pending_chunks[start_offset] = chunk
    _drain_pending_chunks(session)


def _drain_pending_chunks(session: _ProxySession) -> None:
    while True:
        contiguous_end = len(session.contiguous_data)
        direct = session.pending_chunks.pop(contiguous_end, None)
        if direct is not None:
            session.contiguous_data.extend(direct)
            continue

        appended = False
        for start in sorted(session.pending_chunks):
            if start > contiguous_end:
                break
            chunk = session.pending_chunks.pop(start)
            overlap = contiguous_end - start
            if overlap < len(chunk):
                session.contiguous_data.extend(chunk[overlap:])
                appended = True
                break
        if not appended:
            break


def _decode_complete_audio_bins(
    data: bytes,
    duration_ms: int,
    bin_count: int,
) -> tuple[tuple[float, ...], int]:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        data = _extract_flac_from_mp4(data)
    decoded = miniaudio.decode(
        data,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=2,
        sample_rate=44_100,
    )
    samples = decoded.samples
    channels = max(1, decoded.nchannels)
    frames = len(samples) // channels
    if frames <= 0:
        raise ValueError("decoded audio has no frames")

    decoded_duration_ms = int(frames * 1000 / decoded.sample_rate)
    known_position_ms = duration_ms or decoded_duration_ms
    if known_position_ms <= 0:
        raise ValueError("decoded audio has no known duration")

    known_bin_count = bin_count
    frames_per_bin = max(1, frames // known_bin_count)
    bins = [0.0] * bin_count
    max_possible = float(32767)

    for bin_index in range(known_bin_count):
        frame_start = bin_index * frames_per_bin
        frame_end = (
            frames
            if bin_index == known_bin_count - 1
            else min(frames, frame_start + frames_per_bin)
        )
        if frame_start >= frame_end:
            continue
        amplitude_sum = 0.0
        sample_count = 0
        for frame in range(frame_start, frame_end):
            base_index = frame * channels
            for channel in range(channels):
                amplitude_sum += abs(samples[base_index + channel]) / max_possible
                sample_count += 1
        bins[bin_index] = amplitude_sum / sample_count if sample_count else 0.0

    peak = max(bins[:known_bin_count]) if known_bin_count else 0.0
    if peak > 0:
        bins = [min(1.0, value / peak) for value in bins]
    return tuple(bins), known_position_ms


def _extract_flac_from_mp4(data: bytes) -> bytes:
    moov = _find_mp4_box(data, 0, len(data), b"moov")
    flac_metadata: bytes | None = None
    sample_table: tuple[int, int] | None = None
    for box_type, payload_start, box_end in _iter_mp4_boxes(data, *moov):
        if box_type != b"trak":
            continue
        try:
            mdia = _find_mp4_box(data, payload_start, box_end, b"mdia")
            minf = _find_mp4_box(data, *mdia, b"minf")
            stbl = _find_mp4_box(data, *minf, b"stbl")
            stsd = _find_mp4_box(data, *stbl, b"stsd")
            flac_metadata = _flac_metadata_from_sample_description(data, *stsd)
        except (KeyError, ValueError, struct.error):
            continue
        sample_table = stbl
        break

    if flac_metadata is None or sample_table is None:
        raise ValueError("MP4 contains no FLAC audio track")

    sample_sizes = _mp4_sample_sizes(data, sample_table)
    chunk_offsets = _mp4_chunk_offsets(data, sample_table)
    samples_per_chunk = _mp4_samples_per_chunk(data, sample_table, len(chunk_offsets))
    if sum(samples_per_chunk) != len(sample_sizes):
        raise ValueError("MP4 FLAC sample table is inconsistent")

    native_flac = bytearray(b"fLaC")
    native_flac.extend(flac_metadata)
    sample_index = 0
    for chunk_offset, chunk_sample_count in zip(chunk_offsets, samples_per_chunk, strict=True):
        offset = chunk_offset
        for _ in range(chunk_sample_count):
            sample_size = sample_sizes[sample_index]
            sample_end = offset + sample_size
            if offset < 0 or sample_end > len(data):
                raise ValueError("MP4 FLAC sample points outside the file")
            native_flac.extend(data[offset:sample_end])
            offset = sample_end
            sample_index += 1
    return bytes(native_flac)


def _iter_mp4_boxes(data: bytes, start: int, end: int):
    offset = start
    while offset + 8 <= end:
        size, box_type = struct.unpack_from(">I4s", data, offset)
        header_size = 8
        if size == 1:
            if offset + 16 > end:
                raise ValueError("truncated extended MP4 box")
            size = struct.unpack_from(">Q", data, offset + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            raise ValueError("invalid MP4 box size")
        yield box_type, offset + header_size, offset + size
        offset += size
    if offset != end:
        raise ValueError("trailing bytes in MP4 box")


def _find_mp4_box(
    data: bytes,
    start: int,
    end: int,
    wanted_type: bytes,
) -> tuple[int, int]:
    for box_type, payload_start, box_end in _iter_mp4_boxes(data, start, end):
        if box_type == wanted_type:
            return payload_start, box_end
    raise KeyError(wanted_type)


def _flac_metadata_from_sample_description(data: bytes, start: int, end: int) -> bytes:
    if start + 8 > end:
        raise ValueError("truncated MP4 sample description")
    entry_count = struct.unpack_from(">I", data, start + 4)[0]
    entry_start = start + 8
    for index, (codec, payload_start, entry_end) in enumerate(
        _iter_mp4_boxes(data, entry_start, end)
    ):
        if index >= entry_count:
            break
        if codec != b"fLaC" or payload_start + 28 > entry_end:
            continue
        version = struct.unpack_from(">H", data, payload_start + 8)[0]
        extension_offset = {0: 28, 1: 44, 2: 64}.get(version)
        if extension_offset is None:
            raise ValueError("unsupported MP4 audio sample entry version")
        dfla = _find_mp4_box(data, payload_start + extension_offset, entry_end, b"dfLa")
        metadata_start = dfla[0] + 4
        if metadata_start + 4 > dfla[1]:
            raise ValueError("truncated MP4 FLAC metadata")
        metadata = data[metadata_start : dfla[1]]
        block_type = metadata[0] & 0x7F
        block_size = int.from_bytes(metadata[1:4], "big")
        if block_type != 0 or block_size != 34 or len(metadata) < 38:
            raise ValueError("MP4 FLAC metadata has no STREAMINFO block")
        return metadata
    raise KeyError(b"fLaC")


def _mp4_sample_sizes(data: bytes, sample_table: tuple[int, int]) -> list[int]:
    start, end = _find_mp4_box(data, *sample_table, b"stsz")
    if start + 12 > end:
        raise ValueError("truncated MP4 sample-size table")
    default_size, sample_count = struct.unpack_from(">II", data, start + 4)
    if default_size:
        return [default_size] * sample_count
    sizes_end = start + 12 + sample_count * 4
    if sizes_end > end:
        raise ValueError("truncated MP4 sample-size entries")
    return list(struct.unpack_from(f">{sample_count}I", data, start + 12))


def _mp4_chunk_offsets(data: bytes, sample_table: tuple[int, int]) -> list[int]:
    try:
        start, end = _find_mp4_box(data, *sample_table, b"stco")
        value_size = 4
        value_format = "I"
    except KeyError:
        start, end = _find_mp4_box(data, *sample_table, b"co64")
        value_size = 8
        value_format = "Q"
    if start + 8 > end:
        raise ValueError("truncated MP4 chunk-offset table")
    chunk_count = struct.unpack_from(">I", data, start + 4)[0]
    offsets_end = start + 8 + chunk_count * value_size
    if offsets_end > end:
        raise ValueError("truncated MP4 chunk-offset entries")
    return list(struct.unpack_from(f">{chunk_count}{value_format}", data, start + 8))


def _mp4_samples_per_chunk(
    data: bytes,
    sample_table: tuple[int, int],
    chunk_count: int,
) -> list[int]:
    start, end = _find_mp4_box(data, *sample_table, b"stsc")
    if start + 8 > end:
        raise ValueError("truncated MP4 sample-to-chunk table")
    entry_count = struct.unpack_from(">I", data, start + 4)[0]
    entries_end = start + 8 + entry_count * 12
    if entries_end > end or entry_count == 0:
        raise ValueError("invalid MP4 sample-to-chunk entries")
    entries = [
        struct.unpack_from(">III", data, start + 8 + index * 12) for index in range(entry_count)
    ]
    result: list[int] = []
    entry_index = 0
    for chunk_number in range(1, chunk_count + 1):
        while entry_index + 1 < len(entries) and entries[entry_index + 1][0] <= chunk_number:
            entry_index += 1
        first_chunk, sample_count, _description_index = entries[entry_index]
        if first_chunk > chunk_number or sample_count <= 0:
            raise ValueError("invalid MP4 sample-to-chunk mapping")
        result.append(sample_count)
    return result
