"""Phase-based temporal normalizer for raw PoseSequences.

RuleBasedNormalizer implements the PoseNormalizer Protocol.  It:
1. Slices the raw frame list into descent / bottom / ascent segments
   (boundaries provided by PhaseDetector)
2. Resamples each segment to a fixed target frame count via linear
   interpolation of the (33, 4) landmark arrays
3. Returns a NormalizedPoseSequence ready for BiomechanicsExtractor

The Protocol design allows a v2 3D-lifting normalizer (MotionBERT /
VideoPose3D) to replace this class with zero changes to downstream code.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from autocoach.pose.models import Frame, NormalizedPoseSequence, PhaseSegment, PoseSequence

PHASE_ORDER = ("descent", "bottom", "ascent")


class PoseNormalizer(Protocol):
    """Swappable normalizer interface — v2 will implement 3D lifting here."""

    def normalize(
        self,
        sequence: PoseSequence,
        phases: list[PhaseSegment],
    ) -> NormalizedPoseSequence:
        ...


class RuleBasedNormalizer:
    """Resample each phase to a fixed frame count via linear interpolation.

    Default target frame counts per phase:
        descent : 16
        bottom  :  8
        ascent  : 16
    Total: 40 frames per video — fixed-length feature vector for the RAG layer.
    """

    PHASE_TARGET_FRAMES: dict[str, int] = {
        "descent": 16,
        "bottom": 8,
        "ascent": 16,
    }

    def normalize(
        self,
        sequence: PoseSequence,
        phases: list[PhaseSegment],
    ) -> NormalizedPoseSequence:
        """Slice and resample each phase; return a NormalizedPoseSequence."""
        result_phases: dict[str, list[Frame]] = {}
        for segment in phases:
            source_frames = sequence.frames[segment.start_idx : segment.end_idx + 1]
            target_n = self.PHASE_TARGET_FRAMES.get(segment.name, 16)
            result_phases[segment.name] = self._resample_phase(source_frames, target_n)

        return NormalizedPoseSequence(
            video_id=sequence.video_id,
            lift_type=sequence.lift_type,
            phases=result_phases,
        )

    def _resample_phase(self, frames: list[Frame], target_n: int) -> list[Frame]:
        """Linearly interpolate ``frames`` to exactly ``target_n`` frames.

        Uses ``np.interp`` on each of the 33×4 landmark coordinates so that
        the output is a smooth, evenly-spaced sample of the input.
        """
        n = len(frames)
        if n == 0:
            # Edge case: empty phase — return target_n copies of a zero frame
            lm = np.zeros((33, 4), dtype=np.float32)
            return [Frame(index=0, timestamp=0.0, landmarks=lm.copy()) for _ in range(target_n)]

        if n == target_n:
            return list(frames)

        # Source indices [0 … n-1], query positions evenly spaced over same range
        src_idx = np.arange(n, dtype=np.float64)
        query_idx = np.linspace(0.0, n - 1, target_n)

        # Stack landmarks: shape (n, 33, 4)
        stacked = np.stack([f.landmarks for f in frames], axis=0)

        resampled_frames: list[Frame] = []
        for qi, q in enumerate(query_idx):
            # Linear interpolation: find surrounding indices and blend
            lo = int(np.floor(q))
            hi = min(lo + 1, n - 1)
            t = q - lo
            blended = (1.0 - t) * stacked[lo] + t * stacked[hi]
            resampled_frames.append(
                Frame(
                    index=qi,
                    timestamp=float(np.interp(q, src_idx, [f.timestamp for f in frames])),
                    landmarks=blended.astype(np.float32),
                )
            )

        return resampled_frames
