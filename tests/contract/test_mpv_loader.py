from __future__ import annotations

import os

import pytest

from app.infrastructure.playback.mpv_loader import ensure_mpv_available

pytestmark = pytest.mark.skipif(
    os.getenv("YAYMP_ENABLE_MPV_TESTS") != "1",
    reason="MPV availability checks are enabled only in environments that provide libmpv.",
)


def test_mpv_loader_resolves_python_binding_and_system_library() -> None:
    module, library_path = ensure_mpv_available()

    assert module is not None
    assert hasattr(module, "MPV")
    assert library_path
