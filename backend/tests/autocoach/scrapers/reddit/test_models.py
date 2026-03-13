"""Unit tests for data models.

This demonstrates TDD:
1. Write failing tests first
2. Implement code to make tests pass
3. Refactor while keeping tests green
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from autocoach.scrapers.reddit.models import Comment, LiftPost

pytestmark = pytest.mark.unit


class TestComment:
    """Test Comment model."""

    def test_create_valid_comment(self) -> None:
        """Test creating a valid comment."""
        comment = Comment(
            id="abc123",
            body="Your knees are caving in. Try pushing them out.",
            score=42,
            author="expert_coach",
            created_utc=datetime(2024, 1, 15, 12, 0, 0),
            is_top_level=True,
        )

        assert comment.id == "abc123"
        assert "knees" in comment.body
        assert comment.score == 42
        assert comment.author == "expert_coach"

    def test_comment_is_immutable(self) -> None:
        """Test that comments are frozen (immutable)."""
        comment = Comment(
            id="abc123",
            body="Test comment",
            score=10,
            author="test_user",
            created_utc=datetime.now(),
        )

        with pytest.raises(ValidationError):
            comment.score = 99  # type: ignore[misc]

    def test_comment_requires_all_fields(self) -> None:
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            Comment(  # type: ignore[call-arg]
                id="abc123",
                body="Test",
                # Missing: score, author, created_utc
            )

        error_dict = exc_info.value.errors()
        missing_fields = {err["loc"][0] for err in error_dict}
        assert "score" in missing_fields
        assert "author" in missing_fields
        assert "created_utc" in missing_fields

    def test_is_top_level_defaults_to_true(self) -> None:
        """Test that is_top_level defaults to True."""
        comment = Comment(
            id="abc123",
            body="Test",
            score=5,
            author="user",
            created_utc=datetime.now(),
        )

        assert comment.is_top_level is True


class TestLiftPost:
    """Test LiftPost model."""

    def test_create_valid_lift_post(self) -> None:
        """Test creating a valid lift post."""
        post = LiftPost(
            id="xyz789",
            lift_type="Squat",
            title="Form check - 225lbs squat",
            video_url="https://v.redd.it/abc123/DASH_720.mp4",
            created_utc=datetime(2024, 1, 15, 12, 0, 0),
            author="lifter123",
            post_score=15,
            comments=[],
        )

        assert post.id == "xyz789"
        assert post.lift_type == "Squat"
        assert "225lbs" in post.title
        assert post.post_score == 15

    def test_lift_post_with_comments(self) -> None:
        """Test lift post with multiple comments."""
        comments = [
            Comment(
                id="c1",
                body="Good depth!",
                score=20,
                author="coach1",
                created_utc=datetime.now(),
            ),
            Comment(
                id="c2",
                body="Knees caving in",
                score=15,
                author="coach2",
                created_utc=datetime.now(),
            ),
            Comment(
                id="c3",
                body="Nice lift",
                score=2,
                author="random",
                created_utc=datetime.now(),
            ),
        ]

        post = LiftPost(
            id="xyz789",
            lift_type="Squat",
            title="Form check",
            video_url="https://v.redd.it/abc123/DASH_720.mp4",
            created_utc=datetime.now(),
            author="lifter",
            post_score=10,
            comments=comments,
        )

        assert len(post.comments) == 3

    def test_top_comments_filters_by_score(self) -> None:
        """Test that top_comments returns only high-scoring comments."""
        comments = [
            Comment(id="c1", body="Great!", score=20, author="a", created_utc=datetime.now()),
            Comment(id="c2", body="Good", score=10, author="b", created_utc=datetime.now()),
            Comment(id="c3", body="Okay", score=2, author="c", created_utc=datetime.now()),
        ]

        post = LiftPost(
            id="xyz",
            lift_type="Squat",
            title="Test",
            video_url="https://v.redd.it/test/DASH_720.mp4",
            created_utc=datetime.now(),
            author="user",
            post_score=5,
            comments=comments,
        )

        top = post.top_comments(min_score=5)
        assert len(top) == 2
        assert all(c.score >= 5 for c in top)

    def test_has_quality_feedback_true(self) -> None:
        """Test that has_quality_feedback returns True with enough good comments."""
        comments = [
            Comment(
                id=f"c{i}", body=f"Comment {i}", score=10, author="a", created_utc=datetime.now()
            )
            for i in range(5)
        ]

        post = LiftPost(
            id="xyz",
            lift_type="Squat",
            title="Test",
            video_url="https://v.redd.it/test/DASH_720.mp4",
            created_utc=datetime.now(),
            author="user",
            post_score=5,
            comments=comments,
        )

        assert post.has_quality_feedback is True

    def test_has_quality_feedback_false(self) -> None:
        """Test that has_quality_feedback returns False with insufficient comments."""
        comments = [
            Comment(id="c1", body="Okay", score=2, author="a", created_utc=datetime.now()),
            Comment(id="c2", body="Nice", score=3, author="b", created_utc=datetime.now()),
        ]

        post = LiftPost(
            id="xyz",
            lift_type="Squat",
            title="Test",
            video_url="https://v.redd.it/test/DASH_720.mp4",
            created_utc=datetime.now(),
            author="user",
            post_score=5,
            comments=comments,
        )

        assert post.has_quality_feedback is False

    def test_video_path_optional(self) -> None:
        """Test that video_path is optional."""
        post = LiftPost(
            id="xyz",
            lift_type="Squat",
            title="Test",
            video_url="https://v.redd.it/test/DASH_720.mp4",
            created_utc=datetime.now(),
            author="user",
            post_score=5,
        )

        assert post.video_path is None

    def test_invalid_url_raises_error(self) -> None:
        """Test that invalid URL raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            LiftPost(
                id="xyz",
                lift_type="Squat",
                title="Test",
                video_url="not-a-valid-url",
                created_utc=datetime.now(),
                author="user",
                post_score=5,
            )

        assert "video_url" in str(exc_info.value)
