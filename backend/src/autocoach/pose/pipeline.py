"""Thin orchestrator for the full pose processing pipeline.

Input:  video file path + lift_type string
Output: BiomechanicalFeatures (Pydantic, JSON-serialisable)

Stages
------
1. PoseExtractor        → PoseSequence          (MediaPipe landmark extraction)
2. ViewClassifier       → ViewClassification    (camera angle + dominant side)
3. PhaseDetector        → [PhaseSegment]        (descent / bottom / ascent)
4. RuleBasedNormalizer  → NormalizedPoseSequence (fixed-length resampling)
5. BiomechanicsExtractor → BiomechanicalFeatures (joint angles)

BiomechanicsExtractor sets view_confidence=1.0 by default; the pipeline
overwrites it with the real value from ViewClassification so downstream
consumers can weight retrieval results by view quality.
"""

from __future__ import annotations

from pathlib import Path

from autocoach.pose.biomechanics import BiomechanicsExtractor
from autocoach.pose.extractor import PoseExtractor
from autocoach.pose.filters import ViewClassifier
from autocoach.pose.models import BiomechanicalFeatures, ViewClass
from autocoach.pose.normalizer import RuleBasedNormalizer
from autocoach.pose.phases import PhaseDetector


class PipelineError(Exception):
    """Raised when the pipeline cannot process a video.

    Covers bad camera angle, sequences too short for phase detection, and
    similar domain-level failures.  Low-level I/O failures surface as
    :exc:`~autocoach.pose.extractor.PoseExtractionError` instead.
    """


class PosePipeline:
    """Run all pose processing stages end-to-end.

    Parameters
    ----------
    model_path:
        Path to the MediaPipe PoseLandmarker ``.task`` file.  Passed through
        to :class:`PoseExtractor`; defaults to
        ``backend/models/pose_landmarker_full.task``.
    reject_front_view:
        If ``True`` (default), raise :exc:`PipelineError` for FRONT_VIEW
        videos rather than returning low-confidence features.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        reject_front_view: bool = True,
    ) -> None:
        self._extractor = PoseExtractor(model_path=model_path)
        self._classifier = ViewClassifier()
        self._detector = PhaseDetector()
        self._normalizer = RuleBasedNormalizer()
        self._biomechanics = BiomechanicsExtractor()
        self._reject_front_view = reject_front_view

    def process(
        self,
        video_path: Path,
        video_id: str | None = None,
        lift_type: str = "Squat",
    ) -> BiomechanicalFeatures:
        """Run the full pipeline on a video file.

        Parameters
        ----------
        video_path:
            Path to the input video.
        video_id:
            Identifier stored in the returned features.  Defaults to the
            file stem (e.g. ``"abc123"`` for ``"abc123.mp4"``).
        lift_type:
            Lift type label stored in the returned features.

        Returns
        -------
        BiomechanicalFeatures
            Pydantic model with joint angles, summary statistics, and view
            metadata.

        Raises
        ------
        PoseExtractionError
            If the model or video file is missing (user-actionable message).
        PipelineError
            If the view is FRONT_VIEW (when *reject_front_view* is ``True``)
            or if phase detection fails (e.g. sequence too short).
        """
        vid_id = video_id or video_path.stem

        # Stage 1 — extract landmarks (PoseExtractionError propagates as-is)
        sequence = self._extractor.extract(video_path, vid_id, lift_type)

        # Stage 2 — classify view angle
        view = self._classifier.classify(sequence)
        if self._reject_front_view and view.view_class == ViewClass.FRONT_VIEW:
            raise PipelineError(
                f"Video rejected: camera angle is too frontal "
                f"(normalised spread={view.lateral_spread:.2f}, "
                f"threshold={self._classifier.FRONT_THRESHOLD}). "
                "Re-film from the side."
            )

        # Stage 3 — detect phases
        try:
            phases = self._detector.detect(sequence)
        except ValueError as exc:
            raise PipelineError(f"Phase detection failed: {exc}") from exc

        # Stage 4 — resample to fixed frame counts
        normalized = self._normalizer.normalize(sequence, phases)

        # Stage 5 — extract joint angles
        features = self._biomechanics.extract(normalized, dominant_side=view.dominant_side)

        # Overwrite the default view_confidence=1.0 with the real classifier value
        return features.model_copy(update={"view_confidence": view.view_confidence})
