from __future__ import annotations

from app.domain import LibraryCacheRepo, Logger, MusicService, Track


class SearchService:
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

    def search_tracks(self, query: str, *, limit: int = 25) -> tuple[Track, ...]:
        normalized_query = query.strip()
        if not normalized_query:
            return ()

        tracks = tuple(self._music_service.search_tracks(normalized_query, limit=limit))
        self._cache_tracks(tracks)
        self._remember_recent_search(normalized_query)
        self._logger.info("Search returned %s tracks for query %s", len(tracks), normalized_query)
        return tracks

    def load_recent_searches(self) -> tuple[str, ...]:
        return tuple(self._library_cache_repo.load_recent_searches())

    def _remember_recent_search(self, query: str) -> None:
        current = [
            item for item in self._library_cache_repo.load_recent_searches() if item != query
        ]
        current.insert(0, query)
        self._library_cache_repo.save_recent_searches(tuple(current[:10]))

    def _cache_tracks(self, tracks: tuple[Track, ...]) -> None:
        for track in tracks:
            self._library_cache_repo.save_track_metadata(track)
            if track.artwork_ref:
                self._library_cache_repo.save_artwork_ref(track.id, track.artwork_ref)
