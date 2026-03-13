"""Qdrant vector store for lift coaching retrieval.

QdrantStore manages a single Qdrant collection that stores pose vectors
alongside coaching comments as payload. It supports:
- Indexing: BiomechanicalFeatures + comments → Qdrant point (upsert)
- Search: query features → top-k similar lifts, optionally filtered by lift_type
"""

from __future__ import annotations

import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    NamedVector,
    PointStruct,
    VectorParams,
)

from autocoach.pose.models import BiomechanicalFeatures
from autocoach.rag.embeddings import PoseEmbedder
from autocoach.rag.models import SearchResult


class QdrantStore:
    """Persistence and retrieval layer backed by Qdrant."""

    COLLECTION_NAME: str = "lift_coaching"
    VECTOR_NAME: str = "pose"

    def __init__(self, _client: QdrantClient | None = None) -> None:
        self._client = _client or QdrantClient(":memory:")
        self._embedder = PoseEmbedder()

    def ensure_collection(self) -> None:
        """Create the collection if it does not already exist (idempotent)."""
        collections = [c.name for c in self._client.get_collections().collections]
        if self.COLLECTION_NAME not in collections:
            self._client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config={
                    self.VECTOR_NAME: VectorParams(
                        size=PoseEmbedder.DIMENSION,
                        distance=Distance.COSINE,
                    ),
                },
            )

    def index(
        self,
        features: BiomechanicalFeatures,
        comments: list[str],
    ) -> None:
        """Upsert a lift's pose vector and comments into Qdrant."""
        vec = self._embedder.embed(features)
        point_id = self._video_id_to_point_id(features.video_id)

        self._client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[
                PointStruct(
                    id=point_id,
                    vector={self.VECTOR_NAME: vec.tolist()},
                    payload={
                        "video_id": features.video_id,
                        "lift_type": features.lift_type,
                        "comments": comments,
                    },
                ),
            ],
        )

    def search(
        self,
        features: BiomechanicalFeatures,
        limit: int = 5,
        lift_type: str | None = None,
    ) -> list[SearchResult]:
        """Find the most similar lifts by pose vector cosine similarity."""
        vec = self._embedder.embed(features)

        query_filter = None
        if lift_type is not None:
            query_filter = Filter(
                must=[FieldCondition(key="lift_type", match=MatchValue(value=lift_type))]
            )

        hits = self._client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=vec.tolist(),
            using=self.VECTOR_NAME,
            query_filter=query_filter,
            limit=limit,
        ).points

        return [
            SearchResult(
                video_id=hit.payload["video_id"],  # type: ignore[index]
                lift_type=hit.payload["lift_type"],  # type: ignore[index]
                comments=hit.payload["comments"],  # type: ignore[index]
                score=hit.score,
            )
            for hit in hits
        ]

    @staticmethod
    def _video_id_to_point_id(video_id: str) -> str:
        """Deterministic point ID from video_id for idempotent upsert."""
        return hashlib.md5(video_id.encode()).hexdigest()  # noqa: S324
