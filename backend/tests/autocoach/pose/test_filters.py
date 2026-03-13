"""Tests for ViewClassifier.

Each test maps to a real consequence for the biomechanics / RAG pipeline:
- view_class determines whether a video is processed at all
- view_confidence is stored on BiomechanicalFeatures and used by downstream
  consumers to weight retrieval results
- dominant_side tells BiomechanicsExtractor which set of landmarks to use

Fixture note: shoulder_y=0.2 / hip_y=0.5 gives torso_height=0.3, a typical
value for a person filling roughly half the frame height.  The normalised
spread is raw_spread / 0.3, so test x-values are chosen accordingly.
"""

import numpy as np
import pytest

from autocoach.pose.models import Frame, PoseSequence, ViewClass

pytestmark = pytest.mark.unit

LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_KNEE, RIGHT_KNEE = 25, 26


def _make_sequence(
    left_hip_x: float = 0.5,
    right_hip_x: float = 0.5,
    left_hip_vis: float = 0.9,
    right_hip_vis: float = 0.9,
    shoulder_y: float = 0.2,  # torso_height = hip_y - shoulder_y = 0.3
    hip_y: float = 0.5,
    n_frames: int = 10,
) -> PoseSequence:
    """Build a PoseSequence with controllable hip x-positions, visibility, and torso height."""
    frames = []
    for i in range(n_frames):
        lm = np.zeros((33, 4), dtype=np.float32)
        lm[:, 3] = 0.9
        lm[LEFT_HIP, 0] = left_hip_x
        lm[LEFT_HIP, 1] = hip_y
        lm[LEFT_HIP, 3] = left_hip_vis
        lm[RIGHT_HIP, 0] = right_hip_x
        lm[RIGHT_HIP, 1] = hip_y
        lm[RIGHT_HIP, 3] = right_hip_vis
        lm[LEFT_SHOULDER, 0] = left_hip_x
        lm[LEFT_SHOULDER, 1] = shoulder_y
        lm[RIGHT_SHOULDER, 0] = right_hip_x
        lm[RIGHT_SHOULDER, 1] = shoulder_y
        frames.append(Frame(index=i, timestamp=float(i) / 30, landmarks=lm))
    return PoseSequence(video_id="v", lift_type="Squat", frames=frames)


