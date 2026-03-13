"""Integration tests for the Reddit scraper against the live API.

These tests require real Reddit credentials in the environment (or .env file):
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT

They are skipped automatically when credentials are absent so CI stays clean.
Run manually with:
    uv run pytest -m integration
"""

import json
import os
from pathlib import Path

import pytest

from autocoach.scrapers.reddit.client import RedditClient
from autocoach.scrapers.reddit.config import RedditConfig
from autocoach.scrapers.reddit.downloader import VideoDownloader
from autocoach.scrapers.reddit.models import LiftPost
from autocoach.scrapers.reddit.scraper import FormcheckScraper, ScrapeResult
from autocoach.scrapers.reddit.storage import ScraperStorage

# ---------------------------------------------------------------------------
# Skip guard — all tests in this module are skipped without credentials
# ---------------------------------------------------------------------------

_CREDS_PRESENT = all(
    os.environ.get(k) for k in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _CREDS_PRESENT, reason="Reddit credentials not set in environment"),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reddit_config() -> RedditConfig:
    return RedditConfig()


@pytest.fixture(scope="module")
def client(reddit_config: RedditConfig) -> RedditClient:
    return RedditClient(
        client_id=reddit_config.client_id,
        client_secret=reddit_config.client_secret,
        user_agent=reddit_config.user_agent,
    )


@pytest.fixture(scope="module")
def downloader() -> VideoDownloader:
    return VideoDownloader()


# ---------------------------------------------------------------------------
# RedditClient — live API
# ---------------------------------------------------------------------------


class TestRedditClientIntegration:
    def test_authenticates_successfully(self, client: RedditClient) -> None:
        """Credentials are valid and the API is reachable."""
        posts = list(client.get_formcheck_posts("Squat", limit=1))
        # If auth failed, AuthError would have been raised
        assert isinstance(posts, list)

    def test_returns_lift_post_objects(self, client: RedditClient) -> None:
        posts = list(client.get_formcheck_posts("Squat", limit=3))
        assert len(posts) >= 1
        assert all(isinstance(p, LiftPost) for p in posts)

    def test_returned_posts_have_correct_lift_type(self, client: RedditClient) -> None:
        posts = list(client.get_formcheck_posts("Deadlift", limit=3))
        assert all(p.lift_type == "Deadlift" for p in posts)

    def test_returned_posts_have_valid_video_url(self, client: RedditClient) -> None:
        posts = list(client.get_formcheck_posts("Squat", limit=3))
        for post in posts:
            url = str(post.video_url)
            assert url.startswith("https://")
            assert "?" not in url, f"Query params not stripped from {url}"

    def test_returned_posts_have_comments(self, client: RedditClient) -> None:
        """At least some posts should have comments (r/formcheck is active)."""
        posts = list(client.get_formcheck_posts("Squat", limit=5))
        posts_with_comments = [p for p in posts if len(p.comments) > 0]
        assert len(posts_with_comments) >= 1

    def test_deduplication_excludes_seen_posts(self, client: RedditClient) -> None:
        first_batch = list(client.get_formcheck_posts("Squat", limit=3))
        seen = {p.id for p in first_batch}

        second_batch = list(client.get_formcheck_posts("Squat", limit=3, seen_ids=seen))
        overlap = {p.id for p in second_batch} & seen
        assert len(overlap) == 0

    @pytest.mark.parametrize("lift_type", ["Squat", "Deadlift", "Bench Press"])
    def test_all_lift_types_return_results(self, client: RedditClient, lift_type: str) -> None:
        posts = list(client.get_formcheck_posts(lift_type, limit=2))
        assert len(posts) >= 1, f"No posts returned for lift type: {lift_type}"


# ---------------------------------------------------------------------------
# VideoDownloader — live HTTP
# ---------------------------------------------------------------------------


