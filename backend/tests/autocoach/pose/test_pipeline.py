"""Tests for PosePipeline.

The pipeline is the single entry point for all pose processing.  These tests
verify the orchestration logic — that the right data flows between stages and
that errors from individual stages are handled or propagated correctly.

PoseExtractor.extract is mocked in all unit tests so that no model file is
required.  The downstream stages (ViewClassifier, PhaseDetector, Normalizer,
BiomechanicsExtractor) run for real against canned PoseSequences so that
integration between those modules is exercised.

Key pipeline invariants tested:
- FRONT_VIEW videos are rejected by default (bad camera angle → bad angles)
- view_confidence from ViewClassifier is stored on BiomechanicalFeatures
- dominant_side from ViewClassifier controls which landmarks BiomechanicsExtractor reads
- PoseExtractionError bubbles up unchanged (it carries a user-actionable message)
- PipelineError wraps PhaseDetector ValueError so callers see a consistent type
- video_id defaults to the video file stem when not supplied
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from autocoach.pose.extractor import PoseExtractionError
from autocoach.pose.models import Frame, PoseSequence

pytestmark = pytest.mark.unit

# MediaPipe landmark indices used in helpers
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28


# ---------------------------------------------------------------------------
# Sequence builders
# ---------------------------------------------------------------------------


def _make_frame(
    idx: int,
    left_hip_x: float = 0.50,
    right_hip_x: float = 0.51,
    hip_y: float = 0.50,
    knee_y: float = 0.60,
    shoulder_y: float = 0.20,
    left_vis: float = 0.9,
    right_vis: float = 0.9,
) -> Frame:
    """Build a single Frame with controllable geometry."""
    lm = np.zeros((33, 4), dtype=np.float32)
    lm[:, 3] = 0.9  # default visibility

    lm[LEFT_HIP, 0] = left_hip_x
    lm[LEFT_HIP, 1] = hip_y
    lm[LEFT_HIP, 3] = left_vis
    lm[RIGHT_HIP, 0] = right_hip_x
    lm[RIGHT_HIP, 1] = hip_y
    lm[RIGHT_HIP, 3] = right_vis
    lm[LEFT_SHOULDER, 0] = left_hip_x
    lm[LEFT_SHOULDER, 1] = shoulder_y
    lm[RIGHT_SHOULDER, 0] = right_hip_x
    lm[RIGHT_SHOULDER, 1] = shoulder_y
    lm[LEFT_KNEE, 0] = left_hip_x
    lm[LEFT_KNEE, 1] = knee_y
    lm[RIGHT_KNEE, 0] = right_hip_x
    lm[RIGHT_KNEE, 1] = knee_y
    lm[LEFT_ANKLE, 0] = left_hip_x
    lm[LEFT_ANKLE, 1] = 0.85
    lm[RIGHT_ANKLE, 0] = right_hip_x
    lm[RIGHT_ANKLE, 1] = 0.85
    return Frame(index=idx, timestamp=float(idx) / 30, landmarks=lm)


def _make_side_view_squat(n: int = 30) -> PoseSequence:
    """Return a PoseSequence that passes through the full pipeline.

    Geometry:
    - Small lateral spread (side view): left_hip_x≈right_hip_x
    - Squat depth curve: hip_y increases in the middle (hip descends, depth_ratio peaks)
    - torso_height = hip_y - shoulder_y = 0.3 → normalised spread ≈ 0.033 < SIDE_THRESHOLD
    - Enough frames for PhaseDetector (n ≥ MIN_FRAMES=10)
    """
    frames = []
    t = np.linspace(0, np.pi, n)
    # hip_y: starts at 0.50 (standing), peaks at 0.65 (bottom), returns to 0.50
    hip_y_curve = 0.50 + 0.15 * np.sin(t)
    for i in range(n):
        frames.append(_make_frame(i, hip_y=float(hip_y_curve[i])))
    return PoseSequence(video_id="test_v", lift_type="Squat", frames=frames)


def _make_front_view_sequence(n: int = 15) -> PoseSequence:
    """Wide lateral spread → ViewClassifier returns FRONT_VIEW."""
    frames = [_make_frame(i, left_hip_x=0.28, right_hip_x=0.72) for i in range(n)]
    return PoseSequence(video_id="front_v", lift_type="Squat", frames=frames)


def _make_short_sequence(n: int = 5) -> PoseSequence:
    """Fewer frames than PhaseDetector.MIN_FRAMES=10 — triggers ValueError."""
    frames = [_make_frame(i) for i in range(n)]
    return PoseSequence(video_id="short_v", lift_type="Squat", frames=frames)


# ---------------------------------------------------------------------------
# View angle rejection
# ---------------------------------------------------------------------------


class TestViewRejection:
    def test_front_view_raises_pipeline_error_by_default(self, tmp_path: Path) -> None:
        """FRONT_VIEW camera angle makes every joint angle geometrically meaningless.

        The pipeline must refuse to produce features from a front-facing video
        rather than return plausible-looking but wrong angles that would corrupt
        coaching feedback.
        """
        from autocoach.pose.pipeline import PipelineError, PosePipeline

        seq = _make_front_view_sequence()
        pipeline = PosePipeline(reject_front_view=True)

        with (
            patch.object(pipeline._extractor, "extract", return_value=seq),
            pytest.raises(PipelineError, match="frontal"),
        ):
            pipeline.process(tmp_path / "v.mp4")

    def test_front_view_allowed_when_flag_set(self, tmp_path: Path) -> None:
        """reject_front_view=False lets callers process oblique footage deliberately.

        Useful for debugging or for lift types where side-view is not achievable.
        The returned features will have low view_confidence to signal unreliability.
        """
        from autocoach.pose.pipeline import PosePipeline

        # Use a short sequence so PhaseDetector raises before biomechanics runs —
        # we only care that PipelineError is NOT raised for the front view itself.
        seq = _make_front_view_sequence(n=5)
        pipeline = PosePipeline(reject_front_view=False)

        with patch.object(pipeline._extractor, "extract", return_value=seq):
            # PhaseDetector will raise PipelineError (too few frames) — that's fine,
            # it means we got past the view rejection check.
            from autocoach.pose.pipeline import PipelineError

            with pytest.raises(PipelineError, match="Phase detection"):
                pipeline.process(tmp_path / "v.mp4")

    def test_oblique_view_is_processed(self, tmp_path: Path) -> None:
        """OBLIQUE view is accepted — angles are usable, just with reduced confidence."""
        from autocoach.pose.pipeline import PosePipeline

        # Oblique: normalised spread between SIDE_THRESHOLD(0.3) and FRONT_THRESHOLD(1.0)
        # raw=0.24, torso=0.3 → normalised=0.80
        frames = []
        t = np.linspace(0, np.pi, 30)
        hip_y_curve = 0.50 + 0.15 * np.sin(t)
        for i in range(30):
            frames.append(
                _make_frame(i, left_hip_x=0.38, right_hip_x=0.62, hip_y=float(hip_y_curve[i]))
            )
        seq = PoseSequence(video_id="oblique_v", lift_type="Squat", frames=frames)

        pipeline = PosePipeline(reject_front_view=True)
        with patch.object(pipeline._extractor, "extract", return_value=seq):
            features = pipeline.process(tmp_path / "v.mp4")

        assert 0.0 < features.view_confidence < 1.0


# ---------------------------------------------------------------------------
# Output metadata
# ---------------------------------------------------------------------------


class TestOutputMetadata:
    def test_view_confidence_comes_from_classifier_not_default(self, tmp_path: Path) -> None:
        """BiomechanicsExtractor hardcodes view_confidence=1.0 in its output.

        The pipeline must overwrite this with the real value from ViewClassification
        so downstream consumers can weight retrieval results by view quality.
        """
        from autocoach.pose.pipeline import PosePipeline

        # Oblique view: spread=0.80, confidence = max(0, 1 - 0.80/1.0) = 0.20
        frames = []
        t = np.linspace(0, np.pi, 30)
        hip_y_curve = 0.50 + 0.15 * np.sin(t)
        for i in range(30):
            frames.append(
                _make_frame(i, left_hip_x=0.38, right_hip_x=0.62, hip_y=float(hip_y_curve[i]))
            )
        seq = PoseSequence(video_id="v", lift_type="Squat", frames=frames)

        pipeline = PosePipeline(reject_front_view=True)
        with patch.object(pipeline._extractor, "extract", return_value=seq):
            features = pipeline.process(tmp_path / "v.mp4")

        assert features.view_confidence != pytest.approx(1.0)
        assert 0.0 < features.view_confidence < 1.0

    def test_dominant_side_comes_from_classifier(self, tmp_path: Path) -> None:
        """dominant_side must reflect which hip is more visible to the camera.

        BiomechanicsExtractor uses dominant_side to choose left or right landmarks;
        passing the wrong side would silently flip every angle reading.
        """
        from autocoach.pose.pipeline import PosePipeline

        # Right hip more visible → ViewClassifier returns 'right'
        frames = []
        t = np.linspace(0, np.pi, 30)
        hip_y_curve = 0.50 + 0.15 * np.sin(t)
        for i in range(30):
            frames.append(_make_frame(i, left_vis=0.3, right_vis=0.9, hip_y=float(hip_y_curve[i])))
        seq = PoseSequence(video_id="v", lift_type="Squat", frames=frames)

        pipeline = PosePipeline()
        with patch.object(pipeline._extractor, "extract", return_value=seq):
            features = pipeline.process(tmp_path / "v.mp4")

        assert features.dominant_side == "right"

    def test_video_id_defaults_to_file_stem(self, tmp_path: Path) -> None:
        """When video_id is not supplied, the file stem is used.

        The stem is the natural identifier when processing files scraped to disk
        where the filename is the video ID.
        """
        from autocoach.pose.pipeline import PosePipeline

        base_seq = _make_side_view_squat()
        pipeline = PosePipeline()

        # Simulate real extractor behaviour: use whatever video_id is passed in
        def _extract(path: Path, video_id: str, lift_type: str) -> PoseSequence:
            return PoseSequence(video_id=video_id, lift_type=lift_type, frames=base_seq.frames)

        video_path = tmp_path / "abc123.mp4"
        with patch.object(pipeline._extractor, "extract", side_effect=_extract):
            features = pipeline.process(video_path)  # no video_id kwarg

        assert features.video_id == "abc123"

    def test_explicit_video_id_overrides_stem(self, tmp_path: Path) -> None:
        """Explicit video_id must take precedence over the file stem.

        When re-processing a file that was renamed after scraping, the caller
        needs to supply the original ID.
        """
        from autocoach.pose.pipeline import PosePipeline

        base_seq = _make_side_view_squat()
        pipeline = PosePipeline()

        def _extract(path: Path, video_id: str, lift_type: str) -> PoseSequence:
            return PoseSequence(video_id=video_id, lift_type=lift_type, frames=base_seq.frames)

        with patch.object(pipeline._extractor, "extract", side_effect=_extract):
            features = pipeline.process(tmp_path / "renamed.mp4", video_id="original_id")

        assert features.video_id == "original_id"


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_pose_extraction_error_propagates_unchanged(self, tmp_path: Path) -> None:
        """PoseExtractionError must bubble up without being wrapped in PipelineError.

        It carries a user-actionable message (e.g. 'run make download-models')
        that would be obscured if wrapped.
        """
        from autocoach.pose.pipeline import PosePipeline

        pipeline = PosePipeline()
        with (
            patch.object(
                pipeline._extractor,
                "extract",
                side_effect=PoseExtractionError("model not found: x"),
            ),
            pytest.raises(PoseExtractionError, match="model not found"),
        ):
            pipeline.process(tmp_path / "v.mp4")

    def test_pipeline_error_raised_when_too_few_frames(self, tmp_path: Path) -> None:
        """PhaseDetector.detect raises ValueError for short sequences.

        The pipeline must convert this to PipelineError so callers only need
        to catch two exception types (PoseExtractionError, PipelineError).
        """
        from autocoach.pose.pipeline import PipelineError, PosePipeline

        short_seq = _make_short_sequence(n=5)  # < MIN_FRAMES=10
        pipeline = PosePipeline()

        with (
            patch.object(pipeline._extractor, "extract", return_value=short_seq),
            pytest.raises(PipelineError, match="Phase detection"),
        ):
            pipeline.process(tmp_path / "v.mp4")


# ---------------------------------------------------------------------------
# End-to-end pipeline (fully mocked extractor, real downstream stages)
# ---------------------------------------------------------------------------


class TestPipelineEndToEnd:
    def test_returns_biomechanical_features_for_valid_squat(self, tmp_path: Path) -> None:
        """Happy path: side-view squat produces a fully populated BiomechanicalFeatures.

        This exercises the full stage chain (classifier → detector → normalizer →
        biomechanics) with a realistic synthetic sequence.
        """
        from autocoach.pose.models import BiomechanicalFeatures
        from autocoach.pose.normalizer import RuleBasedNormalizer
        from autocoach.pose.pipeline import PosePipeline

        seq = _make_side_view_squat(n=30)
        pipeline = PosePipeline()

        with patch.object(pipeline._extractor, "extract", return_value=seq):
            features = pipeline.process(tmp_path / "v.mp4", lift_type="Squat")

        norm = RuleBasedNormalizer()
        total = sum(norm.PHASE_TARGET_FRAMES.values())

        assert isinstance(features, BiomechanicalFeatures)
        assert len(features.knee_angles) == total
        assert len(features.phase_labels) == total
        assert features.lift_type == "Squat"
        assert features.view_confidence == pytest.approx(1.0, abs=0.05)


# ---------------------------------------------------------------------------
# Integration tests — require real model file
# ---------------------------------------------------------------------------

from autocoach.pose.extractor import _DEFAULT_MODEL  # noqa: E402


@pytest.fixture(scope="module")
def mediapipe_model() -> Path:
    """Skip the test module if the model file has not been downloaded."""
    if not _DEFAULT_MODEL.exists():
        pytest.skip(f"MediaPipe model not found at {_DEFAULT_MODEL} — run `make download-models`")
    return _DEFAULT_MODEL


@pytest.fixture
def synthetic_video(tmp_path: Path) -> Path:
    """Write a 30-frame blank MP4 using cv2.VideoWriter."""
    import cv2

    path = tmp_path / "test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(str(path), fourcc, 30.0, (128, 128))
    for _ in range(30):
        writer.write(np.zeros((128, 128, 3), dtype=np.uint8))
    writer.release()
    return path


@pytest.mark.integration
class TestPipelineIntegration:
    def test_pipeline_handles_no_pose_detected(
        self, mediapipe_model: Path, synthetic_video: Path
    ) -> None:
        """Blank video → no landmarks → PipelineError for front view or too few frames.

        Validates that the cv2 + MediaPipe + pipeline chain runs without
        unhandled exceptions even when no pose is detected.  All-zero landmarks
        produce zero lateral spread (SIDE_VIEW) and zero depth ratios, so
        PhaseDetector may or may not raise depending on sequence length.
        """
        from autocoach.pose.pipeline import PipelineError, PosePipeline

        pipeline = PosePipeline(model_path=mediapipe_model, reject_front_view=False)
        # With all-zero landmarks the pipeline will either succeed or raise a
        # PipelineError (phase detection fails on a flat depth curve).  Either
        # way it must not raise any other exception type.
        with contextlib.suppress(PipelineError):
            pipeline.process(synthetic_video, lift_type="Squat")
