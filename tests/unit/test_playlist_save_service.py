from __future__ import annotations

import pytest

from app.application.playlist_save_service import PlaylistSaveService
from app.domain import (
    NetworkError,
    Playlist,
    PlaylistNameConflictError,
    PlaylistSaveMode,
    PlaylistSaveRequest,
    PlaylistVisibility,
    Track,
)


class TestLogger:
    def debug(self, message: str, *args: object) -> None:
        del message, args

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        del message, args

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


class FakeLibraryService:
    def __init__(self, snapshots: list[tuple[Playlist, ...]]) -> None:
        self.snapshots = snapshots
        self.load_calls = 0
        self.cached_snapshot: tuple[Playlist, ...] = ()

    def load_user_playlists(self, *, force_refresh: bool = False) -> tuple[Playlist, ...]:
        assert force_refresh is True
        value = self.snapshots[min(self.load_calls, len(self.snapshots) - 1)]
        self.load_calls += 1
        return value

    def update_user_playlist_snapshot(self, playlists: tuple[Playlist, ...]) -> None:
        self.cached_snapshot = playlists


class FakeMusicService:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.deleted: list[tuple[str, str | None]] = []
        self.appended: list[tuple[str, tuple[Track, ...], str | None]] = []
        self.replaced: list[tuple[str, tuple[Track, ...], str | None]] = []
        self.append_error: NetworkError | None = None

    def get_tracks(self, track_ids: tuple[str, ...]) -> tuple[Track, ...]:
        return tuple(
            Track(
                id=track_id,
                title=f"Resolved {track_id}",
                artists=("Artist",),
                album_id=f"album-{track_id}",
            )
            for track_id in track_ids
        )

    def create_playlist(self, title: str, *, visibility: str) -> Playlist:
        self.created.append((title, visibility))
        return Playlist(id="new-1", title=title, owner_id="7", visibility=visibility)

    def delete_playlist(self, playlist_id: str, *, owner_id: str | None = None) -> None:
        self.deleted.append((playlist_id, owner_id))

    def append_playlist_tracks(
        self,
        playlist_id: str,
        tracks: tuple[Track, ...],
        *,
        owner_id: str | None = None,
    ) -> Playlist:
        self.appended.append((playlist_id, tuple(tracks), owner_id))
        if self.append_error is not None:
            raise self.append_error
        return Playlist(
            id=playlist_id,
            title="Road trip",
            owner_id=owner_id,
            track_count=len(tracks),
        )

    def replace_playlist_tracks(
        self,
        playlist_id: str,
        tracks: tuple[Track, ...],
        *,
        owner_id: str | None = None,
    ) -> Playlist:
        self.replaced.append((playlist_id, tuple(tracks), owner_id))
        return Playlist(
            id=playlist_id,
            title="Existing",
            owner_id=owner_id,
            track_count=len(tracks),
        )


def _track(track_id: str, *, album_id: str | None = "album-1", available: bool = True) -> Track:
    return Track(
        id=track_id,
        title=track_id,
        artists=("Artist",),
        album_id=album_id,
        available=available,
    )


def test_create_revalidates_name_against_fresh_server_catalog() -> None:
    existing = Playlist(id="1", title="  ROAD Trip ", owner_id="7")
    library = FakeLibraryService([(existing,)])
    music = FakeMusicService()
    service = PlaylistSaveService(
        music_service=music,
        library_service=library,  # type: ignore[arg-type]
        logger=TestLogger(),
    )

    with pytest.raises(PlaylistNameConflictError):
        service.save(
            PlaylistSaveRequest(
                tracks=(_track("one"),),
                mode=PlaylistSaveMode.CREATE,
                title="road trip",
            )
        )

    assert library.load_calls == 1
    assert music.created == []


def test_create_resolves_metadata_filters_tracks_and_preserves_order() -> None:
    saved = Playlist(id="new-1", title="Road trip", owner_id="7", track_count=2)
    library = FakeLibraryService([(), (saved,)])
    music = FakeMusicService()
    service = PlaylistSaveService(
        music_service=music,
        library_service=library,  # type: ignore[arg-type]
        logger=TestLogger(),
    )

    result = service.save(
        PlaylistSaveRequest(
            tracks=(
                _track("one"),
                _track("two", album_id=None),
                _track("blocked", available=False),
            ),
            mode=PlaylistSaveMode.CREATE,
            title=" Road trip ",
            visibility=PlaylistVisibility.PRIVATE,
        )
    )

    assert music.created == [("Road trip", "private")]
    assert [track.id for track in music.appended[0][1]] == ["one", "two"]
    assert music.appended[0][1][1].album_id == "album-two"
    assert result.saved_count == 2
    assert result.skipped_count == 1
    assert result.user_playlists == (saved,)
    assert library.load_calls == 2


def test_create_removes_incomplete_playlist_when_track_update_fails() -> None:
    library = FakeLibraryService([()])
    music = FakeMusicService()
    music.append_error = NetworkError("update failed")
    service = PlaylistSaveService(
        music_service=music,
        library_service=library,  # type: ignore[arg-type]
        logger=TestLogger(),
    )

    with pytest.raises(NetworkError, match="update failed"):
        service.save(
            PlaylistSaveRequest(
                tracks=(_track("one"),),
                mode=PlaylistSaveMode.CREATE,
                title="Road trip",
            )
        )

    assert music.deleted == [("new-1", "7")]


def test_replace_uses_fresh_target_from_server_catalog() -> None:
    stale = Playlist(id="1", title="Old", owner_id="7", revision=1)
    fresh = Playlist(id="1", title="Existing", owner_id="7", revision=8)
    library = FakeLibraryService([(fresh,), (fresh,)])
    music = FakeMusicService()
    service = PlaylistSaveService(
        music_service=music,
        library_service=library,  # type: ignore[arg-type]
        logger=TestLogger(),
    )

    result = service.save(
        PlaylistSaveRequest(
            tracks=(_track("one"),),
            mode=PlaylistSaveMode.REPLACE,
            target=stale,
        )
    )

    assert music.replaced[0][0:3:2] == ("1", "7")
    assert result.saved_count == 1
