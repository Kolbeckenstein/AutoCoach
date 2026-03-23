"""Blob storage exceptions."""


class BlobNotFoundError(Exception):
    """Raised when a requested blob key does not exist in storage."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Blob not found: {key}")
