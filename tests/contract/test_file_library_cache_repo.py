from __future__ import annotations

import pytest

from app.domain import StorageError
from app.infrastructure.persistence.file_library_cache_repo import FileLibraryCacheRepo


def test_file_library_cache_repo_round_trips_recent_searches(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "recent.json")

    repo.save_recent_searches(("ambient", "jazz"))

    assert repo.load_recent_searches() == ("ambient", "jazz")


def test_file_library_cache_repo_returns_empty_when_missing(tmp_path) -> None:
    repo = FileLibraryCacheRepo(file_path=tmp_path / "missing.json")

    assert repo.load_recent_searches() == ()


def test_file_library_cache_repo_rejects_invalid_payload(tmp_path) -> None:
    path = tmp_path / "recent.json"
    path.write_text('{"bad": true}', encoding="utf-8")
    repo = FileLibraryCacheRepo(file_path=path)

    with pytest.raises(StorageError):
        repo.load_recent_searches()
