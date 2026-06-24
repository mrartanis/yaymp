from __future__ import annotations

from app.domain import Artist, Track
from app.presentation.qt.preference_markers import preference_marker_kind


def test_preference_marker_kind_for_track() -> None:
    assert (
        preference_marker_kind(Track(id="1", title="T", artists=("A",), is_liked=True))
        == "liked"
    )
    assert (
        preference_marker_kind(
            Track(id="1", title="T", artists=("A",), is_liked=True, is_disliked=True)
        )
        == "disliked"
    )
    assert preference_marker_kind(Track(id="1", title="T", artists=("A",))) is None


def test_preference_marker_kind_for_artist() -> None:
    assert preference_marker_kind(Artist(id="1", name="A", is_liked=True)) == "liked"
    assert (
        preference_marker_kind(Artist(id="1", name="A", is_liked=True, is_disliked=True))
        == "disliked"
    )
    assert preference_marker_kind(Artist(id="1", name="A")) is None


def test_preference_marker_kind_ignores_other_payloads() -> None:
    assert preference_marker_kind(object()) is None
