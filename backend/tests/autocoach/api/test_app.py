"""Tests for the AutoCoach v0 FastAPI application."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from autocoach.api.app import MAX_DURATION_SECONDS, MAX_UPLOAD_BYTES, create_app
from autocoach.config import AppConfig
from autocoach.pose.extractor import PoseExtractionError
from autocoach.pose.models import BiomechanicalFeatures
from autocoach.pose.pipeline import PipelineError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_pipeline():
    """A PosePipeline mock that returns realistic BiomechanicalFeatures."""
    pipeline = MagicMock()
    pipeline.process.return_value = BiomechanicalFeatures(
        video_id="test123",
        lift_type="Squat",
        knee_angles=[120.0, 100.0, 85.0, 100.0, 120.0],
        hip_angles=[130.0, 90.0, 75.0, 90.0, 130.0],
        back_angles=[10.0, 25.0, 35.0, 25.0, 10.0],
        min_knee_angle=85.0,
        min_hip_angle=75.0,
        max_back_angle=35.0,
        phase_labels=["descent", "descent", "bottom", "ascent", "ascent"],
        view_confidence=0.85,
        dominant_side="left",
    )
    return pipeline


@pytest.fixture()
def app_config(tmp_path):
    """Config pointing blob storage at a temp directory."""
    return AppConfig(blob_storage_root=str(tmp_path / "blobs"))


@pytest.fixture()
def client(app_config, mock_pipeline):
    """Test client with mocked pipeline."""
    app = create_app(config=app_config, pipeline=mock_pipeline)
    return TestClient(app)


def _make_video_upload(content: bytes = b"\x00" * 1024, filename: str = "squat.mp4") -> dict:
    """Create a fake video file for upload."""
    return {"file": (filename, io.BytesIO(content), "video/mp4")}


# ---------------------------------------------------------------------------
# Upload page
# ---------------------------------------------------------------------------


class TestUploadPage:
    def test_get_returns_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_contains_upload_form(self, client):
        resp = client.get("/")
        assert 'action="/upload"' in resp.text
        assert 'enctype="multipart/form-data"' in resp.text

    def test_contains_design_elements(self, client):
        resp = client.get("/")
        assert "// SQUAT ANALYSIS" in resp.text
        assert "Film your squat" in resp.text
        assert "Analyze My Form" in resp.text

    def test_contains_camera_capture(self, client):
        resp = client.get("/")
        assert 'capture="environment"' in resp.text

    def test_contains_loading_overlay(self, client):
        resp = client.get("/")
        assert "loading-overlay" in resp.text
        assert "// EXTRACTING POSE" in resp.text


# ---------------------------------------------------------------------------
# Video validation
# ---------------------------------------------------------------------------


class TestVideoValidation:
    def test_rejects_non_video_mime(self, client):
        files = {"file": ("doc.pdf", io.BytesIO(b"fake"), "application/pdf")}
        resp = client.post("/upload", files=files)
        assert resp.status_code == 400
        assert "Invalid file type" in resp.text

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_accepts_small_video(self, _mock_dur, client, mock_pipeline):
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 200
        assert "// RESULTS" in resp.text
        mock_pipeline.process.assert_called_once()

    def test_rejects_oversized_upload(self, client):
        # Create content just over the limit
        big_content = b"\x00" * (MAX_UPLOAD_BYTES + 1)
        files = {"file": ("big.mp4", io.BytesIO(big_content), "video/mp4")}
        resp = client.post("/upload", files=files)
        assert resp.status_code == 400
        assert "File too large" in resp.text

    @patch("autocoach.api.app._video_duration_seconds", return_value=45.0)
    def test_rejects_long_video(self, _mock_dur, client):
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 400
        assert "Video too long" in resp.text
        assert str(MAX_DURATION_SECONDS) in resp.text


# ---------------------------------------------------------------------------
# Pipeline results
# ---------------------------------------------------------------------------


class TestResultsPage:
    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_shows_angles(self, _mock_dur, client):
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 200
        assert "85.0°" in resp.text  # min_knee_angle
        assert "75.0°" in resp.text  # min_hip_angle
        assert "35.0°" in resp.text  # max_back_angle

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_shows_view_confidence(self, _mock_dur, client):
        resp = client.post("/upload", files=_make_video_upload())
        assert "85%" in resp.text  # view_confidence 0.85 → 85%

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_shows_phases(self, _mock_dur, client):
        resp = client.post("/upload", files=_make_video_upload())
        assert "descent" in resp.text
        assert "bottom" in resp.text
        assert "ascent" in resp.text

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_shows_analyze_another_link(self, _mock_dur, client):
        resp = client.post("/upload", files=_make_video_upload())
        assert "Analyze Another" in resp.text


# ---------------------------------------------------------------------------
# Blob storage
# ---------------------------------------------------------------------------


class TestBlobIntegration:
    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_video_persisted_to_blob(self, _mock_dur, client, app_config):
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 200
        # Check that a video file was written to blob storage
        blob_root = Path(app_config.blob_storage_root)
        video_files = list(blob_root.glob("videos/*.mp4"))
        assert len(video_files) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_pipeline_error_front_view(self, _mock_dur, client, mock_pipeline):
        mock_pipeline.process.side_effect = PipelineError(
            "Video rejected: camera angle is too frontal"
        )
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 400
        assert "Wrong camera angle" in resp.text
        assert "Re-film from the side" in resp.text

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_pipeline_error_phase_detection(self, _mock_dur, client, mock_pipeline):
        mock_pipeline.process.side_effect = PipelineError("Phase detection failed: too short")
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 400
        assert "Processing failed" in resp.text

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_pose_extraction_error(self, _mock_dur, client, mock_pipeline):
        mock_pipeline.process.side_effect = PoseExtractionError("No landmarks detected")
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 400
        assert "Could not process video" in resp.text

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_unexpected_error(self, _mock_dur, client, mock_pipeline):
        mock_pipeline.process.side_effect = RuntimeError("something unexpected")
        resp = client.post("/upload", files=_make_video_upload())
        assert resp.status_code == 500
        assert "Something went wrong" in resp.text

    def test_error_page_has_try_again(self, client):
        files = {"file": ("doc.pdf", io.BytesIO(b"fake"), "application/pdf")}
        resp = client.post("/upload", files=files)
        assert "Try Again" in resp.text

    @patch("autocoach.api.app._video_duration_seconds", return_value=5.0)
    def test_error_page_shows_help_for_camera_errors(self, _mock_dur, client, mock_pipeline):
        mock_pipeline.process.side_effect = PipelineError(
            "Video rejected: camera angle is too frontal"
        )
        resp = client.post("/upload", files=_make_video_upload())
        assert "full body in frame" in resp.text


# ---------------------------------------------------------------------------
# Design system compliance
# ---------------------------------------------------------------------------


class TestDesignSystem:
    def test_uses_geist_mono(self, client):
        resp = client.get("/")
        assert "Geist+Mono" in resp.text or "Geist Mono" in resp.text

    def test_uses_instrument_serif(self, client):
        resp = client.get("/")
        assert "Instrument+Serif" in resp.text or "Instrument Serif" in resp.text

    def test_dark_mode_background(self, client):
        resp = client.get("/")
        assert "#111110" in resp.text

    def test_accent_color(self, client):
        resp = client.get("/")
        assert "#E85D3A" in resp.text
