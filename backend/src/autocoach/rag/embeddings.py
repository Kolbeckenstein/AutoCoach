"""Pose embedding for vector search.

PoseEmbedder converts BiomechanicalFeatures into a fixed-length numpy vector
by concatenating the normalised angle time series: [knee || hip || back].

The resulting 120-dimensional vector (40 frames x 3 angle types) serves as
the search key in Qdrant for finding biomechanically similar lifts.
"""

from __future__ import annotations

import numpy as np

from autocoach.pose.models import BiomechanicalFeatures


class PoseEmbedder:
    """Convert BiomechanicalFeatures to a fixed-size pose vector."""

    DIMENSION: int = 120  # 40 knee + 40 hip + 40 back

    def embed(self, features: BiomechanicalFeatures) -> np.ndarray:
        """Return a (120,) float32 vector: [knee_angles || hip_angles || back_angles]."""
        vec = np.concatenate([
            features.knee_angles,
            features.hip_angles,
            features.back_angles,
        ])
        return vec.astype(np.float32)
