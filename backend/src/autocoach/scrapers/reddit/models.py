"""Data models for scraped Reddit content."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Comment(BaseModel):
    """A Reddit comment on a form check post."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Reddit comment ID")
    body: str = Field(..., description="Comment text")
    score: int = Field(..., description="Upvotes minus downvotes")
    author: str = Field(..., description="Reddit username")
    created_utc: datetime = Field(..., description="When comment was posted")
    is_top_level: bool = Field(default=True, description="Is this a direct reply to the post?")

    @classmethod
    def from_praw(cls, comment: Any) -> "Comment":
        """Create Comment from PRAW comment object.

        Args:
            comment: PRAW comment object

        Returns:
            Comment instance
        """
        return cls(
            id=comment.id,
            body=comment.body,
            score=comment.score,
            author=comment.author.name if comment.author else "[deleted]",
            created_utc=datetime.fromtimestamp(comment.created_utc),
            is_top_level=True,
        )


class LiftPost(BaseModel):
    """A Reddit post containing a workout form check video."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Reddit post ID")
    lift_type: str = Field(..., description="Type of lift (Squat, Bench Press, Deadlift)")
    title: str = Field(..., description="Post title")
    video_url: HttpUrl = Field(..., description="URL to video")
    video_path: str | None = Field(default=None, description="Local path after download")
    created_utc: datetime = Field(..., description="When post was created")
    author: str = Field(..., description="Reddit username")
    post_score: int = Field(..., description="Post upvotes minus downvotes")
    comments: list[Comment] = Field(default_factory=list, description="Comments on the post")

    @classmethod
    def from_praw(cls, post: Any, lift_type: str, comments: list[Comment]) -> "LiftPost":
        """Create LiftPost from PRAW submission object.

        Args:
            post: PRAW submission object
            lift_type: Type of lift
            comments: List of comments

        Returns:
            LiftPost instance
        """
        # Extract video URL from reddit_video or other sources
        video_url_str = cls._extract_video_url(post)

        return cls(
            id=str(post.id),
            lift_type=lift_type,
            title=str(post.title),
            video_url=HttpUrl(video_url_str),
            created_utc=datetime.fromtimestamp(float(post.created_utc)),
            author=str(post.author.name) if post.author else "[deleted]",
            post_score=int(post.score),
            comments=comments,
        )

    @staticmethod
    def _extract_video_url(post: Any) -> str:
        """Extract video URL from PRAW post.

        Args:
            post: PRAW submission object

        Returns:
            Video URL as string

        Raises:
            ValueError: If no video URL found
        """
        # Try reddit_video first
        if hasattr(post, "media") and post.media and "reddit_video" in post.media:
            url: str = str(post.media["reddit_video"]["fallback_url"]).split("?")[0]
            return url

        # Try direct URL
        if hasattr(post, "is_video") and post.is_video:
            return str(post.url)

        raise ValueError(f"No video URL found in post {getattr(post, 'id', 'unknown')}")

    def top_comments(self, min_score: int = 5) -> list[Comment]:
        """Get highly-rated comments.

        Args:
            min_score: Minimum comment score to include

        Returns:
            List of comments with score >= min_score
        """
        return [c for c in self.comments if c.score >= min_score]

    @property
    def has_quality_feedback(self) -> bool:
        """Check if post has quality community feedback.

        Returns:
            True if post has at least 3 comments with score >= 5
        """
        return len(self.top_comments(min_score=5)) >= 3
