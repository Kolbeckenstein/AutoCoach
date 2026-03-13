"""Tests for RuleBasedNormalizer."""

import numpy as np
import pytest

from autocoach.pose.models import Frame, PhaseSegment, PoseSequence

pytestmark = pytest.mark.unit


def _make_frame(index: int, val: float) -> Frame:
    """Frame whose entire landmark array is filled with ``val``."""
    return Frame(
        index=index, timestamp=float(index) / 30, landmarks=np.full((33, 4), val, dtype=np.float32)
    )


def _make_sequence(n_frames: int, lift_type: str = "Squat") -> PoseSequence:
    frames = [_make_frame(i, float(i)) for i in range(n_frames)]
    return PoseSequence(video_id="v1", lift_type=lift_type, frames=frames)


def _three_phases(n: int) -> list[PhaseSegment]:
    """Split n frames evenly into three phases."""
    third = n // 3
    return [
        PhaseSegment(name="descent", start_idx=0, end_idx=third - 1),
        PhaseSegment(name="bottom", start_idx=third, end_idx=2 * third - 1),
        PhaseSegment(name="ascent", start_idx=2 * third, end_idx=n - 1),
    ]


class TestRuleBasedNormalizer:
    def test_output_has_correct_frame_count_per_phase(self) -> None:
        """Fixed-length phases are the contract the RAG/biomechanics layer relies
        on for a consistent feature vector length across all videos."""
        from autocoach.pose.normalizer import RuleBasedNormalizer

        norm = RuleBasedNormalizer()
        seq = _make_sequence(30)
        nps = norm.normalize(seq, _three_phases(30))
        assert len(nps.phases["descent"]) == norm.PHASE_TARGET_FRAMES["descent"]
        assert len(nps.phases["bottom"]) == norm.PHASE_TARGET_FRAMES["bottom"]
        assert len(nps.phases["ascent"]) == norm.PHASE_TARGET_FRAMES["ascent"]

    def test_short_phase_expanded_to_target(self) -> None:
        """A 1-frame bottom (e.g. very short pause at depth) must expand cleanly."""
        from autocoach.pose.normalizer import RuleBasedNormalizer

        norm = RuleBasedNormalizer()
        seq = _make_sequence(30)
        phases = [
            PhaseSegment(name="descent", start_idx=0, end_idx=13),
            PhaseSegment(name="bottom", start_idx=14, end_idx=14),  # single frame
            PhaseSegment(name="ascent", start_idx=15, end_idx=29),
        ]
        nps = norm.normalize(seq, phases)
        assert len(nps.phases["bottom"]) == norm.PHASE_TARGET_FRAMES["bottom"]

    def test_long_phase_shrunk_to_target(self) -> None:
        """High-fps video → many frames per phase → must shrink without crashing."""
        from autocoach.pose.normalizer import RuleBasedNormalizer

        norm = RuleBasedNormalizer()
        seq = _make_sequence(120)
        nps = norm.normalize(seq, _three_phases(120))
        assert len(nps.phases["descent"]) == norm.PHASE_TARGET_FRAMES["descent"]

    def test_landmark_shape_preserved_after_resampling(self) -> None:
        """Shape (33,4) must survive interpolation — all downstream numpy ops
        assume this shape without checking."""
        from autocoach.pose.normalizer import RuleBasedNormalizer

        nps = RuleBasedNormalizer().normalize(_make_sequence(30), _three_phases(30))
        for phase_frames in nps.phases.values():
            for frame in phase_frames:
                assert frame.landmarks.shape == (33, 4)

    def test_first_and_last_source_frames_are_preserved(self) -> None:
        """Resampling must include the phase endpoints — they define the
        full range of motion and must not be clipped away."""
        from autocoach.pose.normalizer import RuleBasedNormalizer

        norm = RuleBasedNormalizer()
        seq = _make_sequence(30)
        nps = norm.normalize(seq, _three_phases(30))
        first = nps.phases["descent"][0].landmarks[0, 0]
        last = nps.phases["ascent"][-1].landmarks[0, 0]
        assert first == pytest.approx(seq.frames[0].landmarks[0, 0], abs=0.01)
        assert last == pytest.approx(seq.frames[-1].landmarks[0, 0], abs=0.01)

    def test_interpolated_midpoint_is_average_of_endpoints(self) -> None:
        """Validates the linear interpolation: t=0.5 between frame A and frame B
        must equal (A + B) / 2 for every coordinate."""
        from autocoach.pose.normalizer import RuleBasedNormalizer

        norm = RuleBasedNormalizer()
        # Two-frame phase: values 0.0 and 1.0. Midpoint should be 0.5.
        frames = [_make_frame(0, 0.0), _make_frame(1, 1.0)]
        resampled = norm._resample_phase(frames, target_n=3)
        assert resampled[1].landmarks[0, 0] == pytest.approx(0.5, abs=0.01)

    def test_video_id_and_lift_type_propagated(self) -> None:
        """These labels travel the full pipeline to identify the output JSON."""
        from autocoach.pose.normalizer import RuleBasedNormalizer

        seq = PoseSequence(
            video_id="abc123", lift_type="Deadlift", frames=[_make_frame(i, 0.0) for i in range(30)]
        )
        nps = RuleBasedNormalizer().normalize(seq, _three_phases(30))
        assert nps.video_id == "abc123"
        assert nps.lift_type == "Deadlift"