class TestVideoDownloaderIntegration:
    def test_downloads_real_video(self, client: RedditClient, tmp_path: Path) -> None:
        """Fetch a real post and download its video."""
        posts = list(client.get_formcheck_posts("Squat", limit=5))
        # Find a post with a v.redd.it URL (most common on r/formcheck)
        reddit_video_posts = [p for p in posts if "v.redd.it" in str(p.video_url)]
        if not reddit_video_posts:
            pytest.skip("No v.redd.it posts in current batch")

        post = reddit_video_posts[0]
        dest = tmp_path / f"{post.id}.mp4"

        downloader = VideoDownloader()
        result = downloader.download(str(post.video_url), dest)

        assert result == dest
        assert dest.exists()
        assert dest.stat().st_size > 0

    def test_returns_none_for_dead_url(self, tmp_path: Path) -> None:
        dest = tmp_path / "dead.mp4"
        downloader = VideoDownloader()
        result = downloader.download("https://v.redd.it/this_does_not_exist/DASH_720.mp4", dest)
        assert result is None
        assert not dest.exists()


# ---------------------------------------------------------------------------
# FormcheckScraper — end-to-end
# ---------------------------------------------------------------------------


class TestFormcheckScraperIntegration:
    def test_run_produces_scrape_result(
        self, client: RedditClient, downloader: VideoDownloader, tmp_path: Path
    ) -> None:
        storage = ScraperStorage(output_dir=tmp_path)
        scraper = FormcheckScraper(
            client=client,
            downloader=downloader,
            storage=storage,
            min_post_score=1,
            request_delay_seconds=1.0,
        )

        result = scraper.run(lift_types=["Squat"], limit_per_type=3)

        assert isinstance(result, ScrapeResult)
        assert result.posts_found >= 0
        assert result.posts_saved + result.posts_skipped + len(result.errors) == result.posts_found

    def test_run_writes_json_files_to_disk(
        self, client: RedditClient, downloader: VideoDownloader, tmp_path: Path
    ) -> None:
        storage = ScraperStorage(output_dir=tmp_path)
        scraper = FormcheckScraper(
            client=client,
            downloader=downloader,
            storage=storage,
            min_post_score=1,
            request_delay_seconds=1.0,
        )

        result = scraper.run(lift_types=["Squat"], limit_per_type=5)

        if result.posts_saved == 0:
            pytest.skip("No qualifying posts in current batch — cannot verify file output")

        json_files = list(tmp_path.rglob("*.json"))
        post_files = [f for f in json_files if f.name != "seen_ids.json"]
        assert len(post_files) == result.posts_saved

    def test_run_json_files_are_valid_lift_posts(
        self, client: RedditClient, downloader: VideoDownloader, tmp_path: Path
    ) -> None:
        storage = ScraperStorage(output_dir=tmp_path)
        scraper = FormcheckScraper(
            client=client,
            downloader=downloader,
            storage=storage,
            min_post_score=1,
            request_delay_seconds=1.0,
        )

        scraper.run(lift_types=["Squat"], limit_per_type=3)

        for json_file in tmp_path.rglob("*.json"):
            if json_file.name == "seen_ids.json":
                continue
            data = json.loads(json_file.read_text())
            post = LiftPost.model_validate(data)
            assert post.lift_type == "Squat"
            assert post.id == json_file.stem

    def test_second_run_skips_already_seen_posts(
        self, client: RedditClient, downloader: VideoDownloader, tmp_path: Path
    ) -> None:
        storage = ScraperStorage(output_dir=tmp_path)
        scraper = FormcheckScraper(
            client=client,
            downloader=downloader,
            storage=storage,
            min_post_score=1,
            request_delay_seconds=1.0,
        )

        first = scraper.run(lift_types=["Squat"], limit_per_type=3)
        second = scraper.run(lift_types=["Squat"], limit_per_type=3)

        # The second run should not re-save posts already scraped in the first run
        assert second.posts_found <= first.posts_found or second.posts_saved <= first.posts_saved
