from __future__ import annotations

from dataclasses import replace

from app.domain import Artist, LibraryCacheRepo, Track
from app.domain.errors import StorageError


def merge_cached_track_preferences(
    track: Track,
    cache_repo: LibraryCacheRepo | None,
    *,
    user_id: str | None = None,
) -> Track:
    if cache_repo is None:
        return track

    normalized_track_id = _normalize_track_id(track.id)
    liked = track.is_liked
    disliked = track.is_disliked

    try:
        if user_id is not None:
            liked_tracks = cache_repo.load_liked_track_ids(user_id)
            if liked_tracks is not None:
                liked = normalized_track_id in liked_tracks.track_ids
            disliked_tracks = cache_repo.load_disliked_track_ids(user_id)
            if disliked_tracks is not None:
                disliked = normalized_track_id in disliked_tracks.track_ids

        cached_track = cache_repo.load_track_metadata(track.id)
    except StorageError:
        return track

    if cached_track is not None:
        liked = liked or cached_track.is_liked
        disliked = disliked or cached_track.is_disliked

    if disliked:
        liked = False
    if liked == track.is_liked and disliked == track.is_disliked:
        return track
    return replace(track, is_liked=liked, is_disliked=disliked)


def merge_cached_track_preference_states(
    tracks: tuple[Track, ...],
    cache_repo: LibraryCacheRepo | None,
    *,
    user_id: str | None = None,
) -> tuple[Track, ...]:
    return tuple(
        merge_cached_track_preferences(track, cache_repo, user_id=user_id) for track in tracks
    )


def merge_cached_artist_preferences(
    artist: Artist,
    cache_repo: LibraryCacheRepo | None,
    *,
    user_id: str | None = None,
) -> Artist:
    if cache_repo is None or user_id is None:
        return artist

    try:
        liked_artists = cache_repo.load_liked_artist_snapshot(user_id) or ()
        disliked_artists = cache_repo.load_disliked_artist_snapshot(user_id) or ()
    except StorageError:
        return artist

    liked = artist.is_liked or any(item.id == artist.id for item in liked_artists)
    disliked = artist.is_disliked or any(item.id == artist.id for item in disliked_artists)
    if disliked:
        liked = False
    if liked == artist.is_liked and disliked == artist.is_disliked:
        return artist
    return replace(artist, is_liked=liked, is_disliked=disliked)


def merge_cached_artist_preference_states(
    artists: tuple[Artist, ...],
    cache_repo: LibraryCacheRepo | None,
    *,
    user_id: str | None = None,
) -> tuple[Artist, ...]:
    return tuple(
        merge_cached_artist_preferences(artist, cache_repo, user_id=user_id)
        for artist in artists
    )


def _normalize_track_id(track_id: str) -> str:
    raw_track_id = str(track_id)
    base_id, separator, album_id = raw_track_id.partition(":")
    if separator and base_id.isdigit() and album_id.isdigit():
        return base_id
    return raw_track_id
