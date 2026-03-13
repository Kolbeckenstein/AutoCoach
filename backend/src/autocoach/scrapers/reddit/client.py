"""Reddit API client wrapping PRAW."""

import logging
from collections.abc import Iterator

import praw
import prawcore

from autocoach.scrapers.reddit.models import Comment, LiftPost

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Raised when Reddit API credentials are invalid."""


class RateLimitError(Exception):
    """Raised when the Reddit API rate limit is exceeded."""


class RedditClient:
    """Thin wrapper around PRAW for fetching r/formcheck posts."""

    def __init__(self, client_id: str, client_secret: str, user_agent: str) -> None:
        self._reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )

    def get_formcheck_posts(
        self,
        lift_type: str,
        limit: int,
        seen_ids: set[str] | None = None,
    ) -> Iterator[LiftPost]:
        """Yield LiftPost objects for the given lift type from r/formcheck.

        Args:
            lift_type: Flair to search for (e.g. "Squat").
            limit: Maximum number of posts to return.
            seen_ids: Post IDs to skip (already scraped).

        Yields:
            LiftPost instances with comments attached.

        Raises:
            AuthError: On invalid credentials.
            RateLimitError: When the API rate limit is hit.
        """
        if seen_ids is None:
            seen_ids = set()

        try:
            subreddit = self._reddit.subreddit("formcheck")
            results = subreddit.search(
                f'flair:"{lift_type}"',
                sort="new",
                limit=None,  # we enforce the limit ourselves after dedup
            )

            count = 0
            for submission in results:
                if count >= limit:
                    break

                if submission.id in seen_ids:
                    logger.debug("Skipping already-seen post %s", submission.id)
                    continue

                try:
                    post = LiftPost.from_praw(
                        post=submission,
                        lift_type=lift_type,
                        comments=self._collect_comments(submission),
                    )
                except ValueError:
                    logger.debug("Skipping post %s — no video URL", submission.id)
                    continue

                count += 1
                yield post

        except prawcore.exceptions.OAuthException as exc:
            raise AuthError(f"Invalid Reddit credentials: {exc}") from exc
        except prawcore.exceptions.TooManyRequests as exc:
            raise RateLimitError("Reddit API rate limit exceeded") from exc

    def _collect_comments(self, submission: praw.models.Submission) -> list[Comment]:
        """Flatten submission comments into Comment models.

        Top-level comments (direct replies to the post) have parent IDs prefixed
        with "t3_"; nested replies are prefixed with "t1_".
        """
        submission.comments.replace_more(limit=0)  # don't fetch MoreComments
        comments: list[Comment] = []

        for praw_comment in submission.comments.list():
            is_top_level = str(praw_comment.parent_id).startswith("t3_")
            comment = Comment(
                id=praw_comment.id,
                body=praw_comment.body,
                score=praw_comment.score,
                author=praw_comment.author.name if praw_comment.author else "[deleted]",
                created_utc=praw_comment.created_utc,
                is_top_level=is_top_level,
            )
            comments.append(comment)

        return comments
