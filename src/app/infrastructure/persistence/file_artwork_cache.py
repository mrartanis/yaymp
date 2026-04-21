from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from app.domain.errors import StorageError


class FileArtworkCache:
    def __init__(self, *, cache_dir: Path) -> None:
        self._cache_dir = cache_dir

    def normalize_url(self, artwork_ref: str) -> str | None:
        value = artwork_ref.strip()
        if not value:
            return None
        if value.startswith("http://") or value.startswith("https://"):
            return value.replace("%%", "200x200")
        if value.startswith("//"):
            return f"https:{value}".replace("%%", "200x200")
        return f"https://{value}".replace("%%", "200x200")

    def cache_path_for_url(self, artwork_url: str) -> Path:
        digest = sha256(artwork_url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.img"

    def save_bytes(self, path: Path, data: bytes) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError("Failed to save artwork cache file") from exc
