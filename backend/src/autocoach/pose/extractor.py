"""Extract pose sequences from video files using the MediaPipe Tasks API.

Uses PoseLandmarker in VIDEO running mode so temporal tracking is preserved
across frames without the overhead of LIVE mode.

MediaPipe Tasks API note (v0.10+)
----------------------------------
``mp.solutions.pose`` was removed in v0.10.  The replacement is:
    mediapipe.tasks.python.vision.PoseLandmarker
    mediapipe.tasks.python.vision.RunningMode.VIDEO
    landmarker.detect_for_video(mp_image, timestamp_ms)

Timestamps must be strictly monotonically increasing; we derive them from the
frame index and video FPS rather than from cap.get(CAP_PROP_POS_MSEC) because
many codecs return 0 for every frame via that property.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import RunningMode

from autocoach.pose.models import Frame, PoseSequence

# Default model path: <repo>/backend/models/pose_landmarker_full.task
_DEFAULT_MODEL = Path(__file__).parent.parent.parent.parent / "models" / "pose_landmarker_full.task"


class PoseExtractionError(Exception):
    """Raised when extraction fails (model missing, unreadable video, etc.)."""


class PoseExtractor:
    """Extract MediaPipe 33-point pose landmarks from a video file.

    Parameters
    ----------
    model_path:
        Path to a MediaPipe PoseLandmarker ``.task`` file.
        Defaults to ``backend/models/pose_landmarker_full.task``.
    min_pose_detection_confidence:
        Minimum score for the initial pose-detection model.
    min_pose_presence_confidence:
        Minimum score for the pose-presence model on subsequent frames.
    min_tracking_confidence:
        Minimum score to continue tracking without re-running detection.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        min_pose_detection_confidence: float = 0.5,
        min_pose_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self._model_path = model_path or _DEFAULT_MODEL
        self._det_conf = min_pose_detection_confidence
        self._pres_conf = min_pose_presence_confidence
        self._track_conf = min_tracking_confidence

    def extract(self, video_path: Path, video_id: str, lift_type: str) -> PoseSequence:
        """Run MediaPipe on *video_path* and return a :class:`PoseSequence`.

        Parameters
        ----------
        video_path:
            Path to the input video (mp4, mov, avi, …).
        video_id:
            Identifier stored on the returned :class:`PoseSequence`.
        lift_type:
            Lift type label (e.g. ``"Squat"``) stored on the sequence.

        Raises
        ------
        PoseExtractionError
            If the model file is missing, the video cannot be opened, or
            zero frames were read.
        """
        if not self._model_path.exists():
            raise PoseExtractionError(
                f"MediaPipe model not found: {self._model_path}\n"
                "Run `make download-models` (or `make -C backend download-models`) "
                "to fetch the model file."
            )
        if not video_path.exists():
            raise PoseExtractionError(f"Video file not found: {video_path}")

        options = vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(self._model_path)),
            running_mode=RunningMode.VIDEO,
            min_pose_detection_confidence=self._det_conf,
            min_pose_presence_confidence=self._pres_conf,
            min_tracking_confidence=self._track_conf,
        )

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise PoseExtractionError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames: list[Frame] = []

        try:
            with vision.PoseLandmarker.create_from_options(options) as landmarker:
                frame_idx = 0
                while True:
                    ok, bgr = cap.read()
                    if not ok:
                        break

                    # Derive timestamp from frame index — more reliable than
                    # CAP_PROP_POS_MSEC which returns 0 on many codecs.
                    timestamp_ms = int(frame_idx * 1000 / fps)

                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(mp_image, timestamp_ms)

                    if result.pose_landmarks:
                        lm_list = result.pose_landmarks[0]  # first (only) person
                        landmarks = np.array(
                            [[lm.x, lm.y, lm.z, lm.visibility] for lm in lm_list],
                            dtype=np.float32,
                        )
                    else:
                        # No detection this frame — zero-fill so frame indices stay stable
                        landmarks = np.zeros((33, 4), dtype=np.float32)

                    frames.append(
                        Frame(
                            index=frame_idx,
                            timestamp=timestamp_ms / 1000.0,
                            landmarks=landmarks,
                        )
                    )
                    frame_idx += 1
        finally:
            cap.release()

        if not frames:
            raise PoseExtractionError(f"No frames extracted from: {video_path}")

        return PoseSequence(video_id=video_id, lift_type=lift_type, frames=frames)
