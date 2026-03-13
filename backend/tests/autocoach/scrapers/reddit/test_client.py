"""Unit tests for the Reddit API client."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import prawcore
import pytest

from autocoach.scrapers.reddit.client import AuthError, RateLimitError, RedditClient
from autocoach.scrapers.reddit.models import LiftPost

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------


def make_praw_comment(
    id: str = "c1",
    body: str = "Good depth, watch your knees.",
    score: int = 10,
    author_name: str | None = "coach_user",
    created_utc: float | None = None,
    is_top_level: bool = True,
) -> MagicMock:
    comment = MagicMock()
    comment.id = id
    comment.body = body
    comment.score = score
    if author_name:
        comment.author = MagicMock()
        comment.author.name = author_name
    else:
        comment.author = None
    comment.created_utc = created_utc or datetime.now().timestamp()
    comment.parent_id = "t3_post1" if is_top_level else "t1_other_comment"
    return comment


def make_praw_submission(
    id: str = "post1",
    title: str = "Form check squat 225lbs",
    score: int = 20,
    author_name: str | None = "lifter42",
    flair: str = "Squat",
    has_reddit_video: bool = True,
    video_url: str = "https://v.redd.it/abc123/DASH_720.mp4?source=fallback",
    comments: list | None = None,
) -> MagicMock:
    sub = MagicMock()
    sub.id = id
    sub.title = title
    sub.score = score
    sub.author = MagicMock()
    sub.author.name = author_name
    sub.link_flair_text = flair
    sub.created_utc = datetime.now().timestamp()
    sub.is_video = has_reddit_video

    if has_reddit_video:
        sub.media = {"reddit_video": {"fallback_url": video_url}}
    else:
        sub.media = None

    # comments.list() returns flat list of top-level comments
    sub.comments = MagicMock()
    sub.comments.list.return_value = comments or []

    return sub


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRedditClientInit:
    """Tests for client construction and PRAW connection."""

    def test_raises_auth_error_on_bad_credentials(self) -> None:
        with patch("praw.Reddit") as mock_reddit_cls:
            mock_reddit_cls.return_value.subreddit.side_effect = prawcore.exceptions.OAuthException(
                MagicMock(), "invalid_grant", "Invalid credentials"
            )
            client = RedditClient(client_id="bad", client_secret="bad", user_agent="agent/1.0")

            with pytest.raises(AuthError):
                list(client.get_formcheck_posts("Squat", limit=1))


class TestGetFormcheckPosts:
    """Tests for get_formcheck_posts()."""

    def test_returns_lift_posts(self) -> None:
        submission = make_praw_submission()

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=10))

        assert len(posts) == 1
        assert isinstance(posts[0], LiftPost)
        assert posts[0].lift_type == "Squat"

    def test_sets_lift_type_from_argument(self) -> None:
        submission = make_praw_submission(flair="Deadlift")

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Deadlift", limit=10))

        assert posts[0].lift_type == "Deadlift"

    def test_skips_posts_without_video(self) -> None:
        submission = make_praw_submission(has_reddit_video=False)

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=10))

        assert len(posts) == 0

    def test_deduplicates_seen_ids(self) -> None:
        submission = make_praw_submission(id="already_seen")

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=10, seen_ids={"already_seen"}))

        assert len(posts) == 0

    def test_collects_top_level_comments(self) -> None:
        comments = [
            make_praw_comment(id="c1", is_top_level=True),
            make_praw_comment(id="c2", is_top_level=True),
        ]
        submission = make_praw_submission(comments=comments)

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=10))

        assert len(posts[0].comments) == 2
        assert all(c.is_top_level for c in posts[0].comments)

    def test_marks_nested_comments_not_top_level(self) -> None:
        comments = [
            make_praw_comment(id="c1", is_top_level=True),
            make_praw_comment(id="c2", is_top_level=False),
        ]
        submission = make_praw_submission(comments=comments)

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=10))

        top_level = [c for c in posts[0].comments if c.is_top_level]
        nested = [c for c in posts[0].comments if not c.is_top_level]
        assert len(top_level) == 1
        assert len(nested) == 1

    def test_handles_deleted_comment_author(self) -> None:
        comments = [make_praw_comment(id="c1", author_name=None)]
        submission = make_praw_submission(comments=comments)

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=10))

        assert posts[0].comments[0].author == "[deleted]"

    def test_strips_query_params_from_reddit_video_url(self) -> None:
        submission = make_praw_submission(
            video_url="https://v.redd.it/abc123/DASH_720.mp4?source=fallback"
        )

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = [submission]
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=10))

        assert "?" not in str(posts[0].video_url)

    def test_raises_rate_limit_error_on_429(self) -> None:
        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.side_effect = prawcore.exceptions.TooManyRequests(MagicMock())
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")

            with pytest.raises(RateLimitError):
                list(client.get_formcheck_posts("Squat", limit=10))

    def test_respects_limit(self) -> None:
        submissions = [make_praw_submission(id=f"post{i}") for i in range(10)]

        with patch("praw.Reddit") as mock_reddit_cls:
            mock_subreddit = MagicMock()
            mock_subreddit.search.return_value = submissions
            mock_reddit_cls.return_value.subreddit.return_value = mock_subreddit

            client = RedditClient(client_id="id", client_secret="secret", user_agent="agent/1.0")
            posts = list(client.get_formcheck_posts("Squat", limit=3))

        assert len(posts) <= 3
