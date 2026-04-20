from __future__ import annotations

import json
from pathlib import Path

from app.domain import LibraryCacheRepo
from app.domain.errors import StorageError


class FileLibraryCacheRepo(LibraryCacheRepo):
    def __init__(self, *, file_path: Path) -> None:
        self._file_path = file_path

    def load_recent_searches(self) -> tuple[str, ...]:
        if not self._file_path.exists():
            return ()
        try:
            payload = json.loads(self._file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError("Failed to load library cache") from exc
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise StorageError("Library cache file is invalid")
        return tuple(payload)

    def save_recent_searches(self, searches: tuple[str, ...] | list[str]) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._file_path.write_text(
                json.dumps(list(searches), indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
        except OSError as exc:
            raise StorageError("Failed to save library cache") from exc
