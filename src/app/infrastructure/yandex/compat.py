from __future__ import annotations

from functools import wraps
from typing import Any


def apply_optional_user_login_backport() -> None:
    """Backport MarshalX/yandex-music-api#733 until it is released."""
    from yandex_music import User

    if getattr(User, "_yaymp_optional_login_backport", False):
        return

    try:
        User(uid=0)
    except TypeError:
        pass
    else:
        return

    original_init = User.__init__

    @wraps(original_init)
    def init_with_optional_login(
        self: Any,
        uid: int,
        login: str | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        original_init(self, uid, login, *args, **kwargs)

    def identify_by_uid(self: Any) -> None:
        self._id_attrs = (self.uid,)

    User.__init__ = init_with_optional_login
    User.__post_init__ = identify_by_uid
    User._yaymp_optional_login_backport = True
