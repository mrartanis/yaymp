from __future__ import annotations

from app.domain import LibraryCacheRepo, Logger, MusicService, Playlist, Station, Track


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
        tracks = tuple(self._music_service.get_liked_tracks(limit=limit))
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s liked tracks", len(tracks))
        return tracks

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

    def load_playlist_tracks(self, playlist_id: str) -> tuple[Track, ...]:
        tracks = tuple(self._music_service.get_playlist_tracks(playlist_id))
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s tracks for playlist %s", len(tracks), playlist_id)
        return tracks

    def load_station_tracks(self, station_id: str, *, limit: int = 25) -> tuple[Track, ...]:
        tracks = tuple(self._music_service.get_station_tracks(station_id, limit=limit))
        self._cache_tracks(tracks)
        self._logger.info("Loaded %s station tracks for %s", len(tracks), station_id)
        return tracks

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
        self._logger.info("Unliked track %s", track.id)
        return unliked_track

    def cached_track(self, track_id: str) -> Track | None:
        return self._library_cache_repo.load_track_metadata(track_id)

    def _cache_tracks(self, tracks: tuple[Track, ...]) -> None:
        for track in tracks:
            self._library_cache_repo.save_track_metadata(track)
            if track.artwork_ref:
                self._library_cache_repo.save_artwork_ref(track.id, track.artwork_ref)
