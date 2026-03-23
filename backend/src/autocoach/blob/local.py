"""Local filesystem blob storage backend.

Stores blobs as plain files under a configurable root directory.
Intended for development and testing — production uses S3BlobStorage.

File layout:
  {root}/
    videos/
      {video_id}.mp4
    keyframes/
      {video_id}/
        frame_042.png
"""

from __future__ import annotations

import shutil
from pathlib import Path

from autocoach.blob.exceptions import BlobNotFoundError


def _validate_key(key: str) -> None:
    """Reject empty keys, absolute paths, and path traversal attempts."""
    if not key or not key.strip():
        raise ValueError("Blob key must not be empty")
    if key.startswith("/"):
        raise ValueError(f"Blob key must be relative, got absolute path: {key!r}")
    if ".." in key.split("/"):
        raise ValueError(f"Blob key contains path traversal: {key!r}")


class LocalBlobStorage:
    """Filesystem-backed blob storage for development.

    Args:
        root: Base directory for all stored blobs.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def upload(self, key: str, data: bytes | Path) -> None:
        """Store *data* under *key*, creating parent directories as needed."""
        _validate_key(key)
        dest = self._root / key
        dest.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, Path):
            shutil.copy2(data, dest)
        else:
            dest.write_bytes(data)

    def download(self, key: str) -> bytes:
        """Return raw bytes for *key*, or raise BlobNotFoundError."""
        _validate_key(key)
        path = self._root / key
        if not path.is_file():
            raise BlobNotFoundError(key)
        return path.read_bytes()

    def get_url(self, key: str) -> str:
        """Return the absolute file path as a string."""
        _validate_key(key)
        return str(self._root / key)
