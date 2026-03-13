"""Tests for BiomechanicsExtractor."""

import math

import numpy as np
import pytest

from autocoach.pose.models import Frame, NormalizedPoseSequence

pytestmark = pytest.mark.unit

# Landmark indices
LEFT_SHOULDER = 11
LEFT_HIP = 23
LEFT_KNEE = 25
LEFT_ANKLE = 27
RIGHT_HIP = 24
RIGHT_KNEE = 26
RIGHT_ANKLE = 28


def _zero_frame(index: int = 0) -> Frame:
    return Frame(index=index, timestamp=0.0, landmarks=np.zeros((33, 4), dtype=np.float32))


def _set_xy(frame: Frame, idx: int, x: float, y: float) -> None:
    frame.landmarks[idx, 0] = x
    frame.landmarks[idx, 1] = y


def _make_normalized(
    n_descent: int = 16, n_bottom: int = 8, n_ascent: int = 16, fill: float = 0.0
) -> NormalizedPoseSequence:
    def _frames(n: int) -> list[Frame]:
        frames = []
        for i in range(n):
            lm = np.full((33, 4), fill, dtype=np.float32)
            frames.append(Frame(index=i, timestamp=float(i), landmarks=lm))
        return frames

    return NormalizedPoseSequence(
        video_id="v",
        lift_type="Squat",
        phases={
            "descent": _frames(n_descent),
            "bottom": _frames(n_bottom),
            "ascent": _frames(n_ascent),
        },
    )


class TestAngleAtVertex:
    def test_right_angle_is_90(self) -> None:
        """Anchors the angle formula — wrong math corrupts every downstream angle."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        b = BiomechanicsExtractor()
        a = np.array([0.0, 0.0])
        vertex = np.array([1.0, 0.0])
        c = np.array([1.0, 1.0])
        assert b._angle_at_vertex(a, vertex, c) == pytest.approx(90.0, abs=0.1)

    def test_straight_line_is_180(self) -> None:
        """Full extension (standing leg) must read as 180°."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        b = BiomechanicsExtractor()
        a = np.array([0.0, 0.0])
        vertex = np.array([1.0, 0.0])
        c = np.array([2.0, 0.0])
        assert b._angle_at_vertex(a, vertex, c) == pytest.approx(180.0, abs=0.1)

    def test_collinear_points_dont_produce_nan(self) -> None:
        """arccos domain must be clamped — NaN propagates silently through the pipeline."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        b = BiomechanicsExtractor()
        a = np.array([0.0, 0.0])
        vertex = np.array([1.0, 0.0])
        c = np.array([2.0, 0.0])
        result = b._angle_at_vertex(a, vertex, c)
        assert not math.isnan(result)


class TestKneeAngle:
    def test_straight_leg_is_180(self) -> None:
        """Standing position: hip, knee, ankle are collinear → 180°."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        frame = _zero_frame()
        _set_xy(frame, LEFT_HIP, x=0.5, y=0.3)
        _set_xy(frame, LEFT_KNEE, x=0.5, y=0.6)
        _set_xy(frame, LEFT_ANKLE, x=0.5, y=0.9)  # perfectly straight
        angle = BiomechanicsExtractor()._knee_angle(frame, side="left")
        assert angle == pytest.approx(180.0, abs=1.0)

    def test_bent_knee_is_less_than_180(self) -> None:
        """Any knee flexion must read below 180°."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        frame = _zero_frame()
        _set_xy(frame, LEFT_HIP, x=0.5, y=0.3)
        _set_xy(frame, LEFT_KNEE, x=0.5, y=0.6)
        _set_xy(frame, LEFT_ANKLE, x=0.6, y=0.85)  # ankle displaced forward
        angle = BiomechanicsExtractor()._knee_angle(frame, side="left")
        assert angle < 180.0


class TestBackAngle:
    def test_upright_torso_is_near_zero(self) -> None:
        """Vertical shoulder-hip vector → 0° back angle; baseline for 'good form'."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        frame = _zero_frame()
        _set_xy(frame, LEFT_HIP, x=0.5, y=0.6)
        _set_xy(frame, LEFT_SHOULDER, x=0.5, y=0.2)  # directly above hip
        angle = BiomechanicsExtractor()._back_angle(frame, side="left")
        assert angle == pytest.approx(0.0, abs=2.0)

    def test_forward_lean_increases_back_angle(self) -> None:
        """Forward lean must increase back angle monotonically — core diagnostic."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        ext = BiomechanicsExtractor()
        upright = _zero_frame()
        _set_xy(upright, LEFT_HIP, x=0.5, y=0.6)
        _set_xy(upright, LEFT_SHOULDER, x=0.5, y=0.2)

        leaned = _zero_frame()
        _set_xy(leaned, LEFT_HIP, x=0.5, y=0.6)
        _set_xy(leaned, LEFT_SHOULDER, x=0.3, y=0.3)  # shoulder forward of hip

        assert ext._back_angle(leaned, side="left") > ext._back_angle(upright, side="left")


class TestExtract:
    def test_feature_vector_length_matches_normalizer_output(self) -> None:
        """RAG layer assumes a fixed-length vector; mismatch silently corrupts embeddings."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor
        from autocoach.pose.normalizer import RuleBasedNormalizer

        norm = RuleBasedNormalizer()
        total = sum(norm.PHASE_TARGET_FRAMES.values())
        nps = _make_normalized()
        features = BiomechanicsExtractor().extract(nps, dominant_side="left")
        assert len(features.knee_angles) == total
        assert len(features.hip_angles) == total
        assert len(features.back_angles) == total
        assert len(features.phase_labels) == total

    def test_phase_labels_order_is_descent_bottom_ascent(self) -> None:
        """Downstream plotting depends on this ordering to align the time axis."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor
        from autocoach.pose.normalizer import RuleBasedNormalizer

        norm = RuleBasedNormalizer()
        nps = _make_normalized()
        features = BiomechanicsExtractor().extract(nps, dominant_side="left")
        n_d = norm.PHASE_TARGET_FRAMES["descent"]
        n_b = norm.PHASE_TARGET_FRAMES["bottom"]
        assert all(lbl == "descent" for lbl in features.phase_labels[:n_d])
        assert all(lbl == "bottom" for lbl in features.phase_labels[n_d : n_d + n_b])
        assert all(lbl == "ascent" for lbl in features.phase_labels[n_d + n_b :])

    def test_dominant_side_determines_which_landmarks_used(self) -> None:
        """Wrong side → wrong angles; must differ for left-only vs right-only sequences."""
        from autocoach.pose.biomechanics import BiomechanicsExtractor

        frame = _zero_frame()
        # Left side: straight knee; right side: bent knee
        _set_xy(frame, LEFT_HIP, x=0.5, y=0.3)
        _set_xy(frame, LEFT_KNEE, x=0.5, y=0.6)
        _set_xy(frame, LEFT_ANKLE, x=0.5, y=0.9)

        _set_xy(frame, RIGHT_HIP, x=0.5, y=0.3)
        _set_xy(frame, RIGHT_KNEE, x=0.5, y=0.6)
        _set_xy(frame, RIGHT_ANKLE, x=0.6, y=0.85)  # bent

        nps = NormalizedPoseSequence(
            video_id="v",
            lift_type="Squat",
            phases={"descent": [frame] * 16, "bottom": [frame] * 8, "ascent": [frame] * 16},
        )
        left_features = BiomechanicsExtractor().extract(nps, dominant_side="left")
        right_features = BiomechanicsExtractor().extract(nps, dominant_side="right")
        assert left_features.knee_angles[0] != right_features.knee_angles[0]
