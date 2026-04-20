from __future__ import annotations

from app.domain import Logger, MusicService, Playlist, Station, Track


class LibraryService:
    def __init__(self, *, music_service: MusicService, logger: Logger) -> None:
        self._music_service = music_service
        self._logger = logger

    def load_liked_tracks(self, *, limit: int = 100) -> tuple[Track, ...]:
        tracks = tuple(self._music_service.get_liked_tracks(limit=limit))
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
        self._logger.info("Loaded %s tracks for playlist %s", len(tracks), playlist_id)
        return tracks

    def load_station_tracks(self, station_id: str, *, limit: int = 25) -> tuple[Track, ...]:
        tracks = tuple(self._music_service.get_station_tracks(station_id, limit=limit))
        self._logger.info("Loaded %s station tracks for %s", len(tracks), station_id)
        return tracks