class TestViewClass:
    def test_classifies_perfect_side_view(self) -> None:
        """Near-zero normalised spread → SIDE_VIEW. Joint angles are authoritative.
        raw=0.01, torso=0.3 → normalised=0.033 < SIDE_THRESHOLD(0.3).
        """
        from autocoach.pose.filters import ViewClassifier

        seq = _make_sequence(left_hip_x=0.50, right_hip_x=0.51)
        assert ViewClassifier().classify(seq).view_class == ViewClass.SIDE_VIEW

    def test_classifies_oblique_view(self) -> None:
        """~45° off-axis → OBLIQUE. Accepted but confidence < 1.
        raw=0.24, torso=0.3 → normalised=0.80, between SIDE(0.3) and FRONT(1.0).
        """
        from autocoach.pose.filters import ViewClassifier

        seq = _make_sequence(left_hip_x=0.38, right_hip_x=0.62)
        assert ViewClassifier().classify(seq).view_class == ViewClass.OBLIQUE

    def test_classifies_front_view(self) -> None:
        """Wide spread → FRONT_VIEW. Angles are geometrically meaningless.
        raw=0.44, torso=0.3 → normalised=1.47 > FRONT_THRESHOLD(1.0).
        """
        from autocoach.pose.filters import ViewClassifier

        seq = _make_sequence(left_hip_x=0.28, right_hip_x=0.72)
        assert ViewClassifier().classify(seq).view_class == ViewClass.FRONT_VIEW

    def test_side_view_has_full_confidence(self) -> None:
        """view_confidence≈1.0 signals downstream that angles are authoritative."""
        from autocoach.pose.filters import ViewClassifier

        seq = _make_sequence(left_hip_x=0.50, right_hip_x=0.51)
        assert ViewClassifier().classify(seq).view_confidence == pytest.approx(1.0, abs=0.05)

    def test_front_view_has_zero_confidence(self) -> None:
        """view_confidence=0.0 lets consumers filter without hardcoding ViewClass."""
        from autocoach.pose.filters import ViewClassifier

        seq = _make_sequence(left_hip_x=0.28, right_hip_x=0.72)
        assert ViewClassifier().classify(seq).view_confidence == pytest.approx(0.0, abs=0.05)

    def test_oblique_confidence_is_between_zero_and_one(self) -> None:
        """Oblique is neither authoritative nor garbage — intermediate signal."""
        from autocoach.pose.filters import ViewClassifier

        result = ViewClassifier().classify(_make_sequence(left_hip_x=0.38, right_hip_x=0.62))
        assert 0.0 < result.view_confidence < 1.0

    def test_empty_sequence_returns_front_view(self) -> None:
        """No frames → can't classify → conservatively reject."""
        from autocoach.pose.filters import ViewClassifier

        seq = PoseSequence(video_id="x", lift_type="Squat", frames=[])
        assert ViewClassifier().classify(seq).view_class == ViewClass.FRONT_VIEW

    def test_decision_uses_mean_across_all_frames(self) -> None:
        """9 front-view frames + 1 side-view frame → still classified FRONT_VIEW.
        A single outlier frame must not flip the classification.
        """
        from autocoach.pose.filters import ViewClassifier

        def _frame(idx: int, left_x: float, right_x: float) -> Frame:
            lm = np.zeros((33, 4), dtype=np.float32)
            lm[:, 3] = 0.9
            lm[LEFT_HIP, 0] = left_x
            lm[LEFT_HIP, 1] = 0.5
            lm[RIGHT_HIP, 0] = right_x
            lm[RIGHT_HIP, 1] = 0.5
            lm[LEFT_SHOULDER, 0] = left_x
            lm[LEFT_SHOULDER, 1] = 0.2
            lm[RIGHT_SHOULDER, 0] = right_x
            lm[RIGHT_SHOULDER, 1] = 0.2
            return Frame(index=idx, timestamp=float(idx), landmarks=lm)

        frames = [_frame(i, 0.30, 0.70) for i in range(9)]  # front-view
        frames.append(_frame(9, 0.50, 0.51))  # side-view outlier
        seq = PoseSequence(video_id="x", lift_type="Squat", frames=frames)
        assert ViewClassifier().classify(seq).view_class == ViewClass.FRONT_VIEW


class TestDominantSide:
    def test_left_when_left_hip_more_visible(self) -> None:
        """BiomechanicsExtractor uses dominant_side to pick left or right landmarks."""
        from autocoach.pose.filters import ViewClassifier

        result = ViewClassifier().classify(_make_sequence(left_hip_vis=0.9, right_hip_vis=0.3))
        assert result.dominant_side == "left"

    def test_right_when_right_hip_more_visible(self) -> None:
        """Person filmed from the right — right-side landmarks are more reliable."""
        from autocoach.pose.filters import ViewClassifier

        result = ViewClassifier().classify(_make_sequence(left_hip_vis=0.3, right_hip_vis=0.9))
        assert result.dominant_side == "right"

    def test_defaults_to_left_when_visibility_equal(self) -> None:
        """Tie-break: r/formcheck convention is left-side-toward-camera."""
        from autocoach.pose.filters import ViewClassifier

        result = ViewClassifier().classify(_make_sequence(left_hip_vis=0.9, right_hip_vis=0.9))
        assert result.dominant_side == "left"


class TestVisibilityRejection:
    def test_rejects_as_front_view_when_key_landmarks_invisible(self) -> None:
        """Occluded joints (baggy clothes, partial frame) → reject regardless of angle.
        Prevents garbage landmark positions from producing plausible-looking angles.
        """
        from autocoach.pose.filters import ViewClassifier

        seq = _make_sequence(left_hip_vis=0.1, right_hip_vis=0.1)
        assert ViewClassifier().classify(seq).view_class == ViewClass.FRONT_VIEW
