"""Video downloader using streaming HTTP."""

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


class VideoDownloader:
    """Downloads videos to the local filesystem via streaming HTTP."""

    def __init__(self, chunk_size: int = 8192) -> None:
        self._chunk_size = chunk_size

    def download(self, url: str, dest: Path) -> Path | None:
        """Download a video from url to dest.

        Skips the download if dest already exists. Creates parent directories
        as needed. Returns None (without raising) on any network or HTTP error
        so the caller can continue processing other posts.

        Args:
            url: Direct video URL.
            dest: Destination path for the downloaded file.

        Returns:
            dest on success, None on failure.
        """
        if dest.exists():
            logger.debug("Video already exists at %s, skipping download", dest)
            return dest

        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            with httpx.stream("GET", url) as response:
                response.raise_for_status()
                with dest.open("wb") as fh:
                    for chunk in response.iter_bytes(self._chunk_size):
                        fh.write(chunk)
        except httpx.HTTPStatusError as exc:
            logger.warning("HTTP %s downloading %s: %s", exc.response.status_code, url, exc)
            self._cleanup(dest)
            return None
        except httpx.HTTPError as exc:
            logger.warning("Network error downloading %s: %s", url, exc)
            self._cleanup(dest)
            return None

        logger.debug("Downloaded %s → %s", url, dest)
        return dest

    @staticmethod
    def _cleanup(path: Path) -> None:
        """Remove a partial download."""
        if path.exists():
            path.unlink()
