from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu

from app.domain import Album, Artist, Playlist, Station, Track
from app.domain.playback import QueueItem
from app.presentation.qt.library_controller import BrowserItem


class MainWindowLibraryMixin:
    def _render_library_error(self, message: str) -> None:
        self._status_label.setText(f"Library error: {message}")

    def _render_track_liked(self, track: Track) -> None:
        self._track_like_overrides[track.id] = True
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
            self._render_current_track_like_button(True)
        self._replace_content_track(track)
        self._update_queue_track_like(track)
        self._status_label.setText(f"Liked: {track.title}")

    def _render_track_unliked(self, track: Track) -> None:
        self._track_like_overrides[track.id] = False
        if self._current_track is not None and self._current_track.id == track.id:
            self._current_track = track
            self._render_current_track_like_button(False)
        self._replace_content_track(track)
        self._update_queue_track_like(track)
        self._status_label.setText(f"Unliked: {track.title}")

    def _render_album_liked(self, album: Album) -> None:
        self._replace_content_entity(album)
        self._status_label.setText(f"Liked album: {album.title}")

    def _render_album_unliked(self, album: Album) -> None:
        self._replace_content_entity(album)
        self._status_label.setText(f"Unliked album: {album.title}")

    def _render_artist_liked(self, artist: Artist) -> None:
        self._replace_content_entity(artist)
        self._status_label.setText(f"Liked artist: {artist.name}")

    def _render_artist_unliked(self, artist: Artist) -> None:
        self._replace_content_entity(artist)
        self._status_label.setText(f"Unliked artist: {artist.name}")

    def _render_playlist_liked(self, playlist: Playlist) -> None:
        self._replace_content_entity(playlist)
        self._status_label.setText(f"Liked playlist: {playlist.title}")

    def _render_playlist_unliked(self, playlist: Playlist) -> None:
        self._replace_content_entity(playlist)
        self._status_label.setText(f"Unliked playlist: {playlist.title}")

    def _like_selected_or_current_track(self) -> None:
        track = self._selected_or_current_track()
        if track is None:
            self._status_label.setText("Library error: select or play a track first")
            return
        self._library_controller.like_track(track)

    def _unlike_selected_or_current_track(self) -> None:
        track = self._selected_or_current_track()
        if track is None:
            self._status_label.setText("Library error: select or play a track first")
            return
        self._library_controller.unlike_track(track)

    def _selected_or_current_track(self) -> Track | None:
        item = self._content_list.currentItem()
        if item is not None:
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(browser_item, BrowserItem) and isinstance(browser_item.payload, Track):
                return browser_item.payload
        return self._current_track

    def _play_current_source(self) -> None:
        content = self._current_browser_content
        if (
            content is None
            or not content.source_tracks
            or not content.source_type
            or not content.source_id
        ):
            return
        self._controller.play_tracks(
            content.source_tracks,
            start_index=0,
            source_type=content.source_type,
            source_id=content.source_id,
        )

    def _append_current_source(self) -> None:
        content = self._current_browser_content
        if (
            content is None
            or not content.source_tracks
            or not content.source_type
            or not content.source_id
        ):
            return
        self._controller.append_tracks(
            content.source_tracks,
            source_type=content.source_type,
            source_id=content.source_id,
        )

    def _replace_content_track(self, track: Track) -> None:
        for index in range(self._content_list.count()):
            item = self._content_list.item(index)
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(browser_item, BrowserItem):
                continue
            if not isinstance(browser_item.payload, Track):
                continue
            if browser_item.payload.id != track.id:
                continue
            title = track.title
            text = title
            subtitle = ", ".join(track.artists)
            if track.album_title:
                subtitle = f"{subtitle} | {track.album_title}" if subtitle else track.album_title
            if subtitle:
                text = f"{title}\n{subtitle}"
            item.setText(text)
            item.setData(
                Qt.ItemDataRole.UserRole,
                BrowserItem(
                    kind=browser_item.kind,
                    title=title,
                    subtitle=subtitle,
                    payload=track,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                    source_tracks=browser_item.source_tracks,
                    source_index=browser_item.source_index,
                ),
            )
            break

    def _update_queue_track_like(self, track: Track) -> None:
        for index in range(self._queue_list.count()):
            item = self._queue_list.item(index)
            queue_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(queue_item, QueueItem):
                continue
            if queue_item.track.id != track.id:
                continue
            item.setData(
                Qt.ItemDataRole.UserRole,
                replace(queue_item, track=track),
            )
        self._update_queue_active_row(
            self._rendered_active_index,
            self._rendered_playback_status,
        )

    def _replace_content_entity(self, entity: Album | Artist | Playlist) -> None:
        for index in range(self._content_list.count()):
            item = self._content_list.item(index)
            browser_item = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(browser_item, BrowserItem):
                continue
            payload = browser_item.payload
            if type(payload) is not type(entity):
                continue
            if getattr(payload, "id", None) != getattr(entity, "id", None):
                continue
            item.setData(
                Qt.ItemDataRole.UserRole,
                BrowserItem(
                    kind=browser_item.kind,
                    title=browser_item.title,
                    subtitle=browser_item.subtitle,
                    payload=entity,
                    source_type=browser_item.source_type,
                    source_id=browser_item.source_id,
                    source_tracks=browser_item.source_tracks,
                    source_index=browser_item.source_index,
                ),
            )
            break

    def _show_content_context_menu(self, position: QPoint) -> None:
        item = self._content_list.itemAt(position)
        if item is None:
            return
        self._content_list.setCurrentItem(item)
        browser_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(browser_item, BrowserItem):
            return
        menu = QMenu(self)
        if not self._populate_browser_item_menu(menu, browser_item):
            return
        menu.exec(self._content_list.viewport().mapToGlobal(position))

    def _show_queue_context_menu(self, position: QPoint) -> None:
        item = self._queue_list.itemAt(position)
        if item is None:
            return
        self._queue_list.setCurrentItem(item)
        self._select_queue_highlight(item)
        queue_item = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(queue_item, QueueItem):
            return
        menu = QMenu(self)
        queue_index = self._queue_list.row(item)
        if not self._populate_queue_item_menu(menu, queue_item, queue_index):
            return
        menu.exec(self._queue_list.viewport().mapToGlobal(position))

    def _populate_browser_item_menu(self, menu: QMenu, browser_item: BrowserItem) -> bool:
        payload = browser_item.payload
        if isinstance(payload, Track):
            return self._populate_track_menu(menu, payload)
        if isinstance(payload, Album):
            self._add_copy_share_link_action(menu, self._album_share_link(payload))
            self._add_album_like_action(menu, payload)
            self._add_album_radio_action(menu, payload)
            self._add_go_to_artist_actions(menu, payload.artist_ids, payload.artists)
            return not menu.isEmpty()
        if isinstance(payload, Artist):
            self._add_copy_share_link_action(menu, self._artist_share_link(payload))
            self._add_artist_like_action(menu, payload)
            self._add_artist_radio_action(menu, payload)
            return not menu.isEmpty()
        if isinstance(payload, Playlist):
            self._add_copy_share_link_action(menu, self._playlist_share_link(payload))
            self._add_playlist_like_action(menu, payload)
            return not menu.isEmpty()
        if isinstance(payload, Station):
            self._add_copy_share_link_action(menu, self._station_share_link(payload))
            return not menu.isEmpty()
        return False

    def _populate_track_menu(
        self,
        menu: QMenu,
        track: Track,
        *,
        include_queue_actions: bool = True,
    ) -> bool:
        self._add_copy_share_link_action(menu, self._track_share_link(track))
        action_text = "Unlike" if track.is_liked else "Like"
        toggle_like = QAction(action_text, self)
        toggle_like.triggered.connect(
            lambda checked=False, selected_track=track: self._toggle_track_like(selected_track)
        )
        menu.addAction(toggle_like)
        if include_queue_actions:
            add_to_queue = QAction("Add to queue", self)
            add_to_queue.triggered.connect(
                lambda checked=False, selected_track=track: self._controller.append_tracks(
                    (selected_track,),
                    source_type="track",
                    source_id=selected_track.id,
                )
            )
            menu.addAction(add_to_queue)
            play_next = QAction("Play next", self)
            play_next.triggered.connect(
                lambda checked=False, selected_track=track: self._controller.play_track_next(
                    selected_track,
                    source_type="track",
                    source_id=selected_track.id,
                )
            )
            menu.addAction(play_next)
        self._add_track_radio_action(menu, track)
        self._add_go_to_artist_actions(menu, track.artist_ids, track.artists)
        if track.album_id:
            go_to_album = QAction("Go to album", self)
            album_id = track.album_id
            go_to_album.triggered.connect(
                lambda checked=False, selected_album_id=album_id: (
                    self._library_controller.open_album_by_id(selected_album_id)
                )
            )
            menu.addAction(go_to_album)
        return not menu.isEmpty()

    def _populate_queue_item_menu(
        self,
        menu: QMenu,
        queue_item: QueueItem,
        queue_index: int,
    ) -> bool:
        self._populate_track_menu(menu, queue_item.track, include_queue_actions=False)
        play_next = QAction("Play next", self)
        play_next.triggered.connect(
            lambda checked=False, index=queue_index: self._controller.move_queue_item_next(index)
        )
        menu.addAction(play_next)
        remove_action = QAction("Remove from queue", self)
        remove_action.triggered.connect(
            lambda checked=False, index=queue_index: self._controller.remove_queue_index(index)
        )
        menu.addAction(remove_action)
        return not menu.isEmpty()

    def _toggle_track_like(self, track: Track) -> None:
        if track.is_liked:
            self._library_controller.unlike_track(track)
            return
        self._library_controller.like_track(track)

    def _add_album_like_action(self, menu: QMenu, album: Album) -> None:
        action = QAction("Unlike" if album.is_liked else "Like", self)
        action.triggered.connect(
            lambda checked=False, selected_album=album: self._toggle_album_like(selected_album)
        )
        menu.addAction(action)

    def _add_artist_like_action(self, menu: QMenu, artist: Artist) -> None:
        action = QAction("Unlike" if artist.is_liked else "Like", self)
        action.triggered.connect(
            lambda checked=False, selected_artist=artist: self._toggle_artist_like(selected_artist)
        )
        menu.addAction(action)

    def _add_playlist_like_action(self, menu: QMenu, playlist: Playlist) -> None:
        action = QAction("Unlike" if playlist.is_liked else "Like", self)
        action.triggered.connect(
            lambda checked=False, selected_playlist=playlist: self._toggle_playlist_like(
                selected_playlist
            )
        )
        menu.addAction(action)

    def _toggle_album_like(self, album: Album) -> None:
        if album.is_liked:
            self._library_controller.unlike_album(album)
            return
        self._library_controller.like_album(album)

    def _toggle_artist_like(self, artist: Artist) -> None:
        if artist.is_liked:
            self._library_controller.unlike_artist(artist)
            return
        self._library_controller.like_artist(artist)

    def _toggle_playlist_like(self, playlist: Playlist) -> None:
        if playlist.is_liked:
            self._library_controller.unlike_playlist(playlist)
            return
        self._library_controller.like_playlist(playlist)

    def _add_copy_share_link_action(self, menu: QMenu, link: str | None) -> None:
        if not link:
            return
        action = QAction("Copy share link", self)
        action.triggered.connect(
            lambda checked=False, share_link=link: self._copy_share_link(share_link)
        )
        menu.addAction(action)

    def _add_track_radio_action(self, menu: QMenu, track: Track) -> None:
        action = QAction("Start track radio", self)
        action.triggered.connect(
            lambda checked=False, selected_track=track: self._open_and_play_station(
                Station(id=f"track:{selected_track.id}", title=f"{selected_track.title} Radio")
            )
        )
        menu.addAction(action)

    def _add_album_radio_action(self, menu: QMenu, album: Album) -> None:
        action = QAction("Start album radio", self)
        action.triggered.connect(
            lambda checked=False, selected_album=album: self._open_and_play_station(
                Station(id=f"album:{selected_album.id}", title=f"{selected_album.title} Radio")
            )
        )
        menu.addAction(action)

    def _add_artist_radio_action(self, menu: QMenu, artist: Artist) -> None:
        action = QAction("Start artist radio", self)
        action.triggered.connect(
            lambda checked=False, selected_artist=artist: self._open_and_play_station(
                Station(id=f"artist:{selected_artist.id}", title=f"{selected_artist.name} Radio")
            )
        )
        menu.addAction(action)

    def _add_go_to_artist_actions(
        self,
        menu: QMenu,
        artist_ids: tuple[str, ...],
        artist_names: tuple[str, ...],
    ) -> None:
        artists = [
            Artist(id=artist_id, name=artist_name)
            for artist_id, artist_name in zip(artist_ids, artist_names, strict=False)
        ]
        if not artists:
            return
        if len(artists) == 1:
            artist = artists[0]
            action = QAction("Go to artist", self)
            action.triggered.connect(
                lambda checked=False, selected_artist=artist: self._library_controller.open_artist(
                    selected_artist
                )
            )
            menu.addAction(action)
            return
        submenu = menu.addMenu("Go to artist")
        for artist in artists:
            action = QAction(artist.name, self)
            action.triggered.connect(
                lambda checked=False, selected_artist=artist: self._library_controller.open_artist(
                    selected_artist
                )
            )
            submenu.addAction(action)

    def _open_and_play_station(self, station: Station) -> None:
        self._controller.play_station(station.id)

    def _copy_share_link(self, link: str) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(link)
        self._status_label.setText(f"Copied share link: {link}")

    def _track_share_link(self, track: Track) -> str | None:
        if track.album_id:
            return f"https://music.yandex.ru/album/{track.album_id}/track/{track.id}"
        return None

    def _album_share_link(self, album: Album) -> str:
        return f"https://music.yandex.ru/album/{album.id}"

    def _artist_share_link(self, artist: Artist) -> str:
        return f"https://music.yandex.ru/artist/{artist.id}"

    def _playlist_share_link(self, playlist: Playlist) -> str | None:
        if playlist.owner_id:
            return f"https://music.yandex.ru/users/{playlist.owner_id}/playlists/{playlist.id}"
        return f"https://music.yandex.ru/playlist/{playlist.id}"

    def _station_share_link(self, station: Station) -> str | None:
        if station.id.startswith("artist:"):
            return f"https://music.yandex.ru/artist/{station.id.split(':', 1)[1]}"
        if station.id.startswith("album:"):
            return f"https://music.yandex.ru/album/{station.id.split(':', 1)[1]}"
        if station.id.startswith("track:"):
            return None
        return None
