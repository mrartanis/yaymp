from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest

from app.domain import Track
from app.domain.errors import DomainError
from app.domain.playback import QueueItem
from app.presentation.qt.artwork_processing import (
    PreparedArtwork,
    accent_sampling_step,
    extract_accent_color,
    has_usable_accent_contrast,
    prepare_artwork,
)


class MainWindowArtworkMixin:
    _THUMB_SOURCE_PIXMAP_CACHE_LIMIT = 576
    _THUMB_SCALED_PIXMAP_CACHE_LIMIT = 1152
    _THUMB_SOURCE_MAX_EDGE = 64
    _BROWSER_CARD_SOURCE_MAX_EDGE = 256

    def _thumb_pixmap_for_artwork_ref(
        self,
        artwork_ref: str | None,
        size: int,
    ) -> QPixmap | None:
        if not artwork_ref:
            return None
        artwork_url = self._container.services.artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            return None
        return self._thumb_pixmap_for_url(artwork_url, size=size)

    def _request_thumb_for_queue_row(
        self,
        artwork_ref: str | None,
        size: int,
        row: int,
    ) -> None:
        if not artwork_ref:
            return
        artwork_url = self._container.services.artwork_cache.normalize_url(artwork_ref)
        if artwork_url is None:
            return
        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        if cache_path.exists():
            return
        self._queue_thumb_download(
            artwork_url,
            cache_path,
            on_ready=lambda: self._queue_delegate.update_row(row),
        )

    def _thumb_pixmap_for_url(
        self,
        artwork_url: str,
        *,
        size: int,
        source_max_edge: int | None = None,
    ) -> QPixmap | None:
        normalized_max_edge = source_max_edge or self._THUMB_SOURCE_MAX_EDGE
        if normalized_max_edge == self._THUMB_SOURCE_MAX_EDGE:
            cache_key: object = (artwork_url, size)
        else:
            cache_key = (artwork_url, size, normalized_max_edge)
        cached_scaled = self._thumb_scaled_pixmap_cache.get(cache_key)
        if cached_scaled is not None:
            self._thumb_scaled_pixmap_cache.move_to_end(cache_key)
            return cached_scaled
        source_pixmap = self._thumb_source_pixmap(
            artwork_url,
            max_edge=normalized_max_edge,
        )
        if source_pixmap is None:
            return None
        scaled = source_pixmap.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._lru_store_pixmap(
            self._thumb_scaled_pixmap_cache,
            cache_key,
            scaled,
            limit=self._THUMB_SCALED_PIXMAP_CACHE_LIMIT,
        )
        return scaled

    def _thumb_source_pixmap(
        self,
        artwork_url: str,
        *,
        max_edge: int | None = None,
    ) -> QPixmap | None:
        normalized_max_edge = max_edge or self._THUMB_SOURCE_MAX_EDGE
        if normalized_max_edge == self._THUMB_SOURCE_MAX_EDGE:
            cache_key: object = artwork_url
        else:
            cache_key = (artwork_url, normalized_max_edge)
        cached_source = self._thumb_source_pixmap_cache.get(cache_key)
        if cached_source is not None:
            self._thumb_source_pixmap_cache.move_to_end(cache_key)
            return cached_source
        cache_path = self._container.services.artwork_cache.cache_path_for_url(artwork_url)
        if not cache_path.exists():
            return None
        pixmap = QPixmap(str(cache_path))
        if pixmap.isNull():
            return None
        normalized = self._normalized_thumb_source_pixmap(
            pixmap,
            max_edge=normalized_max_edge,
        )
        self._lru_store_pixmap(
            self._thumb_source_pixmap_cache,
            cache_key,
            normalized,
            limit=self._THUMB_SOURCE_PIXMAP_CACHE_LIMIT,
        )
        return normalized

    def _store_thumb_source_pixmap(self, artwork_url: str, pixmap: QPixmap) -> None:
        stale_source_keys = [
            key for key in self._thumb_source_pixmap_cache
            if key[0] == artwork_url
        ]
        for key in stale_source_keys:
            del self._thumb_source_pixmap_cache[key]
        self._lru_store_pixmap(
            self._thumb_source_pixmap_cache,
            artwork_url,
            self._normalized_thumb_source_pixmap(
                pixmap,
                max_edge=self._THUMB_SOURCE_MAX_EDGE,
            ),
            limit=self._THUMB_SOURCE_PIXMAP_CACHE_LIMIT,
        )
        stale_keys = [
            key for key in self._thumb_scaled_pixmap_cache
            if key[0] == artwork_url
        ]
        for key in stale_keys:
            del self._thumb_scaled_pixmap_cache[key]

    def _normalized_thumb_source_pixmap(self, pixmap: QPixmap, *, max_edge: int) -> QPixmap:
        pixmap_max_edge = max(pixmap.width(), pixmap.height())
        if pixmap_max_edge <= max_edge:
            return pixmap
        if pixmap.width() >= pixmap.height():
            return pixmap.scaledToWidth(
                max_edge,
                Qt.TransformationMode.SmoothTransformation,
            )
        return pixmap.scaledToHeight(
            max_edge,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _lru_store_pixmap(
        self,
        cache: OrderedDict,
        key: object,
        pixmap: QPixmap,
        *,
        limit: int,
    ) -> None:
        cache[key] = pixmap
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    def _render_artwork(self, track: Track) -> None:
        self._cancel_artwork_preparation()
        self._pending_artwork_track_id = track.id
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
        if cache_path.exists():
            self._set_artwork_pixmap(cache_path, preferred_accent=track.accent_color)
            return

        self._pending_artwork_track_id = track.id
        request = QNetworkRequest(QUrl(artwork_url))
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        request.setAttribute(QNetworkRequest.Attribute.HttpPipeliningAllowedAttribute, False)
        reply = self._artwork_manager.get(request)
        reply.setProperty("track_id", track.id)
        reply.setProperty("cache_path", str(cache_path))
        reply.setProperty("preferred_accent", track.accent_color)

    def _handle_artwork_downloaded(self, reply: QNetworkReply) -> None:
        thumb_artwork_url = reply.property("thumb_artwork_url")
        if isinstance(thumb_artwork_url, str) and thumb_artwork_url:
            self._handle_thumb_downloaded(reply, thumb_artwork_url)
            return

        track_id = reply.property("track_id")
        cache_path = Path(str(reply.property("cache_path")))
        preferred_accent = reply.property("preferred_accent")
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
            self._set_artwork_pixmap(
                cache_path,
                preferred_accent=preferred_accent if isinstance(preferred_accent, str) else None,
            )

    def _handle_thumb_downloaded(self, reply: QNetworkReply, artwork_url: str) -> None:
        cache_path = Path(str(reply.property("cache_path")))
        labels = self._pending_thumb_labels.pop(artwork_url, [])
        callbacks = self._pending_thumb_callbacks.pop(artwork_url, [])
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
        self._store_thumb_source_pixmap(artwork_url, pixmap)
        for label in labels:
            if shiboken6.isValid(label):
                self._set_thumb_pixmap(label, pixmap)
        for callback in callbacks:
            callback()
        self._start_next_thumb_downloads()

    def _set_artwork_pixmap(self, path: Path, *, preferred_accent: str | None = None) -> None:
        cache = self._container.services.artwork_cache
        logger = self._container.logger

        def prepare() -> PreparedArtwork:
            return prepare_artwork(
                path, cache=cache, logger=logger, preferred_accent=preferred_accent
            )

        runner = getattr(self, "_library_task_runner", None)
        if runner is None:
            self._display_prepared_artwork(prepare())
            return
        self._cancel_artwork_preparation()
        self._artwork_prepare_task_id = runner.submit(prepare)

    def _cancel_artwork_preparation(self) -> None:
        task_id = getattr(self, "_artwork_prepare_task_id", None)
        if task_id is not None:
            self._library_task_runner.cancel(task_id)
            self._artwork_prepare_task_id = None

    def _handle_artwork_prepared(self, task_id: int, result: object) -> None:
        if task_id != getattr(self, "_artwork_prepare_task_id", None):
            return
        self._artwork_prepare_task_id = None
        if isinstance(result, PreparedArtwork):
            self._display_prepared_artwork(result)

    def _handle_artwork_preparation_failed(self, task_id: int, error: object) -> None:
        if task_id == getattr(self, "_artwork_prepare_task_id", None):
            self._artwork_prepare_task_id = None
            self._container.logger.warning("Artwork preparation failed: %s", error)

    def _display_prepared_artwork(self, artwork: PreparedArtwork) -> None:
        if artwork.image.isNull():
            self._clear_artwork()
            return
        self._set_accent_color(artwork.accent)
        self._artwork_label.setPixmap(
            QPixmap.fromImage(artwork.image).scaled(
                self._artwork_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _clear_artwork(self) -> None:
        self._cancel_artwork_preparation()
        self._pending_artwork_track_id = None
        self._artwork_label.clear()
        self._artwork_label.setText("No cover")

    def _extract_accent_color(self, pixmap: QPixmap) -> str | None:
        return extract_accent_color(pixmap.toImage())

    def _accent_sampling_step(self, width: int, height: int) -> int:
        return accent_sampling_step(width, height)

    def _has_usable_accent_contrast(self, color: str) -> bool:
        return has_usable_accent_contrast(color)

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
