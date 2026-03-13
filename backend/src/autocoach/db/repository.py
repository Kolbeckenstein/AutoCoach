"""Data-access layer for scraped post and comment metadata."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from autocoach.db.models import CommentRecord, PostRecord
from autocoach.scrapers.reddit.models import LiftPost


class PostRepository:
    """Persist and query LiftPost metadata in a relational database.

    Callers are responsible for managing the session lifecycle (commit/rollback).
    Each mutating method commits immediately so the caller doesn't need to know
    the internals; read methods are plain SELECTs.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save(self, post: LiftPost) -> None:
        """Upsert a LiftPost and fully replace its comments.

        If the post already exists it is deleted and re-inserted so that
        comments are always in sync with the source data (no stale entries).
        """
        existing = self._session.get(PostRecord, post.id)
        if existing is not None:
            self._session.delete(existing)
            self._session.flush()

        record = PostRecord(
            id=post.id,
            lift_type=post.lift_type,
            title=post.title,
            video_url=str(post.video_url),
            video_path=post.video_path,
            author=post.author,
            post_score=post.post_score,
            created_utc=post.created_utc,
            scraped_at=datetime.now(UTC),
            comments=[
                CommentRecord(
                    id=c.id,
                    post_id=post.id,
                    body=c.body,
                    score=c.score,
                    author=c.author,
                    created_utc=c.created_utc,
                    is_top_level=c.is_top_level,
                )
                for c in post.comments
            ],
        )
        self._session.add(record)
        self._session.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_seen_ids(self) -> set[str]:
        """Return the set of all post IDs currently stored in the database."""
        rows = self._session.query(PostRecord.id).all()
        return {row[0] for row in rows}

    def count(self, lift_type: str | None = None) -> int:
        """Count stored posts, optionally filtered by lift type."""
        q = self._session.query(PostRecord)
        if lift_type is not None:
            q = q.filter(PostRecord.lift_type == lift_type)
        return q.count()
