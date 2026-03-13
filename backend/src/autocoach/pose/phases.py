"""Phase detection for a raw PoseSequence.

Detects three temporal phases of a powerlifting movement:
  descent — from standing to maximum depth
  bottom  — the window around maximum depth (most diagnostically important)
  ascent  — from maximum depth back to standing

Detection uses the hip-knee depth ratio: ``hip_y - knee_y`` (MediaPipe y
increases downward, so a positive ratio means the hip has descended below
the knee — the deepest point).
"""

from __future__ import annotations

import numpy as np

from autocoach.pose.models import PhaseSegment, PoseSequence

# Landmark indices
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26

# y-coordinate column
_Y = 1

# Minimum number of frames required for meaningful phase detection
MIN_FRAMES = 10

# Half-width of the "bottom" window centred on argmax(depth_ratio)
BOTTOM_HALF_WIDTH = 2


class PhaseDetector:
    """Detect descent / bottom / ascent phases from a raw PoseSequence."""

    def detect(self, sequence: PoseSequence) -> list[PhaseSegment]:
        """Return [descent, bottom, ascent] PhaseSegments in temporal order.

        Raises:
            ValueError: if the sequence has too few frames to analyse.
        """
        if len(sequence.frames) < MIN_FRAMES:
            raise ValueError(
                f"too few frames to detect phases: {len(sequence.frames)} "
                f"(minimum {MIN_FRAMES})"
            )

        ratios = self._depth_ratio_series(sequence)
        smoothed = self._smooth(ratios)
        bottom_idx = int(np.argmax(smoothed))

        # Bottom window: ±BOTTOM_HALF_WIDTH frames around the deepest frame,
        # clamped to valid indices
        bottom_start = max(0, bottom_idx - BOTTOM_HALF_WIDTH)
        bottom_end = min(len(sequence.frames) - 1, bottom_idx + BOTTOM_HALF_WIDTH)

        # Ensure descent and ascent each have at least one frame
        descent_start = 0
        descent_end = max(0, bottom_start - 1)
        ascent_start = min(len(sequence.frames) - 1, bottom_end + 1)
        ascent_end = len(sequence.frames) - 1

        # If bottom ate into the start or end, collapse gracefully
        if descent_end < descent_start:
            descent_end = descent_start
            bottom_start = descent_start + 1

        if ascent_start > ascent_end:
            ascent_start = ascent_end
            bottom_end = ascent_end - 1

        return [
            PhaseSegment(name="descent", start_idx=descent_start, end_idx=descent_end),
            PhaseSegment(name="bottom", start_idx=bottom_start, end_idx=bottom_end),
            PhaseSegment(name="ascent", start_idx=ascent_start, end_idx=ascent_end),
        ]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _depth_ratio_series(self, sequence: PoseSequence) -> np.ndarray:
        """Compute mean_hip_y − mean_knee_y for every frame.

        Positive = hip below knee (at or past parallel).
        """
        ratios = []
        for frame in sequence.frames:
            hip_y = (
                float(frame.landmarks[LEFT_HIP, _Y]) + float(frame.landmarks[RIGHT_HIP, _Y])
            ) / 2
            knee_y = (
                float(frame.landmarks[LEFT_KNEE, _Y]) + float(frame.landmarks[RIGHT_KNEE, _Y])
            ) / 2
            ratios.append(hip_y - knee_y)
        return np.array(ratios, dtype=np.float64)

    def _smooth(self, series: np.ndarray, window: int = 5) -> np.ndarray:
        """Apply a median filter to reduce landmark jitter."""
        if len(series) < window:
            return series
        # np.lib.stride_tricks for a rolling window
        half = window // 2
        padded = np.pad(series, half, mode="edge")
        shape = (len(series), window)
        strides = (padded.strides[0], padded.strides[0])
        windows = np.lib.stride_tricks.as_strided(padded, shape=shape, strides=strides)
        result: np.ndarray = np.median(windows, axis=1)
        return result
