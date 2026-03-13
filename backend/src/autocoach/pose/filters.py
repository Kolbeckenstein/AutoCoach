"""View quality classification for pose sequences.

Uses a three-tier system (Option D):
  SIDE_VIEW  — near-perpendicular to camera; joint angles are authoritative
  OBLIQUE    — up to ~60° off axis; angles usable, confidence < 1.0
  FRONT_VIEW — camera-facing or indeterminate; reject, angles meaningless

The dominant side (left/right) is determined by landmark visibility so
BiomechanicsExtractor always reads from the camera-facing side.

Normalisation note
------------------
Lateral spread is divided by torso height (|shoulder_y − hip_y|) so that the
thresholds describe body-proportional geometry rather than zoom-dependent pixel
distances.  This is an approximation — actual hip width varies between people
and focal length affects projection — but it is substantially more robust than
raw pixel spread.  The residual error is acceptable for Phase 2; v2 will
replace this classifier with a 3D pose lifting model (MotionBERT/VideoPose3D)
that produces camera-angle-agnostic joint positions.
"""

from __future__ import annotations

import numpy as np

from autocoach.pose.models import PoseSequence, ViewClass, ViewClassification

# Landmark indices (MediaPipe Pose, 33-point model)
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24

# Array column indices
_X = 0
_Y = 1
_VIS = 3

# Bilateral pairs used for lateral-spread computation.
# Knee is excluded because it moves substantially during the lift and would
# bias the mean spread toward the bottom position.
_SPREAD_PAIRS: list[tuple[int, int]] = [
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_SHOULDER, RIGHT_SHOULDER),
]


class ViewClassifier:
    """Classify camera angle using body-size-normalised lateral spread.

    ``lateral_spread = mean(|left_x − right_x|) / torso_height``

    Thresholds (normalised units):
        spread < SIDE_THRESHOLD  → SIDE_VIEW   (~0°–35° off axis)
        spread < FRONT_THRESHOLD → OBLIQUE     (~35°–60° off axis)
        otherwise               → FRONT_VIEW  (≥ 60° off axis, or invisible)

    view_confidence decays linearly: 1.0 at spread=0, 0.0 at FRONT_THRESHOLD.
    """

    SIDE_THRESHOLD: float = 0.3
    FRONT_THRESHOLD: float = 1.0
    MIN_VISIBILITY: float = 0.4

    def classify(self, sequence: PoseSequence) -> ViewClassification:
        """Return a ViewClassification for the given PoseSequence."""
        if not sequence.frames:
            return ViewClassification(
                view_class=ViewClass.FRONT_VIEW,
                lateral_spread=999.0,
                dominant_side="left",
                view_confidence=0.0,
            )

        spread = self._mean_lateral_spread(sequence)
        dominant_side = self._dominant_side(sequence)

        if not self._has_sufficient_visibility(sequence):
            return ViewClassification(
                view_class=ViewClass.FRONT_VIEW,
                lateral_spread=spread,
                dominant_side=dominant_side,
                view_confidence=0.0,
            )

        if spread < self.SIDE_THRESHOLD:
            view_class = ViewClass.SIDE_VIEW
        elif spread < self.FRONT_THRESHOLD:
            view_class = ViewClass.OBLIQUE
        else:
            view_class = ViewClass.FRONT_VIEW

        confidence = max(0.0, 1.0 - spread / self.FRONT_THRESHOLD)

        return ViewClassification(
            view_class=view_class,
            lateral_spread=spread,
            dominant_side=dominant_side,
            view_confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _mean_lateral_spread(self, sequence: PoseSequence) -> float:
        """Body-size-normalised lateral spread: mean(|left_x − right_x|) / torso_height.

        Torso height is the mean of left and right |shoulder_y − hip_y|, which
        converts raw pixel-space spread into a body-proportional ratio that is
        invariant to camera distance and subject size.
        """
        raw_spreads: list[float] = []
        torso_heights: list[float] = []

        for frame in sequence.frames:
            for left_idx, right_idx in _SPREAD_PAIRS:
                raw_spreads.append(
                    abs(
                        float(frame.landmarks[left_idx, _X]) - float(frame.landmarks[right_idx, _X])
                    )
                )
            left_torso = abs(
                float(frame.landmarks[LEFT_SHOULDER, _Y]) - float(frame.landmarks[LEFT_HIP, _Y])
            )
            right_torso = abs(
                float(frame.landmarks[RIGHT_SHOULDER, _Y]) - float(frame.landmarks[RIGHT_HIP, _Y])
            )
            torso_heights.append((left_torso + right_torso) / 2)

        if not raw_spreads:
            return 999.0

        mean_raw = float(np.mean(raw_spreads))
        mean_torso = max(float(np.mean(torso_heights)), 1e-6)
        return mean_raw / mean_torso

    def _dominant_side(self, sequence: PoseSequence) -> str:
        """Return 'left' or 'right' based on mean hip visibility.

        The camera-facing hip has higher MediaPipe visibility because the
        far-side hip is partially occluded by the torso in side-view footage.
        Defaults to 'left' on a tie (r/formcheck convention).
        """
        left_vis = float(np.mean([f.landmarks[LEFT_HIP, _VIS] for f in sequence.frames]))
        right_vis = float(np.mean([f.landmarks[RIGHT_HIP, _VIS] for f in sequence.frames]))
        return "right" if right_vis > left_vis else "left"

    def _has_sufficient_visibility(self, sequence: PoseSequence) -> bool:
        """True if mean hip visibility across frames meets the minimum threshold."""
        all_vis = [
            float(f.landmarks[LEFT_HIP, _VIS]) + float(f.landmarks[RIGHT_HIP, _VIS])
            for f in sequence.frames
        ]
        return (float(np.mean(all_vis)) / 2) >= self.MIN_VISIBILITY
