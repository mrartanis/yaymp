from __future__ import annotations

import os
import sys
from ctypes.util import find_library
from importlib import import_module
from pathlib import Path

from app.domain.errors import PlaybackBackendError


def _candidate_runtime_roots() -> list[Path]:
    roots: list[Path] = []
    executable = Path(sys.executable).resolve()
    roots.append(executable.parent)

    if sys.platform == "darwin":
        # Nuitka app bundles place the executable in Contents/MacOS.
        contents_dir = executable.parent.parent
        if contents_dir.name == "Contents":
            roots.append(contents_dir)
            roots.append(contents_dir / "Resources")
            roots.append(contents_dir / "Frameworks")

    return roots


def _candidate_library_names() -> tuple[str, ...]:
    if sys.platform == "darwin":
        return ("libmpv.2.dylib", "libmpv.dylib")
    if sys.platform.startswith("linux"):
        return ("libmpv.so.2", "libmpv.so")
    if sys.platform == "win32":
        return ("mpv-2.dll", "mpv-1.dll", "libmpv-2.dll", "libmpv.dll")
    return ("libmpv",)


def _resolve_bundled_mpv_library() -> str | None:
    relative_dirs = (
        Path("."),
        Path("lib"),
        Path("Frameworks"),
        Path("Resources") / "lib",
    )
    for root in _candidate_runtime_roots():
        for relative_dir in relative_dirs:
            for library_name in _candidate_library_names():
                candidate = root / relative_dir / library_name
                if candidate.exists():
                    return str(candidate)
    return None


def resolve_mpv_library_path() -> str | None:
    bundled = _resolve_bundled_mpv_library()
    if bundled:
        return bundled
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
