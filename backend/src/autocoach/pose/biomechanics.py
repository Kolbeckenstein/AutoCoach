"""Biomechanical feature extraction from NormalizedPoseSequences.

Computes three joint angles per frame using 2D (x, y) coordinates only:
  knee_angle  — Hip → Knee → Ankle  (180° = straight, ~90° = parallel depth)
  hip_angle   — Shoulder → Hip → Knee  (180° = standing, ~90° = horizontal back)
  back_angle  — Inclination of Shoulder→Hip vector from vertical (0° = upright)

The ``dominant_side`` parameter (from ViewClassifier) selects which side's
landmarks to use so the camera-facing side is always preferred.
"""

from __future__ import annotations

import numpy as np

from autocoach.pose.models import BiomechanicalFeatures, Frame, NormalizedPoseSequence

# MediaPipe landmark indices
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28

# Axis indices in the (33, 4) array
_X = 0
_Y = 1

# Phase order for concatenation — must match NormalizedPoseSequence convention
PHASE_ORDER = ("descent", "bottom", "ascent")

# Upward vertical in MediaPipe image coords (y=0 at top, increases downward)
_UP = np.array([0.0, -1.0])


class BiomechanicsExtractor:
    """Compute joint angles from a NormalizedPoseSequence."""

    def extract(
        self,
        sequence: NormalizedPoseSequence,
        dominant_side: str = "left",
    ) -> BiomechanicalFeatures:
        """Return BiomechanicalFeatures for all phases concatenated in order."""
        knee_angles: list[float] = []
        hip_angles: list[float] = []
        back_angles: list[float] = []
        phase_labels: list[str] = []

        for phase_name in PHASE_ORDER:
            for frame in sequence.phases.get(phase_name, []):
                knee_angles.append(self._knee_angle(frame, dominant_side))
                hip_angles.append(self._hip_angle(frame, dominant_side))
                back_angles.append(self._back_angle(frame, dominant_side))
                phase_labels.append(phase_name)

        return BiomechanicalFeatures(
            video_id=sequence.video_id,
            lift_type=sequence.lift_type,
            knee_angles=knee_angles,
            hip_angles=hip_angles,
            back_angles=back_angles,
            min_knee_angle=float(min(knee_angles)) if knee_angles else 0.0,
            min_hip_angle=float(min(hip_angles)) if hip_angles else 0.0,
            max_back_angle=float(max(back_angles)) if back_angles else 0.0,
            phase_labels=phase_labels,
            view_confidence=1.0,  # caller should override from ViewClassification
            dominant_side=dominant_side,
        )

    # ------------------------------------------------------------------
    # Per-frame angle helpers
    # ------------------------------------------------------------------

    def _knee_angle(self, frame: Frame, side: str) -> float:
        """Angle at the knee joint: Hip → Knee → Ankle (degrees, 2D)."""
        hip_idx, knee_idx, ankle_idx = (
            (LEFT_HIP, LEFT_KNEE, LEFT_ANKLE)
            if side == "left"
            else (RIGHT_HIP, RIGHT_KNEE, RIGHT_ANKLE)
        )
        return self._angle_at_vertex(
            frame.landmarks[hip_idx, :2],
            frame.landmarks[knee_idx, :2],
            frame.landmarks[ankle_idx, :2],
        )

    def _hip_angle(self, frame: Frame, side: str) -> float:
        """Angle at the hip joint: Shoulder → Hip → Knee (degrees, 2D)."""
        shoulder_idx, hip_idx, knee_idx = (
            (LEFT_SHOULDER, LEFT_HIP, LEFT_KNEE)
            if side == "left"
            else (RIGHT_SHOULDER, RIGHT_HIP, RIGHT_KNEE)
        )
        return self._angle_at_vertex(
            frame.landmarks[shoulder_idx, :2],
            frame.landmarks[hip_idx, :2],
            frame.landmarks[knee_idx, :2],
        )

    def _back_angle(self, frame: Frame, side: str) -> float:
        """Torso inclination from vertical: angle between Hip→Shoulder and (0, -1).

        0° = perfectly upright. Increases with forward lean.
        """
        hip_idx, shoulder_idx = (
            (LEFT_HIP, LEFT_SHOULDER) if side == "left" else (RIGHT_HIP, RIGHT_SHOULDER)
        )
        hip = frame.landmarks[hip_idx, :2].astype(np.float64)
        shoulder = frame.landmarks[shoulder_idx, :2].astype(np.float64)
        torso_vec = shoulder - hip
        norm = np.linalg.norm(torso_vec)
        if norm < 1e-9:
            return 0.0
        torso_unit = torso_vec / norm
        cos_theta = np.clip(np.dot(torso_unit, _UP), -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_theta)))

    def _angle_at_vertex(
        self,
        a: np.ndarray,  # (2,) — point A
        b: np.ndarray,  # (2,) — vertex B
        c: np.ndarray,  # (2,) — point C
    ) -> float:
        """Return the angle in degrees at vertex B formed by rays BA and BC."""
        ba = a.astype(np.float64) - b.astype(np.float64)
        bc = c.astype(np.float64) - b.astype(np.float64)
        norm_ba = np.linalg.norm(ba)
        norm_bc = np.linalg.norm(bc)
        if norm_ba < 1e-9 or norm_bc < 1e-9:
            return 0.0
        cos_theta = np.clip(np.dot(ba, bc) / (norm_ba * norm_bc), -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_theta)))
