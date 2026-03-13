"""Tests for QdrantStore.

QdrantStore is the persistence and retrieval layer for the RAG system.
It indexes BiomechanicalFeatures as pose vectors in Qdrant and retrieves
similar lifts by cosine similarity, returning coaching comments from
the matched posts.

These tests verify the indexing, search, and filtering contracts that
downstream consumers (CLI batch-index, API search endpoint, LLM coaching
pipeline) depend on.

Unit tests use Qdrant's in-memory client so no external service is needed.
"""

from __future__ import annotations

import pytest

from autocoach.pose.models import BiomechanicalFeatures

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOTAL_FRAMES = 40  # 16 descent + 8 bottom + 16 ascent


def _make_features(
    video_id: str = "test_v",
    lift_type: str = "Squat",
    knee: float = 90.0,
    hip: float = 85.0,
    back: float = 30.0,
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


def _make_record(
    video_id: str = "test_v",
    lift_type: str = "Squat",
    comments: list[str] | None = None,
    knee: float = 90.0,
    hip: float = 85.0,
    back: float = 30.0,
) -> tuple[BiomechanicalFeatures, list[str]]:
    """Return (features, comments) pair for indexing."""
    features = _make_features(video_id=video_id, lift_type=lift_type, knee=knee, hip=hip, back=back)
    return features, comments or ["Good depth, but watch your knees."]


# ---------------------------------------------------------------------------
# Collection creation
# ---------------------------------------------------------------------------


class TestCollectionSetup:
    def test_ensure_collection_creates_collection(self) -> None:
        """QdrantStore must create the collection on first call.

        Without the collection, every index and search call would fail.
        The store should be safe to call multiple times (idempotent).
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()
        # Calling again should not raise
        store.ensure_collection()

    def test_collection_uses_cosine_distance(self) -> None:
        """Cosine similarity is the correct metric for angle-based vectors.

        Euclidean distance would weight absolute magnitude differences,
        making a 180° squat look closer to a 170° squat than a 90° one —
        cosine captures the shape of the angle curve instead.
        """
        from qdrant_client import QdrantClient

        from autocoach.rag.store import QdrantStore

        client = QdrantClient(":memory:")
        store = QdrantStore(_client=client)
        store.ensure_collection()

        collection_info = client.get_collection(store.COLLECTION_NAME)
        vectors_config = collection_info.config.params.vectors
        assert isinstance(vectors_config, dict)
        assert vectors_config["pose"].distance.name == "COSINE"


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------


class TestIndexing:
    def test_index_stores_point(self) -> None:
        """After indexing, the point should be retrievable by search.

        If indexing silently fails, the RAG system returns zero results
        and the LLM has no coaching context to work with.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        features, comments = _make_record(video_id="v1")
        store.index(features, comments)

        results = store.search(features, limit=1)
        assert len(results) == 1
        assert results[0].video_id == "v1"

    def test_index_stores_comments_as_payload(self) -> None:
        """Comments must survive the index → search round trip.

        The LLM coaching pipeline reads comments from search results;
        if they're lost during indexing, the LLM gets features but no
        human coaching context.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        features, comments = _make_record(
            video_id="v1", comments=["Push your knees out.", "Good depth."]
        )
        store.index(features, comments)

        results = store.search(features, limit=1)
        assert results[0].comments == ["Push your knees out.", "Good depth."]

    def test_index_stores_lift_type_in_payload(self) -> None:
        """lift_type must be stored for filtered search.

        Without it, a squat query could return deadlift coaching — useless
        or actively misleading advice.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        features, comments = _make_record(video_id="v1", lift_type="Deadlift")
        store.index(features, comments)

        results = store.search(features, limit=1)
        assert results[0].lift_type == "Deadlift"

    def test_index_multiple_points(self) -> None:
        """Multiple lifts can be indexed and all are searchable."""
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        for i in range(5):
            features, comments = _make_record(video_id=f"v{i}", knee=90.0 + i)
            store.index(features, comments)

        # Use the first one as query — should return all 5
        query_features = _make_features(video_id="v0", knee=90.0)
        results = store.search(query_features, limit=10)
        assert len(results) == 5


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_returns_most_similar_first(self) -> None:
        """Results must be ordered by cosine similarity (descending).

        The LLM prompt includes top-k results; wrong ordering means the
        most relevant coaching context gets pushed out of the context window.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        # Index three lifts with different knee angles
        for vid, knee in [("deep", 60.0), ("parallel", 90.0), ("quarter", 130.0)]:
            features, comments = _make_record(video_id=vid, knee=knee)
            store.index(features, comments)

        # Query with parallel squat — should match "parallel" first
        query = _make_features(knee=91.0)
        results = store.search(query, limit=3)
        assert results[0].video_id == "parallel"

    def test_search_respects_limit(self) -> None:
        """limit parameter must cap the number of returned results.

        Without this, large collections would return thousands of results
        and blow up the LLM context window.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        for i in range(10):
            features, comments = _make_record(video_id=f"v{i}", knee=90.0 + i * 0.1)
            store.index(features, comments)

        results = store.search(_make_features(), limit=3)
        assert len(results) == 3

    def test_search_returns_similarity_score(self) -> None:
        """Each result must include a similarity score for downstream ranking.

        The coaching pipeline uses this to weight how much trust to place
        in each retrieved example.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        features, comments = _make_record(video_id="v1")
        store.index(features, comments)

        results = store.search(features, limit=1)
        assert results[0].score is not None
        assert results[0].score > 0.0
        assert results[0].score == pytest.approx(1.0, abs=0.01)

    def test_search_empty_collection_returns_empty(self) -> None:
        """Searching before any indexing must return an empty list, not error.

        The CLI and API must handle the cold-start case gracefully.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        results = store.search(_make_features(), limit=5)
        assert results == []


# ---------------------------------------------------------------------------
# Filtered search
# ---------------------------------------------------------------------------


class TestFilteredSearch:
    def test_filter_by_lift_type(self) -> None:
        """Search must filter by lift_type when requested.

        Without filtering, a squat query returns deadlift examples —
        the coaching advice would be wrong and confusing.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        # Index squats and deadlifts
        for vid, lt in [("s1", "Squat"), ("s2", "Squat"), ("d1", "Deadlift")]:
            features, comments = _make_record(video_id=vid, lift_type=lt)
            store.index(features, comments)

        query = _make_features(lift_type="Squat")
        results = store.search(query, limit=10, lift_type="Squat")
        assert all(r.lift_type == "Squat" for r in results)
        assert len(results) == 2

    def test_filter_returns_empty_when_no_match(self) -> None:
        """Filtering for a non-existent lift_type returns empty, not error."""
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        features, comments = _make_record(lift_type="Squat")
        store.index(features, comments)

        results = store.search(features, limit=5, lift_type="Bench Press")
        assert results == []


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    def test_reindex_same_video_updates_not_duplicates(self) -> None:
        """Re-indexing the same video_id must update, not create a duplicate.

        Without idempotent upsert, re-processing a video doubles its weight
        in search results.
        """
        from autocoach.rag.store import QdrantStore

        store = QdrantStore()
        store.ensure_collection()

        features, _ = _make_record(video_id="v1")
        store.index(features, ["Old comment"])
        store.index(features, ["New comment"])

        results = store.search(features, limit=10)
        assert len(results) == 1
        assert results[0].comments == ["New comment"]
