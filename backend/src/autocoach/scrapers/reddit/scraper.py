"""Orchestrates the Reddit form-check scrape pipeline."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from autocoach.scrapers.reddit.client import RedditClient
from autocoach.scrapers.reddit.downloader import VideoDownloader
from autocoach.scrapers.reddit.models import LiftPost
from autocoach.scrapers.reddit.storage import ScraperStorage

if TYPE_CHECKING:
    from autocoach.db.repository import PostRepository

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    """Summary of a completed scrape run."""

    posts_found: int
    posts_saved: int
    posts_skipped: int
    errors: list[str] = field(default_factory=list)


class FormcheckScraper:
    """Coordinates client, downloader, storage, and optional DB repository."""

    def __init__(
        self,
        client: RedditClient,
        downloader: VideoDownloader,
        storage: ScraperStorage,
        min_post_score: int = 5,
        request_delay_seconds: float = 2.0,
        post_repository: PostRepository | None = None,
    ) -> None:
        self._client = client
        self._downloader = downloader
        self._storage = storage
        self._min_post_score = min_post_score
        self._request_delay = request_delay_seconds
        self._post_repository = post_repository

    def run(self, lift_types: list[str], limit_per_type: int) -> ScrapeResult:
        """Scrape r/formcheck for each lift type and persist qualifying posts.

        A post qualifies if:
        - post_score >= min_post_score
        - has_quality_feedback is True (≥3 comments with score ≥5)

        Seen IDs are merged from both the file-system manifest and the DB
        repository (when provided) to avoid re-scraping posts regardless of
        which storage backend has seen them.

        Args:
            lift_types: Lift flairs to scrape (e.g. ["Squat", "Deadlift"]).
            limit_per_type: Max posts to fetch per lift type before filtering.

        Returns:
            ScrapeResult with counts and any per-post error messages.
        """
        seen_ids = self._storage.load_seen_ids()
        if self._post_repository is not None:
            seen_ids |= self._post_repository.get_seen_ids()

        posts_found = 0
        posts_saved = 0
        posts_skipped = 0
        errors: list[str] = []

        for lift_type in lift_types:
            logger.info("Scraping lift type: %s", lift_type)

            posts = self._client.get_formcheck_posts(
                lift_type, limit=limit_per_type, seen_ids=seen_ids
            )

            for post in posts:
                posts_found += 1

                if not self._qualifies(post):
                    logger.debug(
                        "Skipping post %s (score=%d, quality=%s)",
                        post.id,
                        post.post_score,
                        post.has_quality_feedback,
                    )
                    posts_skipped += 1
                    continue

                dest = self._storage.output_dir / post.lift_type / f"{post.id}.mp4"
                downloaded = self._downloader.download(str(post.video_url), dest)

                if downloaded is None:
                    errors.append(f"{post.id}: video download failed")
                    logger.warning("Download failed for post %s", post.id)
                    continue

                self._storage.save_post(post)
                if self._post_repository is not None:
                    self._post_repository.save(post)

                seen_ids.add(post.id)
                posts_saved += 1

                if self._request_delay > 0:
                    time.sleep(self._request_delay)

        self._storage.save_seen_ids(seen_ids)

        result = ScrapeResult(
            posts_found=posts_found,
            posts_saved=posts_saved,
            posts_skipped=posts_skipped,
            errors=errors,
        )
        logger.info(
            "Scrape complete: found=%d saved=%d skipped=%d errors=%d",
            posts_found,
            posts_saved,
            posts_skipped,
            len(errors),
        )
        return result

    def _qualifies(self, post: LiftPost) -> bool:
        return post.post_score >= self._min_post_score and post.has_quality_feedback
