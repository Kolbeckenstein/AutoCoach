"""Tests for PoseEmbedder.

PoseEmbedder converts BiomechanicalFeatures into a fixed-length numpy vector
that serves as the search key in Qdrant.  These tests verify the shape,
determinism, and sensitivity of that embedding — properties that directly
affect retrieval quality.

If the embedding silently changes shape, Qdrant inserts will fail.
If it's non-deterministic, identical lifts won't match.
If it's insensitive to real biomechanical differences, similar-form searches
return random lifts instead of useful coaching comparisons.
"""

from __future__ import annotations

import numpy as np
import pytest

from autocoach.pose.models import BiomechanicalFeatures

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOTAL_FRAMES = 40  # 16 descent + 8 bottom + 16 ascent
EXPECTED_DIM = TOTAL_FRAMES * 3  # knee + hip + back = 120


def _make_features(
    knee: float = 90.0,
    hip: float = 85.0,
    back: float = 30.0,
    lift_type: str = "Squat",
    video_id: str = "test_v",
) -> BiomechanicalFeatures:
    """Build a BiomechanicalFeatures with uniform angle values."""
    return BiomechanicalFeatures(
        video_id=video_id,
        lift_type=lift_type,
        knee_angles=[knee] * TOTAL_FRAMES,
        hip_angles=[hip] * TOTAL_FRAMES,
        back_angles=[back] * TOTAL_FRAMES,
        min_knee_angle=knee,
        min_hip_angle=hip,
        max_back_angle=back,
        phase_labels=["descent"] * 16 + ["bottom"] * 8 + ["ascent"] * 16,
        view_confidence=1.0,
        dominant_side="left",
    )


# ---------------------------------------------------------------------------
# Shape and type
# ---------------------------------------------------------------------------


class TestEmbeddingShape:
    def test_output_is_120_dim_float32(self) -> None:
        """Qdrant expects a fixed-size float32 vector.

        If the dimension changes, every previously indexed vector becomes
        incompatible and the entire collection must be rebuilt.
        """
        from autocoach.rag.embeddings import PoseEmbedder

        embedder = PoseEmbedder()
        vec = embedder.embed(_make_features())

        assert vec.shape == (EXPECTED_DIM,)
        assert vec.dtype == np.float32

    def test_dimension_constant_matches_output(self) -> None:
        """PoseEmbedder.DIMENSION must match the actual output length.

        Store creation uses DIMENSION to configure the Qdrant collection;
        a mismatch would cause silent insertion failures.
        """
        from autocoach.rag.embeddings import PoseEmbedder

        embedder = PoseEmbedder()
        vec = embedder.embed(_make_features())

        assert vec.shape[0] == PoseEmbedder.DIMENSION


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_features_produce_identical_vectors(self) -> None:
        """Identical lifts must produce identical embeddings.

        Non-determinism would cause the same video to land in different
        Qdrant regions on re-index, breaking deduplication and consistency.
        """
        from autocoach.rag.embeddings import PoseEmbedder

        embedder = PoseEmbedder()
        f = _make_features()

        np.testing.assert_array_equal(embedder.embed(f), embedder.embed(f))


# ---------------------------------------------------------------------------
# Concatenation order
# ---------------------------------------------------------------------------


class TestConcatenationOrder:
    def test_vector_is_knee_hip_back_concatenation(self) -> None:
        """The vector must be [knee_angles || hip_angles || back_angles].

        Order matters: if two embedders disagree on concatenation order,
        cosine similarity becomes meaningless — knee angles would be compared
        to hip angles from the other vector.
        """
        from autocoach.rag.embeddings import PoseEmbedder

        features = _make_features(knee=1.0, hip=2.0, back=3.0)
        embedder = PoseEmbedder()
        vec = embedder.embed(features)

        np.testing.assert_array_equal(vec[:TOTAL_FRAMES], 1.0)
        np.testing.assert_array_equal(vec[TOTAL_FRAMES : 2 * TOTAL_FRAMES], 2.0)
        np.testing.assert_array_equal(vec[2 * TOTAL_FRAMES :], 3.0)


# ---------------------------------------------------------------------------
# Sensitivity to biomechanical differences
# ---------------------------------------------------------------------------


class TestSensitivity:
    def test_different_knee_angles_produce_different_vectors(self) -> None:
        """Two lifts with different depth should not have the same embedding.

        If knee angle differences are lost, the retrieval system cannot
        distinguish a half squat from a deep squat — the core use case.
        """
        from autocoach.rag.embeddings import PoseEmbedder

        embedder = PoseEmbedder()
        shallow = embedder.embed(_make_features(knee=120.0))
        deep = embedder.embed(_make_features(knee=60.0))

        assert not np.array_equal(shallow, deep)

    def test_similar_lifts_are_closer_than_dissimilar_lifts(self) -> None:
        """Cosine similarity should rank biomechanically similar lifts higher.

        This is the fundamental retrieval guarantee: when a user submits a
        squat with 90° knees, the system should return lifts with similar
        angles — not random ones.
        """
        from autocoach.rag.embeddings import PoseEmbedder

        embedder = PoseEmbedder()
        query = embedder.embed(_make_features(knee=90.0, hip=85.0, back=30.0))
        similar = embedder.embed(_make_features(knee=92.0, hip=83.0, back=31.0))
        dissimilar = embedder.embed(_make_features(knee=140.0, hip=50.0, back=60.0))

        def cosine(a: np.ndarray, b: np.ndarray) -> float:
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

        assert cosine(query, similar) > cosine(query, dissimilar)
