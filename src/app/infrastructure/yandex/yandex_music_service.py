from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.domain import AudioQuality, AuthSession, MusicService, Playlist, Station, Track
from app.domain.errors import AuthError, NetworkError, StreamResolveError, TrackUnavailableError


class YandexMusicService(MusicService):
    def __init__(
        self,
        *,
        session: AuthSession | None = None,
        token: str | None = None,
        client: Any | None = None,
        logger: Any | None = None,
    ) -> None:
        effective_session = session
        if effective_session is None and token:
            effective_session = AuthSession(user_id="token-session", token=token)

        self._session = effective_session
        self._client = client
        self._logger = logger
        self._audio_quality = AudioQuality.HQ

    def get_auth_session(self) -> AuthSession | None:
        return self._session

    def build_auth_session(
        self,
        token: str,
        *,
        expires_at: datetime | None = None,
    ) -> AuthSession:
        self._session = AuthSession(user_id="token-session", token=token, expires_at=expires_at)
        self._client = None
        client = self._require_client()

        try:
            me = client.me
            account = me.account
            user_id = str(getattr(account, "uid", getattr(account, "id", "token-session")))
            display_name = getattr(account, "login", None) or getattr(account, "display_name", None)
        except Exception as exc:
            raise AuthError("Failed to load Yandex account profile") from exc

        self._session = AuthSession(
            user_id=user_id,
            token=token,
            expires_at=expires_at,
            display_name=display_name,
        )
        return self._session

    def get_track(self, track_id: str) -> Track:
        client = self._require_client()
        try:
            raw_tracks = client.tracks([track_id])
            raw_track = raw_tracks[0] if raw_tracks else None
        except Exception as exc:
            raise NetworkError(f"Failed to load track {track_id}") from exc
        if raw_track is None:
            raise TrackUnavailableError(f"Track {track_id} is unavailable")
        return self._map_track(raw_track)

    def search_tracks(self, query: str, *, limit: int = 25) -> Sequence[Track]:
        client = self._require_client()
        try:
            search_result = client.search(query, type_="track")
        except Exception as exc:
            raise NetworkError(f"Search failed for query {query!r}") from exc

        tracks = getattr(getattr(search_result, "tracks", None), "results", None) or ()
        return tuple(self._map_track(track) for track in tracks[:limit])

    def get_liked_tracks(self, *, limit: int = 100) -> Sequence[Track]:
        client = self._require_client()
        try:
            likes = client.users_likes_tracks()
            raw_tracks = likes.fetch_tracks() if hasattr(likes, "fetch_tracks") else ()
        except Exception as exc:
            raise NetworkError("Failed to load liked tracks") from exc
        return tuple(self._map_track(track, is_liked=True) for track in raw_tracks[:limit])

    def like_track(self, track_id: str) -> None:
        client = self._require_client()
        try:
            self._call_track_mutation(client.users_likes_tracks_add, track_id)
        except Exception as exc:
            raise NetworkError(f"Failed to like track {track_id}") from exc

    def unlike_track(self, track_id: str) -> None:
        client = self._require_client()
        try:
            self._call_track_mutation(client.users_likes_tracks_remove, track_id)
        except Exception as exc:
            raise NetworkError(f"Failed to unlike track {track_id}") from exc

    def set_audio_quality(self, quality: AudioQuality) -> None:
        self._audio_quality = quality

    def get_audio_quality(self) -> AudioQuality:
        return self._audio_quality

    def get_user_playlists(self) -> Sequence[Playlist]:
        client = self._require_client()
        try:
            raw_playlists = client.users_playlists_list()
        except Exception as exc:
            raise NetworkError("Failed to load user playlists") from exc
        return tuple(self._map_playlist(playlist) for playlist in raw_playlists)

    def get_generated_playlists(self) -> Sequence[Playlist]:
        client = self._require_client()
        try:
            feed = client.feed()
        except Exception as exc:
            raise NetworkError("Failed to load generated playlists") from exc

        generated = getattr(feed, "generated_playlists", None) or ()
        playlists: list[Playlist] = []
        for item in generated:
            data = getattr(item, "data", None)
            if data is not None:
                playlists.append(self._map_playlist(data))
        return tuple(playlists)

    def get_stations(self) -> Sequence[Station]:
        client = self._require_client()
        try:
            raw_stations = client.rotor_stations_list()
        except Exception as exc:
            raise NetworkError("Failed to load stations") from exc
        return tuple(
            self._map_station(item) for item in raw_stations if getattr(item, "station", None)
        )

    def get_station_tracks(self, station_id: str, *, limit: int = 25) -> Sequence[Track]:
        client = self._require_client()
        try:
            result = client.rotor_station_tracks(station_id)
        except Exception as exc:
            raise NetworkError(f"Failed to load station tracks for {station_id}") from exc

        tracks: list[Track] = []
        for item in getattr(result, "sequence", None) or ():
            raw_track = getattr(item, "track", None)
            if raw_track is not None:
                tracks.append(self._map_track(raw_track))
            if len(tracks) >= limit:
                break
        return tuple(tracks)

    def get_playlist(self, playlist_id: str) -> Playlist:
        client = self._require_client()
        try:
            raw_playlist = client.users_playlists(playlist_id)
        except Exception as exc:
            raise NetworkError(f"Failed to load playlist {playlist_id}") from exc
        return self._map_playlist(raw_playlist)

    def get_playlist_tracks(self, playlist_id: str) -> Sequence[Track]:
        client = self._require_client()
        try:
            raw_playlist = client.users_playlists(playlist_id)
            entries = getattr(raw_playlist, "tracks", ()) or ()
        except Exception as exc:
            raise NetworkError(f"Failed to load playlist tracks for {playlist_id}") from exc

        tracks: list[Track] = []
        for entry in entries:
            raw_track = getattr(entry, "track", entry)
            tracks.append(self._map_track(raw_track))
        return tuple(tracks)

    def resolve_stream_ref(self, track: Track) -> str:
        if not track.available:
            raise TrackUnavailableError(f"Track {track.id} is unavailable")

        client = self._require_client()
        try:
            download_infos = client.tracks_download_info(track.id, get_direct_links=True)
        except Exception as exc:
            raise StreamResolveError(f"Failed to resolve stream for track {track.id}") from exc

        if not download_infos:
            raise TrackUnavailableError(f"Track {track.id} has no playable stream")

        ranked_infos = self._rank_download_infos(download_infos)
        self._log_download_quality_options(track.id, ranked_infos)
        for info in ranked_infos:
            direct_link = getattr(info, "direct_link", None)
            if direct_link:
                return direct_link
            if hasattr(info, "get_direct_link"):
                try:
                    resolved = info.get_direct_link()
                except Exception as exc:
                    raise StreamResolveError(
                        f"Failed to resolve stream for track {track.id}"
                    ) from exc
                if resolved:
                    return resolved

        raise TrackUnavailableError(f"Track {track.id} has no playable stream")

    def _require_client(self) -> Any:
        if self._session is None or not self._session.token:
            raise AuthError("No Yandex Music session is configured")
        if self._client is not None:
            return self._client
        try:
            from yandex_music import Client
        except ImportError as exc:
            raise AuthError("yandex-music package is not installed") from exc

        try:
            self._client = Client(self._session.token).init()
        except Exception as exc:
            raise AuthError("Failed to initialize Yandex Music client") from exc
        return self._client

    def _map_track(self, raw_track: Any, *, is_liked: bool = False) -> Track:
        artists = tuple(
            getattr(artist, "name", str(artist))
            for artist in (getattr(raw_track, "artists", None) or ())
        )
        albums = getattr(raw_track, "albums", None) or ()
        album = albums[0] if albums else None
        track_id = str(raw_track.id)
        title = getattr(raw_track, "title", track_id)
        duration_ms = getattr(raw_track, "duration_ms", None)
        available = bool(getattr(raw_track, "available", True))
        album_year = getattr(album, "year", None)
        return Track(
            id=track_id,
            title=title,
            artists=artists or ("Unknown Artist",),
            album_title=getattr(album, "title", None),
            album_year=int(album_year) if album_year else None,
            duration_ms=duration_ms,
            artwork_ref=getattr(raw_track, "cover_uri", None),
            available=available,
            is_liked=is_liked,
        )

    def _map_playlist(self, raw_playlist: Any) -> Playlist:
        owner = getattr(raw_playlist, "owner", None)
        owner_name = getattr(owner, "name", None) or getattr(owner, "login", None)
        playlist_id = str(
            getattr(raw_playlist, "kind", getattr(raw_playlist, "playlist_uuid", "unknown"))
        )
        artwork_ref = getattr(raw_playlist, "cover_uri", None)
        if artwork_ref is None and hasattr(raw_playlist, "get_og_image_url"):
            artwork_ref = raw_playlist.get_og_image_url()
        return Playlist(
            id=playlist_id,
            title=getattr(raw_playlist, "title", playlist_id),
            owner_name=owner_name,
            description=getattr(raw_playlist, "description", None),
            track_count=getattr(raw_playlist, "track_count", None),
            artwork_ref=artwork_ref,
        )

    def _map_station(self, raw_result: Any) -> Station:
        station = raw_result.station
        station_id = self._station_key(station)
        return Station(
            id=station_id,
            title=getattr(raw_result, "rup_title", None) or getattr(station, "name", station_id),
            description=getattr(raw_result, "rup_description", None),
            icon_ref=getattr(station, "full_image_url", None),
        )

    def _station_key(self, station: Any) -> str:
        raw_id = getattr(station, "id", None)
        if raw_id is None:
            return str(getattr(station, "name", "station"))
        return f"{raw_id.type}:{raw_id.tag}"

    def _call_track_mutation(self, operation: Any, track_id: str) -> None:
        try:
            operation(track_id)
        except TypeError:
            operation([track_id])

    def _rank_download_infos(self, download_infos: Sequence[Any]) -> tuple[Any, ...]:
        sorted_infos = sorted(
            download_infos,
            key=lambda info: int(getattr(info, "bitrate_in_kbps", 0) or 0),
        )
        if self._audio_quality is AudioQuality.LQ:
            return tuple(sorted_infos)
        if self._audio_quality is AudioQuality.HQ:
            return tuple(reversed(sorted_infos))

        target_bitrate = 192
        return tuple(
            sorted(
                sorted_infos,
                key=lambda info: (
                    abs(int(getattr(info, "bitrate_in_kbps", 0) or 0) - target_bitrate),
                    int(getattr(info, "bitrate_in_kbps", 0) or 0),
                ),
            )
        )

    def _log_download_quality_options(self, track_id: str, download_infos: Sequence[Any]) -> None:
        if self._logger is None:
            return
        options = ", ".join(
            f"{getattr(info, 'codec', '?')}:{getattr(info, 'bitrate_in_kbps', '?')}"
            for info in download_infos
        )
        selected = download_infos[0] if download_infos else None
        selected_label = "none"
        if selected is not None:
            selected_label = (
                f"{getattr(selected, 'codec', '?')}:"
                f"{getattr(selected, 'bitrate_in_kbps', '?')}"
            )
        self._logger.info(
            "Yandex quality track=%s mode=%s selected=%s options=[%s]",
            track_id,
            self._audio_quality.value,
            selected_label,
            options,
        )
