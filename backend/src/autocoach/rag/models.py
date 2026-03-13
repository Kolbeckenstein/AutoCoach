"""Data models for the RAG layer."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SearchResult(BaseModel):
    """A single result from a pose-similarity search."""

    model_config = ConfigDict(frozen=True)

    video_id: str
    lift_type: str
    comments: list[str]
    score: float
