from __future__ import annotations

import os
from ctypes.util import find_library
from importlib import import_module

from app.domain.errors import PlaybackBackendError


def resolve_mpv_library_path() -> str | None:
    override = os.getenv("YAYMP_MPV_LIBRARY")
    if override:
        return override
    return find_library("mpv")


def load_mpv_module():
    try:
        return import_module("mpv")
    except ModuleNotFoundError as exc:
        raise PlaybackBackendError("python-mpv is not installed") from exc


def ensure_mpv_available() -> tuple[object, str]:
    library_path = resolve_mpv_library_path()
    if library_path is None:
        raise PlaybackBackendError("libmpv could not be resolved")
    module = load_mpv_module()
    return module, library_path
