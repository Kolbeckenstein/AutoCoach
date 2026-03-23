"""Tests for LocalBlobStorage.

LocalBlobStorage is the dev/test filesystem backend for blob storage.
It writes files under a configurable root directory, creating parent
directories as needed.

All tests use pytest's tmp_path fixture — no external services required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autocoach.blob.exceptions import BlobNotFoundError
from autocoach.blob.local import LocalBlobStorage

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage(tmp_path: Path) -> LocalBlobStorage:
    """A LocalBlobStorage rooted in a temp directory."""
    return LocalBlobStorage(root=tmp_path)


# ---------------------------------------------------------------------------
# upload + download roundtrip
# ---------------------------------------------------------------------------


class TestUploadDownloadRoundtrip:
    """Core contract: upload bytes or a Path, download gets them back."""

    def test_upload_bytes_and_download(self, storage: LocalBlobStorage) -> None:
        data = b"hello blob"
        storage.upload("test.bin", data)
        assert storage.download("test.bin") == data

    def test_upload_from_path(self, storage: LocalBlobStorage, tmp_path: Path) -> None:
        source = tmp_path / "source_video.mp4"
        source.write_bytes(b"fake video content")

        storage.upload("videos/v1.mp4", source)
        assert storage.download("videos/v1.mp4") == b"fake video content"

    def test_roundtrip_empty_bytes(self, storage: LocalBlobStorage) -> None:
        storage.upload("empty.bin", b"")
        assert storage.download("empty.bin") == b""

    def test_roundtrip_large_data(self, storage: LocalBlobStorage) -> None:
        data = bytes(range(256)) * 4096  # ~1MB
        storage.upload("large.bin", data)
        assert storage.download("large.bin") == data


# ---------------------------------------------------------------------------
# Nested keys and directory creation
# ---------------------------------------------------------------------------


class TestNestedKeys:
    """Keys with slashes should create intermediate directories."""

    def test_nested_key_creates_parents(self, storage: LocalBlobStorage) -> None:
        storage.upload("a/b/c/deep.png", b"pixel data")
        assert storage.download("a/b/c/deep.png") == b"pixel data"


# ---------------------------------------------------------------------------
# Overwrite behavior
# ---------------------------------------------------------------------------


class TestOverwrite:
    """Uploading the same key twice should overwrite silently."""

    def test_overwrite_replaces_content(self, storage: LocalBlobStorage) -> None:
        storage.upload("file.txt", b"version 1")
        storage.upload("file.txt", b"version 2")
        assert storage.download("file.txt") == b"version 2"


# ---------------------------------------------------------------------------
# Download errors
# ---------------------------------------------------------------------------


class TestDownloadErrors:
    """download() raises BlobNotFoundError for missing keys."""

    def test_download_missing_key(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(BlobNotFoundError, match="nonexistent"):
            storage.download("nonexistent")

    def test_error_contains_key(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(BlobNotFoundError) as exc_info:
            storage.download("missing/key.bin")
        assert exc_info.value.key == "missing/key.bin"


# ---------------------------------------------------------------------------
# get_url
# ---------------------------------------------------------------------------


class TestGetUrl:
    """get_url() returns the absolute file path for local storage."""

    def test_get_url_returns_path(self, storage: LocalBlobStorage, tmp_path: Path) -> None:
        storage.upload("img.png", b"pixels")
        url = storage.get_url("img.png")
        assert str(tmp_path) in url
        assert "img.png" in url


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Reject empty keys and path traversal attempts."""

    def test_empty_key_rejected(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(ValueError, match="empty"):
            storage.upload("", b"data")

    def test_path_traversal_rejected(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(ValueError, match="traversal"):
            storage.upload("../escape.txt", b"data")

    def test_path_traversal_mid_key_rejected(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(ValueError, match="traversal"):
            storage.upload("a/../../escape.txt", b"data")

    def test_absolute_path_rejected(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(ValueError, match="absolute"):
            storage.upload("/etc/passwd", b"data")

    def test_download_absolute_path_rejected(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(ValueError, match="absolute"):
            storage.download("/etc/passwd")

    def test_download_empty_key_rejected(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(ValueError, match="empty"):
            storage.download("")

    def test_download_traversal_rejected(self, storage: LocalBlobStorage) -> None:
        with pytest.raises(ValueError, match="traversal"):
            storage.download("../etc/passwd")
