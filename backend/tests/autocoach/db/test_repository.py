"""Unit tests for PostRepository using an in-memory SQLite database."""

from collections.abc import Generator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from autocoach.db.models import Base
from autocoach.db.repository import PostRepository
from autocoach.scrapers.reddit.models import Comment, LiftPost

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def session() -> Generator[Session, None, None]:
    """Provide a fresh SQLite in-memory session per test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    sess = SessionLocal()
    yield sess
    sess.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def repo(session: Session) -> PostRepository:
    return PostRepository(session)


def _make_post(
    post_id: str = "abc123",
    lift_type: str = "Squat",
    post_score: int = 20,
    n_comments: int = 3,
) -> LiftPost:
    comments = [
        Comment(
            id=f"{post_id}_c{i}",
            body=f"Comment {i}",
            score=10,
            author=f"user{i}",
            created_utc=datetime(2024, 1, 1, 12, 0, 0),
        )
        for i in range(n_comments)
    ]
    return LiftPost(
        id=post_id,
        lift_type=lift_type,
        title=f"{lift_type} form check",
        video_url="https://v.redd.it/abc/DASH_720.mp4",
        created_utc=datetime(2024, 1, 1, 10, 0, 0),
        author="lifter",
        post_score=post_score,
        comments=comments,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPostRepositorySave:
    def test_save_persists_post(self, repo: PostRepository, session: Session) -> None:
        post = _make_post()
        repo.save(post)

        from autocoach.db.models import PostRecord

        record = session.get(PostRecord, "abc123")
        assert record is not None
        assert record.lift_type == "Squat"
        assert record.post_score == 20

    def test_save_persists_all_comments(self, repo: PostRepository, session: Session) -> None:
        post = _make_post(n_comments=3)
        repo.save(post)

        from autocoach.db.models import CommentRecord

        comments = session.query(CommentRecord).filter_by(post_id="abc123").all()
        assert len(comments) == 3

    def test_save_stores_video_url_as_string(self, repo: PostRepository, session: Session) -> None:
        post = _make_post()
        repo.save(post)

        from autocoach.db.models import PostRecord

        record = session.get(PostRecord, "abc123")
        assert record is not None
        assert isinstance(record.video_url, str)
        assert "redd.it" in record.video_url

    def test_save_upserts_on_duplicate_id(self, repo: PostRepository) -> None:
        post = _make_post(post_score=10)
        repo.save(post)

        updated = _make_post(post_score=99)
        repo.save(updated)  # should not raise

        from autocoach.db.models import PostRecord

        # Need a fresh query — reuse the session via the repo
        record = repo._session.get(PostRecord, "abc123")
        assert record is not None
        assert record.post_score == 99

    def test_upsert_replaces_comments(self, repo: PostRepository, session: Session) -> None:
        repo.save(_make_post(n_comments=5))
        repo.save(_make_post(n_comments=2))  # fewer comments on re-scrape

        from autocoach.db.models import CommentRecord

        comments = session.query(CommentRecord).filter_by(post_id="abc123").all()
        assert len(comments) == 2


class TestPostRepositoryGetSeenIds:
    def test_empty_when_no_posts(self, repo: PostRepository) -> None:
        assert repo.get_seen_ids() == set()

    def test_returns_saved_post_id(self, repo: PostRepository) -> None:
        repo.save(_make_post(post_id="xyz99"))
        assert "xyz99" in repo.get_seen_ids()

    def test_returns_all_post_ids(self, repo: PostRepository) -> None:
        repo.save(_make_post(post_id="p1"))
        repo.save(_make_post(post_id="p2"))
        repo.save(_make_post(post_id="p3"))
        assert repo.get_seen_ids() == {"p1", "p2", "p3"}


class TestPostRepositoryCount:
    def test_zero_when_empty(self, repo: PostRepository) -> None:
        assert repo.count() == 0

    def test_counts_all_posts(self, repo: PostRepository) -> None:
        repo.save(_make_post(post_id="p1", lift_type="Squat"))
        repo.save(_make_post(post_id="p2", lift_type="Deadlift"))
        assert repo.count() == 2

    def test_filters_by_lift_type(self, repo: PostRepository) -> None:
        repo.save(_make_post(post_id="p1", lift_type="Squat"))
        repo.save(_make_post(post_id="p2", lift_type="Squat"))
        repo.save(_make_post(post_id="p3", lift_type="Deadlift"))
        assert repo.count(lift_type="Squat") == 2
        assert repo.count(lift_type="Deadlift") == 1
        assert repo.count(lift_type="Bench Press") == 0
