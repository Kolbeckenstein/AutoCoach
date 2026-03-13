"""Tests for PoseExtractor.

Each test maps to a real pipeline consequence:
- Error guards (model missing, video missing) prevent silent bad output
- Frame count determines whether PhaseDetector has enough data to work with
- Landmark shape (33, 4) is the contract every downstream module depends on
- Zero-landmark fallback keeps frame indices stable so timestamps never skip
- Timestamp derivation from FPS ensures monotonic input to MediaPipe VIDEO mode

Fixture note: unit tests mock both cv2.VideoCapture and
vision.PoseLandmarker.create_from_options so that no model file or
real video is required.  Integration tests (pytest.mark.integration)
require the model file and are skipped automatically when it is absent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from autocoach.pose.extractor import _DEFAULT_MODEL, PoseExtractionError, PoseExtractor
from autocoach.pose.models import PoseSequence

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_landmark_list(n: int = 33) -> list[MagicMock]:
    """Build a list of n mock MediaPipe NormalizedLandmark objects."""
    lms = []
    for i in range(n):
        lm = MagicMock()
        lm.x = float(i) / 100
        lm.y = float(i) / 100
        lm.z = 0.0
        lm.visibility = 0.9
        lms.append(lm)
    return lms


def _mock_cap(n_frames: int = 5, fps: float = 30.0) -> MagicMock:
    """Return a mock cv2.VideoCapture that yields *n_frames* blank frames."""
    cap = MagicMock()
    cap.isOpened.return_value = True
    cap.get.return_value = fps
    blank = np.zeros((64, 64, 3), dtype=np.uint8)
    cap.read.side_effect = [(True, blank)] * n_frames + [(False, None)]
    return cap


def _mock_landmarker_cm(landmarks: list | None = None) -> tuple[MagicMock, MagicMock]:
    """Return (context_manager, inner_landmarker) mock pair.

    *landmarks* is what ``result.pose_landmarks`` will hold — pass a list of
    33 landmark mocks for a detected pose, or ``[]`` for no detection.
    """
    result = MagicMock()
    result.pose_landmarks = landmarks if landmarks is not None else [_make_landmark_list()]

    inner = MagicMock()
    inner.detect_for_video.return_value = result

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=inner)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, inner


# ---------------------------------------------------------------------------
# Error guards: model and video validation
# ---------------------------------------------------------------------------


class TestErrorGuards:
    def test_raises_when_model_missing(self, tmp_path: Path) -> None:
        """Pipeline cannot proceed without the MediaPipe .task file.

        This check runs before any cv2 or MediaPipe code so the error
        message can tell the user exactly how to fix it (run make download-models).
        """
        extractor = PoseExtractor(model_path=tmp_path / "nonexistent.task")
        with pytest.raises(PoseExtractionError, match="model not found"):
            extractor.extract(tmp_path / "video.mp4", video_id="v", lift_type="Squat")

    def test_raises_when_video_missing(self, tmp_path: Path) -> None:
        """Non-existent video path must fail with a clear error before MediaPipe opens.

        Without this guard the error surfaces deep inside cv2 with a cryptic
        message that doesn't mention the file path.
        """
        model = tmp_path / "model.task"
        model.touch()  # exists but empty — we don't open it in this code path
        extractor = PoseExtractor(model_path=model)
        with pytest.raises(PoseExtractionError, match="not found"):
            extractor.extract(tmp_path / "missing.mp4", video_id="v", lift_type="Squat")

    def test_raises_when_cap_cannot_open(self, tmp_path: Path) -> None:
        """cv2 reports it cannot open the file (wrong format, permissions, etc.).

        An unopenable capture means zero frames would be read — propagate this
        as a PoseExtractionError rather than silently returning an empty sequence.
        """
        model = tmp_path / "model.task"
        model.touch()
        video = tmp_path / "bad.mp4"
        video.write_bytes(b"not a video")

        bad_cap = MagicMock()
        bad_cap.isOpened.return_value = False

        extractor = PoseExtractor(model_path=model)
        with (
            patch("autocoach.pose.extractor.cv2.VideoCapture", return_value=bad_cap),
            pytest.raises(PoseExtractionError),
        ):
            extractor.extract(video, video_id="v", lift_type="Squat")


# ---------------------------------------------------------------------------
# Frame extraction behaviour
# ---------------------------------------------------------------------------


class TestFrameExtraction:
    def test_returns_one_frame_per_video_frame(self, tmp_path: Path) -> None:
        """Frame count must equal the number of frames cv2 reads.

        PhaseDetector requires MIN_FRAMES=10; any silent frame drop would cause
        it to raise ValueError on videos that are long enough in reality.
        """
        model = tmp_path / "model.task"
        model.touch()
        video = tmp_path / "v.mp4"
        video.touch()
        cap = _mock_cap(n_frames=15)
        cm, _ = _mock_landmarker_cm()

        extractor = PoseExtractor(model_path=model)
        with (
            patch("autocoach.pose.extractor.cv2.VideoCapture", return_value=cap),
            patch(
                "autocoach.pose.extractor.cv2.cvtColor",
                return_value=np.zeros((64, 64, 3), dtype=np.uint8),
            ),
            patch("autocoach.pose.extractor.mp.Image"),
            patch(
                "autocoach.pose.extractor.vision.PoseLandmarker.create_from_options",
                return_value=cm,
            ),
        ):
            seq = extractor.extract(video, video_id="v", lift_type="Squat")

        assert len(seq.frames) == 15

    def test_landmark_shape_is_33_by_4(self, tmp_path: Path) -> None:
        """Every downstream module indexes landmarks as array[joint_idx, column].

        columns: 0=x, 1=y, 2=z, 3=visibility.  Wrong shape silently corrupts
        angle calculations and cannot be caught at runtime.
        """
        model = tmp_path / "model.task"
        model.touch()
        video = tmp_path / "v.mp4"
        video.touch()
        cap = _mock_cap(n_frames=1)
        cm, _ = _mock_landmarker_cm(landmarks=[_make_landmark_list(33)])

        extractor = PoseExtractor(model_path=model)
        with (
            patch("autocoach.pose.extractor.cv2.VideoCapture", return_value=cap),
            patch(
                "autocoach.pose.extractor.cv2.cvtColor",
                return_value=np.zeros((64, 64, 3), dtype=np.uint8),
            ),
            patch("autocoach.pose.extractor.mp.Image"),
            patch(
                "autocoach.pose.extractor.vision.PoseLandmarker.create_from_options",
                return_value=cm,
            ),
        ):
            seq = extractor.extract(video, video_id="v", lift_type="Squat")

        assert seq.frames[0].landmarks.shape == (33, 4)

    def test_zero_landmarks_when_no_detection(self, tmp_path: Path) -> None:
        """When MediaPipe detects no person, the frame must still be appended.

        Skipping no-detection frames would desync frame indices from timestamps,
        breaking any downstream logic that aligns frames to video time.
        A zero-filled array signals 'no detection' without dropping the frame.
        """
        model = tmp_path / "model.task"
        model.touch()
        video = tmp_path / "v.mp4"
        video.touch()
        cap = _mock_cap(n_frames=3)
        cm_no_det, _ = _mock_landmarker_cm(landmarks=[])  # no detection

        extractor = PoseExtractor(model_path=model)
        with (
            patch("autocoach.pose.extractor.cv2.VideoCapture", return_value=cap),
            patch(
                "autocoach.pose.extractor.cv2.cvtColor",
                return_value=np.zeros((64, 64, 3), dtype=np.uint8),
            ),
            patch("autocoach.pose.extractor.mp.Image"),
            patch(
                "autocoach.pose.extractor.vision.PoseLandmarker.create_from_options",
                return_value=cm_no_det,
            ),
        ):
            seq = extractor.extract(video, video_id="v", lift_type="Squat")

        assert len(seq.frames) == 3
        assert np.all(seq.frames[0].landmarks == 0.0)

    def test_timestamps_derived_from_fps_not_pos_msec(self, tmp_path: Path) -> None:
        """Timestamps must come from frame_index / FPS, not CAP_PROP_POS_MSEC.

        Many codecs return 0 for CAP_PROP_POS_MSEC on every frame.  MediaPipe
        VIDEO mode requires strictly monotonically increasing timestamps — if
        all timestamps are 0 it raises a runtime error.
        """
        model = tmp_path / "model.task"
        model.touch()
        video = tmp_path / "v.mp4"
        video.touch()
        cap = _mock_cap(n_frames=3, fps=25.0)
        cm, _ = _mock_landmarker_cm()

        extractor = PoseExtractor(model_path=model)
        with (
            patch("autocoach.pose.extractor.cv2.VideoCapture", return_value=cap),
            patch(
                "autocoach.pose.extractor.cv2.cvtColor",
                return_value=np.zeros((64, 64, 3), dtype=np.uint8),
            ),
            patch("autocoach.pose.extractor.mp.Image"),
            patch(
                "autocoach.pose.extractor.vision.PoseLandmarker.create_from_options",
                return_value=cm,
            ),
        ):
            seq = extractor.extract(video, video_id="v", lift_type="Squat")

        # frame 0 → 0ms, frame 1 → 40ms (1/25s), frame 2 → 80ms
        assert seq.frames[0].timestamp == pytest.approx(0.0)
        assert seq.frames[1].timestamp == pytest.approx(1 / 25.0, abs=0.002)
        assert seq.frames[2].timestamp == pytest.approx(2 / 25.0, abs=0.002)

    def test_frame_indices_are_sequential(self, tmp_path: Path) -> None:
        """frame.index must be 0, 1, 2, … regardless of detection success.

        Downstream code uses frame.index to correlate pose data back to the
        original video for display; gaps in the index make this correlation wrong.
        """
        model = tmp_path / "model.task"
        model.touch()
        video = tmp_path / "v.mp4"
        video.touch()
        cap = _mock_cap(n_frames=5)
        cm, _ = _mock_landmarker_cm()

        extractor = PoseExtractor(model_path=model)
        with (
            patch("autocoach.pose.extractor.cv2.VideoCapture", return_value=cap),
            patch(
                "autocoach.pose.extractor.cv2.cvtColor",
                return_value=np.zeros((64, 64, 3), dtype=np.uint8),
            ),
            patch("autocoach.pose.extractor.mp.Image"),
            patch(
                "autocoach.pose.extractor.vision.PoseLandmarker.create_from_options",
                return_value=cm,
            ),
        ):
            seq = extractor.extract(video, video_id="v", lift_type="Squat")

        assert [f.index for f in seq.frames] == list(range(5))

    def test_metadata_propagated_to_sequence(self, tmp_path: Path) -> None:
        """video_id and lift_type on the returned PoseSequence must match inputs.

        Downstream DB writes use these fields; silently wrong metadata would
        corrupt the pose store without any runtime error.
        """
        model = tmp_path / "model.task"
        model.touch()
        video = tmp_path / "v.mp4"
        video.touch()
        cap = _mock_cap(n_frames=1)
        cm, _ = _mock_landmarker_cm()

        extractor = PoseExtractor(model_path=model)
        with (
            patch("autocoach.pose.extractor.cv2.VideoCapture", return_value=cap),
            patch(
                "autocoach.pose.extractor.cv2.cvtColor",
                return_value=np.zeros((64, 64, 3), dtype=np.uint8),
            ),
            patch("autocoach.pose.extractor.mp.Image"),
            patch(
                "autocoach.pose.extractor.vision.PoseLandmarker.create_from_options",
                return_value=cm,
            ),
        ):
            seq = extractor.extract(video, video_id="my_vid", lift_type="Deadlift")

        assert seq.video_id == "my_vid"
        assert seq.lift_type == "Deadlift"


# ---------------------------------------------------------------------------
# Integration tests — require real model file
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mediapipe_model() -> Path:
    """Skip the test if the MediaPipe model file has not been downloaded yet."""
    if not _DEFAULT_MODEL.exists():
        pytest.skip(f"MediaPipe model not found at {_DEFAULT_MODEL} — run `make download-models`")
    return _DEFAULT_MODEL


@pytest.fixture
def synthetic_video(tmp_path: Path) -> Path:
    """Write a small solid-colour MP4 using cv2.VideoWriter."""
    import cv2

    path = tmp_path / "test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
    writer = cv2.VideoWriter(str(path), fourcc, 30.0, (128, 128))
    for _ in range(30):
        writer.write(np.zeros((128, 128, 3), dtype=np.uint8))
    writer.release()
    return path


@pytest.mark.integration
class TestExtractorIntegration:
    def test_returns_pose_sequence_for_synthetic_video(
        self, mediapipe_model: Path, synthetic_video: Path
    ) -> None:
        """Full extraction pipeline runs without error on a real (blank) video.

        MediaPipe will not detect a pose in a blank frame, so all landmarks
        will be zero — but the sequence must still contain 30 frames.
        Validates that the cv2 + MediaPipe Tasks API wiring is correct.
        """
        extractor = PoseExtractor(model_path=mediapipe_model)
        seq = extractor.extract(synthetic_video, video_id="synth", lift_type="Squat")

        assert isinstance(seq, PoseSequence)
        assert seq.video_id == "synth"
        assert len(seq.frames) == 30
        assert seq.frames[0].landmarks.shape == (33, 4)
        # timestamps increase monotonically
        ts = [f.timestamp for f in seq.frames]
        assert all(ts[i] <= ts[i + 1] for i in range(len(ts) - 1))
