"""Tests for PhaseDetector.

Each test maps to a real pipeline consequence — see inline comments.
"""

import numpy as np
import pytest

from autocoach.pose.models import Frame, PoseSequence

pytestmark = pytest.mark.unit

LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26


def _make_sequence_from_depth_ratios(ratios: list[float]) -> PoseSequence:
    """Build a PoseSequence whose hip_y - knee_y matches the given ratios.

    depth_ratio = hip_y - knee_y:
      negative → hip above knee (standing)
      near 0   → parallel / depth
      positive → hip below knee (ATG)
    """
    frames = []
    for i, ratio in enumerate(ratios):
        lm = np.zeros((33, 4), dtype=np.float32)
        # Place knee at y=0.6, hip at y = 0.6 + ratio
        lm[LEFT_KNEE, 1] = 0.6
        lm[RIGHT_KNEE, 1] = 0.6
        lm[LEFT_HIP, 1] = 0.6 + ratio
        lm[RIGHT_HIP, 1] = 0.6 + ratio
        frames.append(Frame(index=i, timestamp=float(i) / 30, landmarks=lm))
    return PoseSequence(video_id="test", lift_type="Squat", frames=frames)


def _squat_ratios(n: int = 30) -> list[float]:
    """Smooth squat profile: stand → descend → depth → ascend → stand."""
    t = np.linspace(0, np.pi, n)
    # sin curve: 0 at start/end (standing), peak in middle (depth)
    result: list[float] = (np.sin(t) * 0.15 - 0.2).tolist()  # standing at -0.2, depth at -0.05
    return result


class TestPhaseDetector:
    def test_detects_three_phases_for_squat(self) -> None:
        """Complete lift → exactly descent, bottom, ascent returned."""
        from autocoach.pose.phases import PhaseDetector

        seq = _make_sequence_from_depth_ratios(_squat_ratios())
        phases = PhaseDetector().detect(seq)
        names = [p.name for p in phases]
        assert names == ["descent", "bottom", "ascent"]

    def test_bottom_phase_contains_max_depth_frame(self) -> None:
        """The frame with maximum depth_ratio must fall inside the bottom segment.
        The bottom is the most diagnostically important moment — misidentifying
        it means form analysis is based on the wrong position.
        """
        from autocoach.pose.phases import PhaseDetector

        ratios = _squat_ratios(30)
        seq = _make_sequence_from_depth_ratios(ratios)
        phases = PhaseDetector().detect(seq)
        bottom = next(p for p in phases if p.name == "bottom")
        max_idx = int(np.argmax(ratios))
        assert bottom.start_idx <= max_idx <= bottom.end_idx

    def test_descent_ends_at_or_before_bottom(self) -> None:
        """Phase ordering: descent must precede bottom in every valid sequence."""
        from autocoach.pose.phases import PhaseDetector

        seq = _make_sequence_from_depth_ratios(_squat_ratios())
        phases = PhaseDetector().detect(seq)
        descent = next(p for p in phases if p.name == "descent")
        bottom = next(p for p in phases if p.name == "bottom")
        assert descent.end_idx <= bottom.start_idx

    def test_ascent_starts_at_or_after_bottom(self) -> None:
        """Phase ordering: ascent must follow bottom in every valid sequence."""
        from autocoach.pose.phases import PhaseDetector

        seq = _make_sequence_from_depth_ratios(_squat_ratios())
        phases = PhaseDetector().detect(seq)
        bottom = next(p for p in phases if p.name == "bottom")
        ascent = next(p for p in phases if p.name == "ascent")
        assert ascent.start_idx >= bottom.end_idx

    def test_phases_cover_all_frames(self) -> None:
        """No frames are silently dropped — every frame contributes to features.
        A gap would mean part of the lift is invisible to the biomechanics layer.
        """
        from autocoach.pose.phases import PhaseDetector

        ratios = _squat_ratios(30)
        seq = _make_sequence_from_depth_ratios(ratios)
        phases = PhaseDetector().detect(seq)
        assert phases[0].start_idx == 0
        assert phases[-1].end_idx == len(ratios) - 1

    def test_raises_on_too_few_frames(self) -> None:
        """Very short clips can't be meaningfully analysed — fail explicitly
        rather than silently producing nonsense feature vectors.
        """
        from autocoach.pose.phases import PhaseDetector

        seq = _make_sequence_from_depth_ratios([0.0, 0.1, 0.0])
        with pytest.raises(ValueError, match="too few frames"):
            PhaseDetector().detect(seq)

    def test_smoothing_stabilises_noisy_bottom(self) -> None:
        """Noisy depth_ratio should not scatter the bottom across many frames.
        Without median smoothing, jitter shifts the argmax frame-by-frame,
        causing unstable phase boundaries across repeated runs.
        """
        from autocoach.pose.phases import PhaseDetector

        # True bottom around frame 15, with random noise
        rng = np.random.default_rng(42)
        ratios = _squat_ratios(30)
        noisy = [r + rng.normal(0, 0.02) for r in ratios]
        seq_clean = _make_sequence_from_depth_ratios(ratios)
        seq_noisy = _make_sequence_from_depth_ratios(noisy)
        phases_clean = PhaseDetector().detect(seq_clean)
        phases_noisy = PhaseDetector().detect(seq_noisy)
        bottom_clean = next(p for p in phases_clean if p.name == "bottom")
        bottom_noisy = next(p for p in phases_noisy if p.name == "bottom")
        # Bottom frame should be within 3 frames of the clean version
        assert abs(bottom_clean.start_idx - bottom_noisy.start_idx) <= 3
