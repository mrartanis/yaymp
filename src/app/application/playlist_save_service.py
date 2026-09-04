from __future__ import annotations

from app.application.library_service import LibraryService
from app.domain import (
    Logger,
    MusicService,
    NoSaveableTracksError,
    Playlist,
    PlaylistNameConflictError,
    PlaylistSaveMode,
    PlaylistSaveRequest,
    PlaylistSaveResult,
    PlaylistSaveValidationError,
    PlaylistTargetNotFoundError,
    Track,
)
from app.domain.errors import DomainError


class PlaylistSaveService:
    def __init__(
        self,
        *,
        music_service: MusicService,
        library_service: LibraryService,
        logger: Logger,
    ) -> None:
        self._music_service = music_service
        self._library_service = library_service
        self._logger = logger

    def load_destinations(self) -> tuple[Playlist, ...]:
        return self._library_service.load_user_playlists(force_refresh=True)

    def save(self, request: PlaylistSaveRequest) -> PlaylistSaveResult:
        fresh_playlists = self.load_destinations()
        title = (request.title or "").strip()
        target = request.target

        if request.mode is PlaylistSaveMode.CREATE:
            if not title:
                raise PlaylistSaveValidationError("Playlist title is required")
            if self._title_exists(title, fresh_playlists):
                raise PlaylistNameConflictError(title)
        else:
            target = self._fresh_target(target, fresh_playlists)

        prepared_tracks, skipped_count = self._prepare_tracks(request.tracks)
        if not prepared_tracks:
            raise NoSaveableTracksError("No tracks in the queue can be saved")

        if request.mode is PlaylistSaveMode.CREATE:
            playlist = self._music_service.create_playlist(
                title,
                visibility=request.visibility.value,
            )
            try:
                playlist = self._music_service.append_playlist_tracks(
                    playlist.id,
                    prepared_tracks,
                    owner_id=playlist.owner_id,
                )
            except DomainError:
                try:
                    self._music_service.delete_playlist(
                        playlist.id,
                        owner_id=playlist.owner_id,
                    )
                except DomainError as cleanup_error:
                    self._logger.error(
                        "Failed to remove incomplete playlist %s: %s",
                        playlist.id,
                        cleanup_error,
                    )
                raise
        elif request.mode is PlaylistSaveMode.APPEND:
            assert target is not None
            playlist = self._music_service.append_playlist_tracks(
                target.id,
                prepared_tracks,
                owner_id=target.owner_id,
            )
        else:
            assert target is not None
            playlist = self._music_service.replace_playlist_tracks(
                target.id,
                prepared_tracks,
                owner_id=target.owner_id,
            )

        updated_playlists = self._refresh_after_save(playlist, fresh_playlists)
        return PlaylistSaveResult(
            playlist=playlist,
            saved_count=len(prepared_tracks),
            skipped_count=skipped_count,
            user_playlists=updated_playlists,
        )

    def _prepare_tracks(self, tracks: tuple[Track, ...]) -> tuple[tuple[Track, ...], int]:
        missing_ids = tuple(
            dict.fromkeys(track.id for track in tracks if track.available and not track.album_id)
        )
        resolved_by_id: dict[str, Track] = {}
        if missing_ids:
            resolved_by_id = {
                track.id: track for track in self._music_service.get_tracks(missing_ids)
            }

        prepared: list[Track] = []
        skipped = 0
        for track in tracks:
            candidate = track if track.album_id else resolved_by_id.get(track.id)
            if (
                not track.available
                or candidate is None
                or not candidate.available
                or not candidate.album_id
            ):
                skipped += 1
                continue
            prepared.append(candidate)
        return tuple(prepared), skipped

    def _refresh_after_save(
        self,
        playlist: Playlist,
        previous: tuple[Playlist, ...],
    ) -> tuple[Playlist, ...]:
        try:
            return self.load_destinations()
        except DomainError as exc:
            self._logger.warning("Playlist saved but server list refresh failed: %s", exc)
        updated = tuple(item for item in previous if item.id != playlist.id) + (playlist,)
        self._library_service.update_user_playlist_snapshot(updated)
        return updated

    @staticmethod
    def _title_exists(title: str, playlists: tuple[Playlist, ...]) -> bool:
        normalized = title.strip().casefold()
        return any(playlist.title.strip().casefold() == normalized for playlist in playlists)

    @staticmethod
    def _fresh_target(
        target: Playlist | None,
        playlists: tuple[Playlist, ...],
    ) -> Playlist:
        if target is None:
            raise PlaylistTargetNotFoundError("Playlist target is missing")
        for playlist in playlists:
            if playlist.id == target.id and playlist.owner_id == target.owner_id:
                return playlist
        raise PlaylistTargetNotFoundError("Playlist no longer exists")
