from __future__ import annotations

from dataclasses import replace

from app.application.track_metadata import (
    merge_cached_artist_preference_states,
    merge_cached_track_preference_states,
)
from app.domain import (
    Album,
    Artist,
    DislikedTrackIds,
    LibraryCacheRepo,
    LikedTrackSnapshot,
    Logger,
    MusicService,
    Playlist,
    Station,
    Track,
)
from app.domain.errors import StorageError


class LibraryService:
    _BULK_LIKED_TRACK_LIMIT = 100_000
    _BULK_ARTIST_TRACK_LIMIT = 1_000

    def __init__(
        self,
        *,
        music_service: MusicService,
        library_cache_repo: LibraryCacheRepo,
        logger: Logger,
    ) -> None:
        self._music_service = music_service
        self._library_cache_repo = library_cache_repo
        self._logger = logger

    def load_liked_tracks(self, *, limit: int = 100) -> tuple[Track, ...]:
        user_id = self._current_user_id()
        cached_snapshot = self._safe_load_liked_track_snapshot(user_id)
        cached_tracks = cached_snapshot.tracks[:limit] if cached_snapshot is not None else ()
        current_revision = cached_snapshot.revision if cached_snapshot is not None else 0
        cached_liked_ids = self._safe_load_liked_track_ids(user_id)
        total_cached_tracks = len(cached_snapshot.tracks) if cached_snapshot is not None else 0
        total_known_tracks = (
            len(cached_liked_ids.track_ids) if cached_liked_ids is not None else total_cached_tracks
        )
        if user_id is None:
            tracks = tuple(self._music_service.get_liked_tracks(limit=limit))
            self._cache_tracks(tracks)
            self._logger.info("Loaded %s liked tracks", len(tracks))
            return tracks

        liked_tracks = self._music_service.get_liked_track_ids(
            if_modified_since_revision=current_revision
        )
        if (
            liked_tracks is None
            and cached_tracks
            and total_cached_tracks >= min(limit, total_known_tracks)
        ):
            self._logger.info(
                "Loaded %s liked tracks from cache at revision %s",
                len(cached_tracks),
                current_revision,
            )
            return cached_tracks

        tracks = tuple(self._music_service.get_liked_tracks(limit=limit))
        self._cache_tracks(tracks)
        snapshot_revision = (
            liked_tracks.revision if liked_tracks is not None else current_revision
        )
        self._safe_save_liked_track_snapshot(
            LikedTrackSnapshot(
                user_id=user_id,
                revision=snapshot_revision,
                tracks=tracks,
            )
        )
        if liked_tracks is not None:
            self._safe_save_liked_track_ids(liked_tracks)
        self._logger.info("Loaded %s liked tracks", len(tracks))
        return tracks

    def load_all_liked_tracks(self) -> tuple[Track, ...]:
        user_id = self._current_user_id()
        cached_snapshot = self._safe_load_liked_track_snapshot(user_id)
        cached_liked_ids = self._safe_load_liked_track_ids(user_id)
        current_revision = cached_snapshot.revision if cached_snapshot is not None else 0

        if user_id is None:
            tracks = tuple(self._music_service.get_liked_tracks(limit=self._BULK_LIKED_TRACK_LIMIT))
            self._cache_tracks(tracks)
            self._logger.info("Loaded %s liked tracks for bulk playback", len(tracks))
            return tracks

        liked_tracks = self._music_service.get_liked_track_ids(
            if_modified_since_revision=current_revision
        )
        if (
            liked_tracks is None
            and cached_snapshot is not None
            and cached_liked_ids is not None
            and len(cached_snapshot.tracks) >= len(cached_liked_ids.track_ids)
        ):
            self._logger.info(
                "Loaded %s liked tracks from cache for bulk playback at revision %s",
                len(cached_snapshot.tracks),
                current_revision,
            )
            return cached_snapshot.tracks

        total_tracks = len(liked_tracks.track_ids) if liked_tracks is not None else 0
        tracks = tuple(
            self._music_service.get_liked_tracks(
                limit=max(total_tracks, self._BULK_LIKED_TRACK_LIMIT),
            )
        )
        self._cache_tracks(tracks)
        snapshot_revision = liked_tracks.revision if liked_tracks is not None else current_revision
        self._safe_save_liked_track_snapshot(
            LikedTrackSnapshot(
                user_id=user_id,
                revision=snapshot_revision,
                tracks=tracks,
            )
        )
        if liked_tracks is not None:
            self._safe_save_liked_track_ids(liked_tracks)
        self._logger.info("Loaded %s liked tracks for bulk playback", len(tracks))
        return tracks

    def refresh_liked_track_index(self, *, force: bool = False) -> None:
        user_id = self._current_user_id()
        if user_id is None:
            return
        cached_likes = self._safe_load_liked_track_ids(user_id)
        revision = 0 if force or cached_likes is None else cached_likes.revision
        liked_tracks = self._music_service.get_liked_track_ids(
            if_modified_since_revision=revision
        )
        if liked_tracks is None:
            self._logger.info("Liked track index is up to date at revision %s", revision)
            return
        self._safe_save_liked_track_ids(liked_tracks)
        self._logger.info(
            "Refreshed liked track index: %s ids at revision %s",
            len(liked_tracks.track_ids),
            liked_tracks.revision,
        )

    def refresh_disliked_track_index(self, *, force: bool = False) -> None:
        user_id = self._current_user_id()
        if user_id is None:
            return
        cached_dislikes = self._safe_load_disliked_track_ids(user_id)
        revision = 0 if force or cached_dislikes is None else cached_dislikes.revision
        disliked_tracks = self._music_service.get_disliked_track_ids(
            if_modified_since_revision=revision
        )
        if disliked_tracks is None:
            self._logger.info("Disliked track index is up to date at revision %s", revision)
            return
        self._safe_save_disliked_track_ids(disliked_tracks)
        self._logger.info(
            "Refreshed disliked track index: %s ids at revision %s",
            len(disliked_tracks.track_ids),
            disliked_tracks.revision,
        )

    def load_liked_albums(self, *, limit: int = 100) -> tuple[Album, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_liked_album_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached:
            return cached[:limit]
        albums = tuple(self._music_service.get_liked_albums(limit=limit))
        if user_id is not None:
            self._library_cache_repo.save_liked_album_snapshot(user_id, albums)
        self._logger.info("Loaded %s liked albums", len(albums))
        return albums

    def load_liked_artists(self, *, limit: int = 100) -> tuple[Artist, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(
                merge_cached_artist_preference_states(
                    tuple(self._library_cache_repo.load_liked_artist_snapshot(user_id) or ()),
                    self._library_cache_repo,
                    user_id=user_id,
                )
            )
            if user_id is not None
            else ()
        )
        if cached:
            return cached[:limit]
        artists = merge_cached_artist_preference_states(
            tuple(self._music_service.get_liked_artists(limit=limit)),
            self._library_cache_repo,
            user_id=user_id,
        )
        if user_id is not None:
            self._library_cache_repo.save_liked_artist_snapshot(user_id, artists)
        self._logger.info("Loaded %s liked artists", len(artists))
        return artists

    def load_disliked_artists(self, *, limit: int = 100) -> tuple[Artist, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_disliked_artist_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached:
            return cached[:limit]
        artists = tuple(
            replace(artist, is_liked=False, is_disliked=True)
            for artist in self._music_service.get_disliked_artists(limit=limit)
        )
        if user_id is not None:
            self._library_cache_repo.save_disliked_artist_snapshot(user_id, artists)
        self._logger.info("Loaded %s disliked artists", len(artists))
        return artists

    def refresh_liked_artist_snapshot(self) -> None:
        user_id = self._current_user_id()
        if user_id is None:
            return
        artists = merge_cached_artist_preference_states(
            tuple(self._music_service.get_liked_artists(limit=10_000)),
            self._library_cache_repo,
            user_id=user_id,
        )
        try:
            self._library_cache_repo.save_liked_artist_snapshot(user_id, artists)
        except StorageError as exc:
            self._logger.warning(
                "Liked artist snapshot cache save failed for %s: %s",
                user_id,
                exc,
            )
            return
        self._logger.info("Refreshed liked artist snapshot: %s artists", len(artists))

    def refresh_disliked_artist_snapshot(self) -> None:
        user_id = self._current_user_id()
        if user_id is None:
            return
        artists = tuple(
            replace(artist, is_liked=False, is_disliked=True)
            for artist in self._music_service.get_disliked_artists(limit=10_000)
        )
        try:
            self._library_cache_repo.save_disliked_artist_snapshot(user_id, artists)
        except StorageError as exc:
            self._logger.warning(
                "Disliked artist snapshot cache save failed for %s: %s",
                user_id,
                exc,
            )
            return
        self._logger.info("Refreshed disliked artist snapshot: %s artists", len(artists))

    def load_liked_playlists(self, *, limit: int = 100) -> tuple[Playlist, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_liked_playlist_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached:
            return cached[:limit]
        playlists = tuple(self._music_service.get_liked_playlists(limit=limit))
        if user_id is not None:
            self._library_cache_repo.save_liked_playlist_snapshot(user_id, playlists)
        self._logger.info("Loaded %s liked playlists", len(playlists))
        return playlists

    def load_user_playlists(self) -> tuple[Playlist, ...]:
        user_id = self._current_user_id()
        cached = (
            tuple(self._library_cache_repo.load_user_playlist_snapshot(user_id) or ())
            if user_id is not None
            else ()
        )
        if cached:
            return cached
        playlists = tuple(self._music_service.get_user_playlists())
        if user_id is not None:
            self._library_cache_repo.save_user_playlist_snapshot(user_id, playlists)
        self._logger.info("Loaded %s user playlists", len(playlists))
        return playlists

    def load_generated_playlists(self) -> tuple[Playlist, ...]:
        user_id = self._current_user_id()
        cache_user_id = user_id or "__anonymous__"
        cached = tuple(
            self._library_cache_repo.load_generated_playlist_snapshot(cache_user_id) or ()
        )
        if cached:
            return cached
        playlists = tuple(self._music_service.get_generated_playlists())
        self._library_cache_repo.save_generated_playlist_snapshot(cache_user_id, playlists)
        self._logger.info("Loaded %s generated playlists", len(playlists))
        return playlists

    def load_stations(self) -> tuple[Station, ...]:
        stations = tuple(self._music_service.get_stations())
        self._logger.info("Loaded %s stations", len(stations))
        return stations

    def load_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> tuple[Track, ...]:
        tracks = merge_cached_track_preference_states(
            tuple(self._music_service.get_playlist_tracks(playlist_id, owner_id=owner_id)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s tracks for playlist %s", len(tracks), playlist_id)
        return tracks

    def load_all_playlist_tracks(
        self,
        playlist_id: str,
        *,
        owner_id: str | None = None,
    ) -> tuple[Track, ...]:
        return self.load_playlist_tracks(playlist_id, owner_id=owner_id)

    def load_album(self, album_id: str) -> Album:
        album = self._music_service.get_album(album_id)
        self._logger.info("Loaded album %s", album_id)
        return album

    def load_album_tracks(self, album_id: str) -> tuple[Track, ...]:
        tracks = merge_cached_track_preference_states(
            tuple(self._music_service.get_album_tracks(album_id)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s tracks for album %s", len(tracks), album_id)
        return tracks

    def load_all_album_tracks(self, album_id: str) -> tuple[Track, ...]:
        return self.load_album_tracks(album_id)

    def load_station_tracks(self, station_id: str, *, limit: int = 25) -> tuple[Track, ...]:
        tracks = merge_cached_track_preference_states(
            tuple(self._music_service.get_station_tracks(station_id, limit=limit)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s station tracks for %s", len(tracks), station_id)
        return tracks

    def load_artist_tracks(self, artist_id: str, *, limit: int = 50) -> tuple[Track, ...]:
        tracks = merge_cached_track_preference_states(
            tuple(self._music_service.get_artist_tracks(artist_id, limit=limit)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s artist tracks for %s", len(tracks), artist_id)
        return tracks

    def load_all_artist_tracks(self, artist_id: str) -> tuple[Track, ...]:
        return self.load_artist_tracks(artist_id, limit=self._BULK_ARTIST_TRACK_LIMIT)

    def load_artist_direct_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> tuple[Album, ...]:
        albums = tuple(self._music_service.get_artist_direct_albums(artist_id, limit=limit))
        self._logger.info("Loaded %s direct artist albums for %s", len(albums), artist_id)
        return albums

    def load_artist_compilation_albums(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> tuple[Album, ...]:
        albums = tuple(self._music_service.get_artist_compilation_albums(artist_id, limit=limit))
        self._logger.info("Loaded %s artist compilation albums for %s", len(albums), artist_id)
        return albums

    def load_artist_playlists(
        self,
        artist_id: str,
        *,
        limit: int = 50,
    ) -> tuple[Playlist, ...]:
        playlists = tuple(self._music_service.get_artist_playlists(artist_id, limit=limit))
        self._logger.info("Loaded %s artist playlists for %s", len(playlists), artist_id)
        return playlists

    def like_track(self, track: Track) -> Track:
        self._music_service.like_track(track.id)
        liked_track = replace(track, is_liked=True, is_disliked=False)
        self._cache_tracks((liked_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_liked(user_id, track.id)
            self._library_cache_repo.mark_track_undisliked(user_id, track.id)
        self._logger.info("Liked track %s", track.id)
        return liked_track

    def unlike_track(self, track: Track) -> Track:
        self._music_service.unlike_track(track.id)
        unliked_track = replace(track, is_liked=False)
        self._cache_tracks((unliked_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_unliked(user_id, track.id)
        self._logger.info("Unliked track %s", track.id)
        return unliked_track

    def dislike_track(self, track: Track) -> Track:
        self._music_service.dislike_track(track.id)
        disliked_track = replace(track, is_liked=False, is_disliked=True)
        self._cache_tracks((disliked_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_unliked(user_id, track.id)
            self._library_cache_repo.mark_track_disliked(user_id, track.id)
        self._logger.info("Disliked track %s", track.id)
        return disliked_track

    def undislike_track(self, track: Track) -> Track:
        self._music_service.undislike_track(track.id)
        neutral_track = replace(track, is_disliked=False)
        self._cache_tracks((neutral_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_undisliked(user_id, track.id)
        self._logger.info("Undisliked track %s", track.id)
        return neutral_track

    def like_album(self, album: Album) -> Album:
        self._music_service.like_album(album.id)
        liked_album = Album(
            id=album.id,
            title=album.title,
            artists=album.artists,
            artist_ids=album.artist_ids,
            is_liked=True,
            release_type=album.release_type,
            year=album.year,
            track_count=album.track_count,
            artwork_ref=album.artwork_ref,
        )
        self._logger.info("Liked album %s", album.id)
        return liked_album

    def unlike_album(self, album: Album) -> Album:
        self._music_service.unlike_album(album.id)
        unliked_album = Album(
            id=album.id,
            title=album.title,
            artists=album.artists,
            artist_ids=album.artist_ids,
            is_liked=False,
            release_type=album.release_type,
            year=album.year,
            track_count=album.track_count,
            artwork_ref=album.artwork_ref,
        )
        self._logger.info("Unliked album %s", album.id)
        return unliked_album

    def like_artist(self, artist: Artist) -> Artist:
        self._music_service.like_artist(artist.id)
        liked_artist = replace(artist, is_liked=True, is_disliked=False)
        self._cache_artist_preference(liked_artist, snapshot_key="liked")
        self._cache_artist_preference(
            replace(liked_artist, is_liked=False),
            snapshot_key="undisliked",
        )
        self._logger.info("Liked artist %s", artist.id)
        return liked_artist

    def unlike_artist(self, artist: Artist) -> Artist:
        self._music_service.unlike_artist(artist.id)
        unliked_artist = replace(artist, is_liked=False)
        self._cache_artist_preference(unliked_artist, snapshot_key="unliked")
        self._logger.info("Unliked artist %s", artist.id)
        return unliked_artist

    def dislike_artist(self, artist: Artist) -> Artist:
        self._music_service.dislike_artist(artist.id)
        disliked_artist = replace(artist, is_liked=False, is_disliked=True)
        self._cache_artist_preference(disliked_artist, snapshot_key="disliked")
        self._cache_artist_preference(
            replace(disliked_artist, is_disliked=False),
            snapshot_key="unliked",
        )
        self._logger.info("Disliked artist %s", artist.id)
        return disliked_artist

    def undislike_artist(self, artist: Artist) -> Artist:
        self._music_service.undislike_artist(artist.id)
        neutral_artist = replace(artist, is_disliked=False)
        self._cache_artist_preference(neutral_artist, snapshot_key="undisliked")
        self._logger.info("Undisliked artist %s", artist.id)
        return neutral_artist

    def like_playlist(self, playlist: Playlist) -> Playlist:
        self._music_service.like_playlist(playlist.id, owner_id=playlist.owner_id)
        liked_playlist = Playlist(
            id=playlist.id,
            title=playlist.title,
            owner_id=playlist.owner_id,
            owner_name=playlist.owner_name,
            description=playlist.description,
            track_count=playlist.track_count,
            artwork_ref=playlist.artwork_ref,
            is_generated=playlist.is_generated,
            is_liked=True,
        )
        self._logger.info("Liked playlist %s", playlist.id)
        return liked_playlist

    def unlike_playlist(self, playlist: Playlist) -> Playlist:
        self._music_service.unlike_playlist(playlist.id, owner_id=playlist.owner_id)
        unliked_playlist = Playlist(
            id=playlist.id,
            title=playlist.title,
            owner_id=playlist.owner_id,
            owner_name=playlist.owner_name,
            description=playlist.description,
            track_count=playlist.track_count,
            artwork_ref=playlist.artwork_ref,
            is_generated=playlist.is_generated,
            is_liked=False,
        )
        self._logger.info("Unliked playlist %s", playlist.id)
        return unliked_playlist

    def cached_track(self, track_id: str) -> Track | None:
        try:
            return self._library_cache_repo.load_track_metadata(track_id)
        except StorageError as exc:
            self._logger.warning("Track cache load failed for %s: %s", track_id, exc)
            return None

    def _cache_tracks(self, tracks: tuple[Track, ...]) -> None:
        for track in tracks:
            try:
                self._library_cache_repo.save_track_metadata(track)
                if track.artwork_ref:
                    self._library_cache_repo.save_artwork_ref(track.id, track.artwork_ref)
            except StorageError as exc:
                self._logger.warning("Track cache save failed for %s: %s", track.id, exc)
                return

    def _safe_load_liked_track_snapshot(self, user_id: str | None) -> LikedTrackSnapshot | None:
        if user_id is None:
            return None
        try:
            return self._library_cache_repo.load_liked_track_snapshot(user_id)
        except StorageError as exc:
            self._logger.warning("Liked track snapshot cache load failed for %s: %s", user_id, exc)
            return None

    def _safe_save_liked_track_snapshot(self, snapshot: LikedTrackSnapshot) -> None:
        try:
            self._library_cache_repo.save_liked_track_snapshot(snapshot)
        except StorageError as exc:
            self._logger.warning(
                "Liked track snapshot cache save failed for %s: %s",
                snapshot.user_id,
                exc,
            )

    def _safe_load_liked_track_ids(self, user_id: str | None):
        if user_id is None:
            return None
        try:
            return self._library_cache_repo.load_liked_track_ids(user_id)
        except StorageError as exc:
            self._logger.warning("Liked track id cache load failed for %s: %s", user_id, exc)
            return None

    def _safe_save_liked_track_ids(self, liked_tracks) -> None:
        try:
            self._library_cache_repo.save_liked_track_ids(liked_tracks)
        except StorageError as exc:
            self._logger.warning(
                "Liked track id cache save failed for %s: %s",
                liked_tracks.user_id,
                exc,
            )

    def _safe_load_disliked_track_ids(
        self,
        user_id: str | None,
    ) -> DislikedTrackIds | None:
        if user_id is None:
            return None
        try:
            return self._library_cache_repo.load_disliked_track_ids(user_id)
        except StorageError as exc:
            self._logger.warning("Disliked track id cache load failed for %s: %s", user_id, exc)
            return None

    def _safe_save_disliked_track_ids(self, disliked_tracks: DislikedTrackIds) -> None:
        try:
            self._library_cache_repo.save_disliked_track_ids(disliked_tracks)
        except StorageError as exc:
            self._logger.warning(
                "Disliked track id cache save failed for %s: %s",
                disliked_tracks.user_id,
                exc,
            )

    def _cache_artist_preference(self, artist: Artist, *, snapshot_key: str) -> None:
        user_id = self._current_user_id()
        if user_id is None:
            return
        try:
            if snapshot_key in {"liked", "unliked"}:
                current_liked = list(
                    self._library_cache_repo.load_liked_artist_snapshot(user_id) or ()
                )
                current_liked = [item for item in current_liked if item.id != artist.id]
                if snapshot_key == "liked":
                    current_liked.append(artist)
                self._library_cache_repo.save_liked_artist_snapshot(user_id, tuple(current_liked))
                return
            current_disliked = list(
                self._library_cache_repo.load_disliked_artist_snapshot(user_id) or ()
            )
            current_disliked = [item for item in current_disliked if item.id != artist.id]
            if snapshot_key == "disliked":
                current_disliked.append(artist)
            self._library_cache_repo.save_disliked_artist_snapshot(
                user_id,
                tuple(current_disliked),
            )
        except StorageError as exc:
            self._logger.warning("Artist preference cache save failed for %s: %s", artist.id, exc)

    def _current_user_id(self) -> str | None:
        session = self._music_service.get_auth_session()
        return session.user_id if session is not None else None
