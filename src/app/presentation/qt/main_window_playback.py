from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt

from app.application.track_metadata import track_credits_are_fresh
from app.domain import Album, Artist, PlaybackStatus, Track
from app.presentation.qt.preference_markers import preference_marker_icon_name
from app.presentation.qt.track_display import display_track_title


class MainWindowPlaybackMixin:
    """Adapt playback snapshots to the player controls and track metadata."""

    def _render_snapshot(self, snapshot) -> None:
        current_item = snapshot.current_item
        queue = snapshot.queue
        state = snapshot.state

        current_track = (
            self._track_with_preference_override(current_item.track)
            if current_item is not None
            else None
        )
        metadata_key = (
            current_track,
            self._t("label.no_track_selected"),
            self._t("label.unknown_artist"),
        )
        if metadata_key != getattr(self, "_rendered_track_metadata_key", None):
            self._rendered_track_metadata_key = metadata_key
            if current_item is not None:
                self._current_track = current_track
                artists = ", ".join(current_track.artists)
                track_title = display_track_title(current_track)
                album_text = (
                    f"{current_track.album_title or 'Single'}"
                    f"{self._format_year(current_track.album_year)}"
                )
                self._track_title_label.setText(current_track.title)
                self._track_title_label.setToolTip(track_title)
                version_parts = [
                    part
                    for part in (current_track.version, "AI" if current_track.ai_usage else None)
                    if part
                ]
                version_text = " · ".join(version_parts)
                self._track_version_label.setText(version_text)
                self._track_version_label.setToolTip(
                    self._ai_usage_text(current_track) or current_track.version or ""
                )
                self._track_version_label.setVisible(bool(version_text))
                self._track_meta_label.setText(artists or self._t("label.unknown_artist"))
                self._track_meta_label.setToolTip(artists)
                self._track_album_label.setText(album_text)
                self._track_album_label.setToolTip(album_text)
                self._update_track_navigation_affordances(current_track)
                self._fit_track_text_labels()
                self._render_current_track_preference_buttons(current_track)
                self._defer_artwork_render(current_track)
            else:
                self._current_track = None
                self._track_title_label.setText(self._t("label.no_track_selected"))
                self._track_version_label.setText("")
                self._track_version_label.setVisible(False)
                self._track_meta_label.setText(self._t("track.choose_music"))
                self._track_album_label.setText("")
                self._update_track_navigation_affordances(None)
                self._fit_track_text_labels()
                self._render_current_track_preference_buttons(None)
                self._pending_artwork_track = None
                self._artwork_render_timer.stop()
                self._clear_artwork()
                self._set_accent_color("#526ee8")

        if current_track is None:
            self._credits_playback_track_id = None
        elif self._credits_playback_track_id != current_track.id:
            self._credits_playback_track_id = current_track.id
            if (
                self._container.services.music_service.get_auth_session() is not None
                and not track_credits_are_fresh(
                    current_track,
                    language=self._container.services.music_service.get_language(),
                )
            ):
                self._music_metadata_controller.request_track_credits(
                    current_track,
                    context=f"playback:{current_track.id}",
                )

        self._render_play_pause_button(state.status)
        self._render_my_wave_button_state(current_item, state.status, state.position_ms)
        self._seek_slider.blockSignals(True)
        self._seek_slider.setMaximum(state.duration_ms or 300_000)
        self._seek_slider.setValue(state.position_ms)
        self._seek_slider.set_waveform_state(
            buffered_position_ms=state.waveform.buffered_position_ms,
            waveform_bins=state.waveform.waveform_bins,
            waveform_known_position_ms=state.waveform.waveform_known_position_ms,
            waveform_mode=state.waveform.waveform_mode,
        )
        self._seek_slider.blockSignals(False)
        self._seek_label.setText(
            f"{self._format_ms(state.position_ms)}/{self._format_ms(state.duration_ms)}"
        )
        self._volume_slider.blockSignals(True)
        if not self._volume_slider_drag_active:
            self._volume_slider.setValue(state.volume)
        self._volume_slider.blockSignals(False)
        self._volume_label.setText(f"{self._volume_slider.value()}%")
        self._queue_shuffle_button.blockSignals(True)
        self._queue_shuffle_button.setChecked(state.shuffle_enabled)
        self._queue_shuffle_button.blockSignals(False)
        self._queue_status_label.setText(
            self._t(
                "status.queue_summary",
                count=len(queue),
                duration=self._format_ms(self._queue_duration_ms(queue)),
            )
        )
        self._audio_info_label.setText(
            self._format_audio_info(state.audio_codec, state.audio_bitrate)
        )
        self._render_queue(snapshot)
        self._render_auth_state()
        self._update_save_queue_button_state()
        self._defer_system_media_update(snapshot)

    def _ai_usage_text(self, track: Track) -> str:
        if track.ai_usage is None:
            return ""
        return self._t(f"track_info.ai_use.{track.ai_usage.value}")

    def _defer_artwork_render(self, track: Track) -> None:
        self._pending_artwork_track = track
        self._artwork_render_timer.start()

    def _flush_deferred_artwork(self) -> None:
        track = self._pending_artwork_track
        if track is None:
            return
        self._pending_artwork_track = None
        if self._current_track is None or self._current_track.id != track.id:
            return
        self._render_artwork(track)

    def _defer_system_media_update(self, snapshot) -> None:
        self._pending_system_media_snapshot = snapshot
        self._system_media_timer.start()

    def _flush_system_media_update(self) -> None:
        snapshot = self._pending_system_media_snapshot
        if snapshot is None:
            return
        self._pending_system_media_snapshot = None
        self._system_media.update_snapshot(snapshot)

    def _track_with_preference_override(self, track: Track) -> Track:
        liked = self._track_like_overrides.get(track.id)
        disliked = self._track_dislike_overrides.get(track.id)
        effective_liked = track.is_liked if liked is None else liked
        effective_disliked = track.is_disliked if disliked is None else disliked
        if effective_disliked:
            effective_liked = False
        if effective_liked == track.is_liked and effective_disliked == track.is_disliked:
            return track
        return replace(track, is_liked=effective_liked, is_disliked=effective_disliked)

    def _update_track_navigation_affordances(self, track: Track | None) -> None:
        can_open_artist = bool(track and track.artist_ids and track.artists)
        can_open_album = bool(track and track.album_id)
        self._track_meta_label.setCursor(
            Qt.CursorShape.PointingHandCursor if can_open_artist else Qt.CursorShape.ArrowCursor
        )
        self._track_album_label.setCursor(
            Qt.CursorShape.PointingHandCursor if can_open_album else Qt.CursorShape.ArrowCursor
        )

    def _open_current_track_primary_artist(self) -> bool:
        track = self._current_track
        if track is None:
            return False
        if not track.artist_ids or not track.artists:
            return False
        artist = Artist(id=track.artist_ids[0], name=track.artists[0])
        self._library_controller.open_artist(artist)
        return True

    def _open_current_track_album(self) -> bool:
        track = self._current_track
        if track is None or not track.album_id:
            return False
        album = Album(
            id=track.album_id,
            title=track.album_title or self._t("label.album"),
            artists=track.artists,
            artist_ids=track.artist_ids,
            year=track.album_year,
        )
        self._library_controller.open_album(album)
        return True

    def _render_current_track_preference_buttons(self, track: Track | None) -> None:
        self._render_current_track_like_button(bool(track and track.is_liked))
        self._render_current_track_dislike_button(bool(track and track.is_disliked))

    def _render_current_track_like_button(self, is_liked: bool) -> None:
        self._set_button_icon(
            self._like_track_button,
            preference_marker_icon_name("liked", theme_mode=self._resolved_theme_mode())
            if is_liked
            else "heart_outline.svg",
            color=(self._accent_color if is_liked else self._theme_icon_color()),
        )
        tooltip = self._t("track.tooltip.unlike") if is_liked else self._t("track.tooltip.like")
        self._like_track_button.setToolTip(tooltip)
        self._like_track_button.setAccessibleName(tooltip)

    def _render_current_track_dislike_button(self, is_disliked: bool) -> None:
        self._set_button_icon(
            self._dislike_track_button,
            "heart_slash.svg" if is_disliked else "heart_slash_outline.svg",
            color=(self._theme_muted_icon_color() if is_disliked else self._theme_icon_color()),
        )
        tooltip = (
            self._t("track.tooltip.undislike") if is_disliked else self._t("track.tooltip.dislike")
        )
        self._dislike_track_button.setToolTip(tooltip)
        self._dislike_track_button.setAccessibleName(tooltip)

    def _render_play_pause_button(self, status: PlaybackStatus) -> None:
        self._play_pause_button.setProperty("playback_status", status.value)
        if status is PlaybackStatus.PLAYING:
            self._set_button_icon(
                self._play_pause_button,
                "pause.svg",
                color=self._accent_text_color(),
            )
            self._play_pause_button.setToolTip(self._t("action.pause"))
            self._play_pause_button.setAccessibleName(self._t("action.pause"))
            return
        self._set_button_icon(
            self._play_pause_button,
            "play.svg",
            color=self._accent_text_color(),
        )
        self._play_pause_button.setToolTip(self._t("action.play"))
        self._play_pause_button.setAccessibleName(self._t("action.play"))

    def _render_my_wave_button_state(
        self,
        current_item,
        status: PlaybackStatus,
        position_ms: int,
    ) -> None:
        is_my_wave = (
            current_item is not None
            and current_item.source_type == "station"
            and current_item.source_id == self._MY_WAVE_STATION_ID
        )
        self._my_wave_active = is_my_wave and status is PlaybackStatus.PLAYING
        if is_my_wave:
            self._my_wave_pending = False
        if self._my_wave_top_button.sync_playback(
            enabled=self._my_wave_active,
            track_id=current_item.track.id if is_my_wave else None,
            position_ms=position_ms,
            accent=self._accent_color,
        ):
            self._my_wave_history_dirty = True
        self._maybe_persist_my_wave_history(
            status=status,
            position_ms=position_ms,
        )

    def _my_wave_trailing_color(self) -> str:
        if self._resolved_theme_mode() == "light":
            return "#d8e2f8"
        return "#2c355f"

    def _render_error(self, message: str) -> None:
        self._my_wave_pending = False
        self._my_wave_active = False
        self._status_label.setText(self._t("status.playback_error", message=message))
