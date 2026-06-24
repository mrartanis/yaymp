from __future__ import annotations

from typing import Literal

from app.domain import Artist, Track

PreferenceMarkerKind = Literal["liked", "disliked"]


def preference_marker_kind(payload: object) -> PreferenceMarkerKind | None:
    if isinstance(payload, Track):
        if payload.is_disliked:
            return "disliked"
        if payload.is_liked:
            return "liked"
        return None
    if isinstance(payload, Artist):
        if payload.is_disliked:
            return "disliked"
        if payload.is_liked:
            return "liked"
        return None
    return None


def preference_marker_icon_name(
    marker_kind: PreferenceMarkerKind,
    *,
    theme_mode: str,
) -> str:
    if marker_kind == "liked":
        return "heart_dark_outline.svg" if theme_mode == "light" else "heart.svg"
    return "heart_slash.svg"
