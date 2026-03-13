"""Unit tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy import inspect

from autocoach.db.models import Base, CommentRecord, PostRecord

pytestmark = pytest.mark.unit


class TestPostRecord:
    def test_tablename(self) -> None:
        assert PostRecord.__tablename__ == "posts"

    def test_has_required_columns(self) -> None:
        cols = {c.key for c in inspect(PostRecord).mapper.column_attrs}
        assert {
            "id",
            "lift_type",
            "title",
            "video_url",
            "author",
            "post_score",
            "created_utc",
            "scraped_at",
        }.issubset(cols)

    def test_video_path_is_nullable(self) -> None:
        col = PostRecord.__table__.c["video_path"]
        assert col.nullable

    def test_id_is_primary_key(self) -> None:
        col = PostRecord.__table__.c["id"]
        assert col.primary_key

    def test_has_comments_relationship(self) -> None:
        assert hasattr(PostRecord, "comments")


class TestCommentRecord:
    def test_tablename(self) -> None:
        assert CommentRecord.__tablename__ == "comments"

    def test_has_required_columns(self) -> None:
        cols = {c.key for c in inspect(CommentRecord).mapper.column_attrs}
        assert {"id", "post_id", "body", "score", "author", "created_utc", "is_top_level"}.issubset(
            cols
        )

    def test_post_id_is_foreign_key(self) -> None:
        col = CommentRecord.__table__.c["post_id"]
        assert len(col.foreign_keys) == 1
        fk = next(iter(col.foreign_keys))
        assert fk.column.table.name == "posts"

    def test_has_post_relationship(self) -> None:
        assert hasattr(CommentRecord, "post")


class TestBaseMetadata:
    def test_base_has_both_tables(self) -> None:
        assert set(Base.metadata.tables.keys()) == {"posts", "comments"}
