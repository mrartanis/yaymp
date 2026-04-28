from __future__ import annotations

import colorsys
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from app.domain import Track
from app.domain.errors import DomainError
from app.domain.playback import QueueItem


class MainWindowArtworkMixin:
    def _render_artwork(self, track: Track) -> None:
        if not track.artwork_ref:
            self._clear_artwork()
            self._set_accent_color("#526ee8")
            return

        artwork_url = self._container.services.artwork_cache.normalize_url(track.artwork_ref)
        if artwork_url is None:
            self._clear_artwork()
            self._set_accent_color("#526ee8")
            return

        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        cached_accent = self._container.services.artwork_cache.load_accent_color(cache_path)
        if cached_accent:
            self._set_accent_color(cached_accent)
        if cache_path.exists():
            self._set_artwork_pixmap(cache_path)
            return

        self._pending_artwork_track_id = track.id
        request = QNetworkRequest(QUrl(artwork_url))
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setAttribute(QNetworkRequest.Attribute.HttpPipeliningAllowedAttribute, False)
        reply = self._artwork_manager.get(request)
        reply.setProperty("track_id", track.id)
        reply.setProperty("cache_path", str(cache_path))

    def _handle_artwork_downloaded(self, reply: QNetworkReply) -> None:
        thumb_artwork_url = reply.property("thumb_artwork_url")
        if isinstance(thumb_artwork_url, str) and thumb_artwork_url:
            self._handle_thumb_downloaded(reply, thumb_artwork_url)
            return

        track_id = reply.property("track_id")
        cache_path = Path(str(reply.property("cache_path")))
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return

        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data:
            return
        try:
            self._container.services.artwork_cache.save_bytes(cache_path, data)
        except DomainError as exc:
            self._container.logger.warning("Artwork cache write failed: %s", exc)
            return
        if track_id == self._pending_artwork_track_id:
            self._set_artwork_pixmap(cache_path)

    def _handle_thumb_downloaded(self, reply: QNetworkReply, artwork_url: str) -> None:
        cache_path = Path(str(reply.property("cache_path")))
        labels = self._pending_thumb_labels.pop(artwork_url, [])
        self._active_thumb_downloads = max(0, self._active_thumb_downloads - 1)
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            self._start_next_thumb_downloads()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data:
            self._start_next_thumb_downloads()
            return
        try:
            self._container.services.artwork_cache.save_bytes(cache_path, data)
        except DomainError as exc:
            self._container.logger.warning("Artwork thumb cache write failed: %s", exc)
            self._start_next_thumb_downloads()
            return
        pixmap = QPixmap(str(cache_path))
        if pixmap.isNull():
            self._start_next_thumb_downloads()
            return
        for label in labels:
            if shiboken6.isValid(label):
                self._set_thumb_pixmap(label, pixmap)
        self._start_next_thumb_downloads()

    def _set_artwork_pixmap(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._clear_artwork()
            return
        accent = self._container.services.artwork_cache.load_accent_color(path)
        if accent is None:
            accent = self._extract_accent_color(pixmap)
            try:
                self._container.services.artwork_cache.save_accent_color(path, accent)
            except DomainError as exc:
                self._container.logger.warning("Artwork accent cache write failed: %s", exc)
        self._set_accent_color(accent)
        self._artwork_label.setPixmap(
            pixmap.scaled(
                self._artwork_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _clear_artwork(self) -> None:
        self._pending_artwork_track_id = None
        self._artwork_label.clear()
        self._artwork_label.setText("No cover")

    def _extract_accent_color(self, pixmap: QPixmap) -> str:
        image = pixmap.toImage().scaled(
            24,
            24,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        samples: list[tuple[float, float, float]] = []
        for y in range(image.height()):
            for x in range(image.width()):
                color = QColor(image.pixel(x, y))
                if color.alpha() < 180:
                    continue
                r, g, b = color.redF(), color.greenF(), color.blueF()
                h, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
                if saturation < 0.12 or lightness < 0.12 or lightness > 0.88:
                    continue
                samples.append((h, lightness, saturation))
        if not samples:
            return "#526ee8"
        hue, lightness, saturation = max(samples, key=lambda item: item[2] * 1.4 + item[1])
        saturation = min(0.65, max(0.25, saturation))
        lightness = min(0.70, max(0.35, lightness))
        r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
        candidate = QColor.fromRgbF(r, g, b).name()
        return candidate if self._has_usable_accent_contrast(candidate) else "#526ee8"

    def _has_usable_accent_contrast(self, color: str) -> bool:
        qcolor = QColor(color)
        luminance = (
            0.2126 * qcolor.redF()
            + 0.7152 * qcolor.greenF()
            + 0.0722 * qcolor.blueF()
        )
        background = 0.055
        contrast = (max(luminance, background) + 0.05) / (min(luminance, background) + 0.05)
        return contrast >= 2.2

    def _set_accent_color(self, color: str) -> None:
        if color == self._accent_color:
            return
        self._accent_color = color
        self._apply_theme()

    def _accent_text_color(self) -> str:
        accent = QColor(self._accent_color)
        luminance = (
            0.2126 * accent.redF()
            + 0.7152 * accent.greenF()
            + 0.0722 * accent.blueF()
        )
        return "#101116" if luminance > 0.58 else "#ffffff"

    def _format_year(self, year: int | None) -> str:
        return f" ({year})" if year else ""

    def _format_audio_info(self, codec: str | None, bitrate: int | None) -> str:
        if not codec or bitrate is None:
            return ""
        codec_label = self._compact_codec(codec)
        kbps = bitrate if bitrate < 1000 else round(bitrate / 1000)
        return f"{codec_label}:{max(1, kbps)}"

    def _compact_codec(self, codec: str | None) -> str:
        if not codec:
            return "?"
        normalized = codec.lower()
        for label in ("mp3", "aac", "flac", "opus", "vorbis", "alac"):
            if label in normalized:
                return label
        if "mpeg" in normalized and "layer 3" in normalized:
            return "mp3"
        return normalized.split(" ", 1)[0].split(",", 1)[0]

    def _queue_duration_ms(self, queue: tuple[QueueItem, ...]) -> int:
        return sum(item.track.duration_ms or 0 for item in queue)
