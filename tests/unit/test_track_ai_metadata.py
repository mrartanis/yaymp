from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.track_metadata import classify_track_ai_usage, track_credits_are_fresh
from app.domain import Track, TrackAiUsage, TrackCredit


@pytest.mark.parametrize(
    ("title", "value", "expected"),
    [
        (
            "Использование ИИ",
            "Трек полностью создан с использованием ИИ",
            TrackAiUsage.FULL,
        ),
        ("Использование ИИ", "Трек создан с помощью ИИ", TrackAiUsage.FULL),
        (
            "Использование ИИ",
            "Трек частично создан с использованием ИИ",
            TrackAiUsage.PARTIAL,
        ),
        (
            "Использование ИИ",
            "Возможно, трек создан с использованием ИИ",
            TrackAiUsage.POSSIBLE,
        ),
        ("AI use", "The track was fully created using AI", TrackAiUsage.FULL),
        ("AI use", "The track was partially created using AI", TrackAiUsage.PARTIAL),
        (
            "AI use",
            "The track may have been created with the help of AI",
            TrackAiUsage.POSSIBLE,
        ),
    ],
)
def test_classify_track_ai_usage(
    title: str,
    value: str,
    expected: TrackAiUsage,
) -> None:
    assert classify_track_ai_usage((TrackCredit(title=title, value=value),)) is expected


def test_classify_track_ai_usage_ignores_unknown_marking() -> None:
    assert (
        classify_track_ai_usage((TrackCredit(title="AI use", value="Unknown value"),))
        is None
    )


def test_track_credits_cache_is_scoped_to_api_language() -> None:
    track = Track(
        id="track-1",
        title="Track",
        artists=("Artist",),
        credits_cached_at=datetime.now(tz=UTC),
        credits_language="ru",
    )

    assert track_credits_are_fresh(track, language="ru")
    assert not track_credits_are_fresh(track, language="en")
