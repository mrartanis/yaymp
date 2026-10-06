from __future__ import annotations

import http.server
import threading
from dataclasses import dataclass, field


class _ThreadingHTTPServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@dataclass
class HttpOrigin:
    body: bytes
    content_type: str = "application/octet-stream"
    status: int = 200
    requests: list[tuple[str, str | None]] = field(default_factory=list)
    _server: _ThreadingHTTPServer | None = field(init=False, default=None)
    _thread: threading.Thread | None = field(init=False, default=None)

    def __enter__(self) -> HttpOrigin:
        origin = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_HEAD(self) -> None:  # noqa: N802
                self._respond(send_body=False)

            def do_GET(self) -> None:  # noqa: N802
                self._respond(send_body=True)

            def _respond(self, *, send_body: bool) -> None:
                range_header = self.headers.get("Range")
                origin.requests.append((self.command, range_header))
                if origin.status >= 400:
                    payload = f"origin error {origin.status}".encode()
                    self.send_response(origin.status)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if send_body:
                        self.wfile.write(payload)
                    return

                payload = origin.body
                status = origin.status
                content_range = None
                if range_header and range_header.startswith("bytes="):
                    start_text, _, end_text = range_header.removeprefix("bytes=").partition("-")
                    start = int(start_text)
                    end = int(end_text) if end_text else len(payload) - 1
                    end = min(end, len(payload) - 1)
                    payload = payload[start : end + 1]
                    status = 206
                    content_range = f"bytes {start}-{end}/{len(origin.body)}"

                self.send_response(status)
                self.send_header("Content-Type", origin.content_type)
                self.send_header("Content-Length", str(len(payload)))
                if content_range:
                    self.send_header("Content-Range", content_range)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Connection", "close")
                self.end_headers()
                if send_body:
                    self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                del format, args

        self._server = _ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("HTTP origin is not running")
        return f"http://127.0.0.1:{self._server.server_port}/audio"

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()
