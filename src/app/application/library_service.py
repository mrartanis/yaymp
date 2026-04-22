from __future__ import annotations

from app.application.track_metadata import merge_cached_liked_states
from app.domain import (
    Album,
    Artist,
    LibraryCacheRepo,
    Logger,
    MusicService,
    Playlist,
    Station,
    Track,
)


class LibraryService:
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
        self.refresh_liked_track_index(force=True)
        tracks = tuple(self._music_service.get_liked_tracks(limit=limit))
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s liked tracks", len(tracks))
        return tracks

    def refresh_liked_track_index(self, *, force: bool = False) -> None:
        user_id = self._current_user_id()
        if user_id is None:
            return
        cached_likes = self._library_cache_repo.load_liked_track_ids(user_id)
        revision = 0 if force or cached_likes is None else cached_likes.revision
        liked_tracks = self._music_service.get_liked_track_ids(
            if_modified_since_revision=revision
        )
        if liked_tracks is None:
            self._logger.info("Liked track index is up to date at revision %s", revision)
            return
        self._library_cache_repo.save_liked_track_ids(liked_tracks)
        self._logger.info(
            "Refreshed liked track index: %s ids at revision %s",
            len(liked_tracks.track_ids),
            liked_tracks.revision,
        )

    def load_liked_albums(self, *, limit: int = 100) -> tuple[Album, ...]:
        albums = tuple(self._music_service.get_liked_albums(limit=limit))
        self._logger.info("Loaded %s liked albums", len(albums))
        return albums

    def load_liked_artists(self, *, limit: int = 100) -> tuple[Artist, ...]:
        artists = tuple(self._music_service.get_liked_artists(limit=limit))
        self._logger.info("Loaded %s liked artists", len(artists))
        return artists

    def load_user_playlists(self) -> tuple[Playlist, ...]:
        playlists = tuple(self._music_service.get_user_playlists())
        self._logger.info("Loaded %s user playlists", len(playlists))
        return playlists

    def load_generated_playlists(self) -> tuple[Playlist, ...]:
        playlists = tuple(self._music_service.get_generated_playlists())
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
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_playlist_tracks(playlist_id, owner_id=owner_id)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s tracks for playlist %s", len(tracks), playlist_id)
        return tracks

    def load_album(self, album_id: str) -> Album:
        album = self._music_service.get_album(album_id)
        self._logger.info("Loaded album %s", album_id)
        return album

    def load_album_tracks(self, album_id: str) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_album_tracks(album_id)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s tracks for album %s", len(tracks), album_id)
        return tracks

    def load_station_tracks(self, station_id: str, *, limit: int = 25) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_station_tracks(station_id, limit=limit)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s station tracks for %s", len(tracks), station_id)
        return tracks

    def load_artist_tracks(self, artist_id: str, *, limit: int = 50) -> tuple[Track, ...]:
        tracks = merge_cached_liked_states(
            tuple(self._music_service.get_artist_tracks(artist_id, limit=limit)),
            self._library_cache_repo,
            user_id=self._current_user_id(),
        )
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s artist tracks for %s", len(tracks), artist_id)
        return tracks

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

    def like_track(self, track: Track) -> Track:
        self._music_service.like_track(track.id)
        liked_track = Track(
            id=track.id,
            title=track.title,
            artists=track.artists,
            album_title=track.album_title,
            album_year=track.album_year,
            duration_ms=track.duration_ms,
            stream_ref=track.stream_ref,
            artwork_ref=track.artwork_ref,
            available=track.available,
            is_liked=True,
        )
        self._cache_tracks((liked_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_liked(user_id, track.id)
        self._logger.info("Liked track %s", track.id)
        return liked_track

    def unlike_track(self, track: Track) -> Track:
        self._music_service.unlike_track(track.id)
        unliked_track = Track(
            id=track.id,
            title=track.title,
            artists=track.artists,
            album_title=track.album_title,
            album_year=track.album_year,
            duration_ms=track.duration_ms,
            stream_ref=track.stream_ref,
            artwork_ref=track.artwork_ref,
            available=track.available,
            is_liked=False,
        )
        self._cache_tracks((unliked_track,))
        user_id = self._current_user_id()
        if user_id is not None:
            self._library_cache_repo.mark_track_unliked(user_id, track.id)
        self._logger.info("Unliked track %s", track.id)
        return unliked_track

    def cached_track(self, track_id: str) -> Track | None:
        return self._library_cache_repo.load_track_metadata(track_id)

    def _cache_tracks(self, tracks: tuple[Track, ...]) -> None:
        for track in tracks:
            self._library_cache_repo.save_track_metadata(track)
            if track.artwork_ref:
                self._library_cache_repo.save_artwork_ref(track.id, track.artwork_ref)

    def _current_user_id(self) -> str | None:
        session = self._music_service.get_auth_session()
        return session.user_id if session is not None else None
