from __future__ import annotations

import pytest

from app.application.track_metadata import classify_track_ai_usage
from app.domain import TrackAiUsage, TrackCredit


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
