from app.application.playback_service import PlaybackService
from app.domain import PlaybackStatus, RepeatMode, Track
from app.infrastructure.playback.fake_playback_engine import FakePlaybackEngine


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


def build_tracks() -> tuple[Track, ...]:
    return (
        Track(id="one", title="One", artists=("Artist",), duration_ms=120_000, stream_ref="demo://one"),
        Track(id="two", title="Two", artists=("Artist",), duration_ms=180_000, stream_ref="demo://two"),
        Track(id="three", title="Three", artists=("Artist",), duration_ms=240_000, stream_ref="demo://three"),
    )


def test_replace_queue_and_play_from_index() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )

    snapshot = service.replace_queue(build_tracks(), start_index=1, source_type="test")

    assert snapshot.state.status is PlaybackStatus.PLAYING
    assert snapshot.state.active_index == 1
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "two"
    assert len(snapshot.queue) == 3


def test_next_and_previous_move_inside_queue() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=1, source_type="test")

    next_snapshot = service.next()
    previous_snapshot = service.previous()

    assert next_snapshot.state.active_index == 2
    assert previous_snapshot.state.active_index == 1


def test_repeat_all_wraps_queue_edges() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=2, source_type="test")
    service.set_repeat_mode(RepeatMode.ALL)

    snapshot = service.next()

    assert snapshot.state.active_index == 0
    assert snapshot.current_item is not None
    assert snapshot.current_item.track.id == "one"


def test_seek_and_volume_are_reflected_in_snapshot() -> None:
    service = PlaybackService(
        playback_engine=FakePlaybackEngine(),
        logger=TestLogger(),
    )
    service.replace_queue(build_tracks(), start_index=0, source_type="test")

    service.seek(45_000)
    snapshot = service.set_volume(33)

    assert snapshot.state.position_ms == 45_000
    assert snapshot.state.volume == 33
