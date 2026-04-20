from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    title: str
    description: str | None = None
    icon_ref: str | None = None
