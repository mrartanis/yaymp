from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AuthSession:
    user_id: str
    token: str
    expires_at: datetime | None = None
    display_name: str | None = None
