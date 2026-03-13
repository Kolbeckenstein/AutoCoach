"""Unit tests for the video downloader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from autocoach.scrapers.reddit.downloader import VideoDownloader

pytestmark = pytest.mark.unit


class TestVideoDownloader:
    """Tests for VideoDownloader."""

    def test_downloads_file_to_dest_path(self, tmp_path: Path) -> None:
        dest = tmp_path / "videos" / "squat" / "abc123.mp4"
        fake_content = b"fake video bytes"

        with patch("httpx.stream") as mock_stream:
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.raise_for_status = MagicMock()
            mock_response.iter_bytes.return_value = [fake_content]
            mock_stream.return_value = mock_response

            downloader = VideoDownloader()
            result = downloader.download("https://v.redd.it/abc/DASH_720.mp4", dest)

        assert result == dest
        assert dest.exists()
        assert dest.read_bytes() == fake_content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        dest = tmp_path / "deep" / "nested" / "dir" / "video.mp4"
        fake_content = b"bytes"

        with patch("httpx.stream") as mock_stream:
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.raise_for_status = MagicMock()
            mock_response.iter_bytes.return_value = [fake_content]
            mock_stream.return_value = mock_response

            downloader = VideoDownloader()
            downloader.download("https://v.redd.it/abc/DASH_720.mp4", dest)

        assert dest.parent.exists()

    def test_returns_none_on_http_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "video.mp4"

        with patch("httpx.stream") as mock_stream:
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            )
            mock_stream.return_value = mock_response

            downloader = VideoDownloader()
            result = downloader.download("https://v.redd.it/dead/DASH_720.mp4", dest)

        assert result is None
        assert not dest.exists()

    def test_returns_none_on_network_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "video.mp4"

        with patch("httpx.stream") as mock_stream:
            mock_stream.side_effect = httpx.ConnectError("Connection refused")

            downloader = VideoDownloader()
            result = downloader.download("https://v.redd.it/abc/DASH_720.mp4", dest)

        assert result is None

    def test_skips_download_if_file_already_exists(self, tmp_path: Path) -> None:
        dest = tmp_path / "video.mp4"
        dest.write_bytes(b"already downloaded")

        with patch("httpx.stream") as mock_stream:
            downloader = VideoDownloader()
            result = downloader.download("https://v.redd.it/abc/DASH_720.mp4", dest)

        mock_stream.assert_not_called()
        assert result == dest

    def test_streams_in_chunks(self, tmp_path: Path) -> None:
        """Verifies iter_bytes is used (streaming, not loading all into memory)."""
        dest = tmp_path / "video.mp4"
        chunks = [b"chunk1", b"chunk2", b"chunk3"]

        with patch("httpx.stream") as mock_stream:
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.raise_for_status = MagicMock()
            mock_response.iter_bytes.return_value = chunks
            mock_stream.return_value = mock_response

            downloader = VideoDownloader()
            downloader.download("https://v.redd.it/abc/DASH_720.mp4", dest)

        mock_response.iter_bytes.assert_called_once()
        assert dest.read_bytes() == b"chunk1chunk2chunk3"

    def test_uses_get_method(self, tmp_path: Path) -> None:
        dest = tmp_path / "video.mp4"

        with patch("httpx.stream") as mock_stream:
            mock_response = MagicMock()
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            mock_response.raise_for_status = MagicMock()
            mock_response.iter_bytes.return_value = [b"data"]
            mock_stream.return_value = mock_response

            downloader = VideoDownloader()
            downloader.download("https://v.redd.it/abc/DASH_720.mp4", dest)

        call_args = mock_stream.call_args
        assert call_args[0][0] == "GET"
