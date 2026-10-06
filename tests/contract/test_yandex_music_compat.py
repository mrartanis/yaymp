from yandex_music import User

from app.infrastructure.yandex.compat import apply_optional_user_login_backport


def test_user_login_is_optional() -> None:
    apply_optional_user_login_backport()

    user = User.de_json({"uid": 42}, client=None)

    assert user is not None
    assert user.login is None


def test_user_identity_does_not_depend_on_login() -> None:
    apply_optional_user_login_backport()

    assert User(uid=42, login="listener") == User(uid=42)
    assert hash(User(uid=42, login="listener")) == hash(User(uid=42))
