"""BlobStorage protocol — the contract all storage backends implement.

Consumers (api/, worker/, overlay/) depend on this protocol, never on
a concrete backend. Swap LocalBlobStorage for S3BlobStorage by changing
one line of config.

Data flow:
  caller ──upload(key, data)──▶ BlobStorage ──▶ backend (local / S3)
  caller ◀──download(key)───── BlobStorage ◀── backend
  caller ◀──get_url(key)────── BlobStorage ◀── backend
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class BlobStorage(Protocol):
    """Storage backend for videos and keyframe images."""

    def upload(self, key: str, data: bytes | Path) -> None:
        """Store *data* under *key*, creating or overwriting.

        Args:
            key: Opaque storage key (e.g. ``videos/{id}.mp4``).
            data: Raw bytes or a local file path to copy from.

        Raises:
            ValueError: If *key* is empty or contains path traversal.
        """
        ...

    def download(self, key: str) -> bytes:
        """Return the raw bytes stored under *key*.

        Raises:
            BlobNotFoundError: If *key* does not exist.
        """
        ...

    def get_url(self, key: str) -> str:
        """Return a URL or path string where *key* can be accessed.

        For local storage this is an absolute filesystem path.
        For S3 this would be a presigned URL.
        """
        ...
