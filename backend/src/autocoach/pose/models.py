"""Data models for the pose processing pipeline.

Design split:
- ``Frame``, ``PoseSequence``, ``NormalizedPoseSequence``, ``PhaseSegment``
  are plain dataclasses because they hold ``numpy`` arrays and are internal
  processing structs that never leave the pipeline boundary.
- ``BiomechanicalFeatures`` is a Pydantic model because it is the pipeline's
  *output* — persisted to JSON, returned by the CLI, and later stored in the
  DB or blob store.  All its fields are plain Python types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, ConfigDict


@dataclass
class Frame:
    """One processed video frame — 33 MediaPipe pose landmarks."""

    index: int  # original frame index in the source video
    timestamp: float  # seconds from the start of the video
    landmarks: np.ndarray  # shape (33, 4): columns are [x, y, z, visibility]


@dataclass
class PoseSequence:
    """Raw pose sequence extracted from a video by MediaPipe."""

    video_id: str
    lift_type: str
    frames: list[Frame] = field(default_factory=list)


class ViewClass(StrEnum):
    """Three-tier camera angle classification (Option D design)."""

    SIDE_VIEW = "side_view"  # < ~30° off axis — angles are authoritative
    OBLIQUE = "oblique"  # 30–60° off axis — angles usable, confidence < 1
    FRONT_VIEW = "front_view"  # > ~60° off axis — reject, angles meaningless


@dataclass
class ViewClassification:
    """Output of ViewClassifier.classify().

    Intermediate result (not persisted), so a plain dataclass is fine.
    """

    view_class: ViewClass
    lateral_spread: float  # body-normalised spread: mean(|left_x-right_x|) / torso_height
    dominant_side: str  # "left" or "right" — whichever faces the camera
    view_confidence: float  # 1.0 = perfect side-on, 0.0 = front-facing


@dataclass
class PhaseSegment:
    """A contiguous range of frames representing one phase of the lift."""

    name: str  # "descent" | "bottom" | "ascent"
    start_idx: int  # index into PoseSequence.frames (inclusive)
    end_idx: int  # index into PoseSequence.frames (inclusive)


@dataclass
class NormalizedPoseSequence:
    """Pose sequence with phases detected and resampled to a canonical length.

    ``phases`` maps phase name → list of resampled Frame objects.  Each list
    has a fixed, predetermined length (set by RuleBasedNormalizer).
    """

    video_id: str
    lift_type: str
    phases: dict[str, list[Frame]] = field(default_factory=dict)


class BiomechanicalFeatures(BaseModel):
    """Per-frame joint angles derived from a NormalizedPoseSequence.

    Angles are in degrees.  Lists run across all phases in order
    (descent → bottom → ascent), so their length is always
    DESCENT_FRAMES + BOTTOM_FRAMES + ASCENT_FRAMES.
    """

    model_config = ConfigDict(frozen=True)

    video_id: str
    lift_type: str
    knee_angles: list[float]
    hip_angles: list[float]
    back_angles: list[float]
    min_knee_angle: float
    min_hip_angle: float
    max_back_angle: float
    phase_labels: list[str]  # "descent"|"bottom"|"ascent" per frame
    view_confidence: float  # 1.0 = authoritative, < 1.0 = oblique view
    dominant_side: str  # "left" or "right"
