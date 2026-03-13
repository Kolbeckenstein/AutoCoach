"""Unit tests for the FormcheckScraper orchestrator."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autocoach.scrapers.reddit.models import Comment, LiftPost
from autocoach.scrapers.reddit.scraper import FormcheckScraper, ScrapeResult

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_lift_post(
    id: str = "post1",
    lift_type: str = "Squat",
    post_score: int = 20,
    num_quality_comments: int = 3,
    video_url: str = "https://v.redd.it/abc/DASH_720.mp4",
) -> LiftPost:
    comments = [
        Comment(
            id=f"c{i}",
            body=f"Form feedback {i}",
            score=10,
            author=f"coach{i}",
            created_utc=datetime.now(),
        )
        for i in range(num_quality_comments)
    ]
    return LiftPost(
        id=id,
        lift_type=lift_type,
        title=f"{lift_type} form check",
        video_url=video_url,
        created_utc=datetime.now(),
        author="lifter",
        post_score=post_score,
        comments=comments,
    )


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_downloader() -> MagicMock:
    dl = MagicMock()
    dl.download.return_value = Path("/tmp/fake/video.mp4")
    return dl


@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.load_seen_ids.return_value = set()
    return storage


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScrapeResult:
    def test_scrape_result_tracks_counts(self) -> None:
        result = ScrapeResult(
            posts_found=10,
            posts_saved=7,
            posts_skipped=3,
            errors=[],
        )
        assert result.posts_found == 10
        assert result.posts_saved == 7
        assert result.posts_skipped == 3
        assert result.errors == []

    def test_scrape_result_has_errors_list(self) -> None:
        result = ScrapeResult(
            posts_found=5,
            posts_saved=4,
            posts_skipped=0,
            errors=["post_x: download failed"],
        )
        assert len(result.errors) == 1


class TestFormcheckScraperRun:
    def test_run_fetches_posts_for_each_lift_type(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_client.get_formcheck_posts.return_value = []

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
        )
        scraper.run(lift_types=["Squat", "Deadlift", "Bench Press"], limit_per_type=10)

        assert mock_client.get_formcheck_posts.call_count == 3
        called_lift_types = {
            call.args[0] for call in mock_client.get_formcheck_posts.call_args_list
        }
        assert called_lift_types == {"Squat", "Deadlift", "Bench Press"}

    def test_run_returns_scrape_result(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_client.get_formcheck_posts.return_value = []

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
        )
        result = scraper.run(lift_types=["Squat"], limit_per_type=10)

        assert isinstance(result, ScrapeResult)

    def test_run_saves_qualifying_posts(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        post = make_lift_post(post_score=20, num_quality_comments=3)
        mock_client.get_formcheck_posts.return_value = [post]

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=5,
        )
        scraper.run(lift_types=["Squat"], limit_per_type=10)

        mock_storage.save_post.assert_called_once()

    def test_run_skips_posts_below_min_score(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        post = make_lift_post(post_score=2, num_quality_comments=5)
        mock_client.get_formcheck_posts.return_value = [post]

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=10,
        )
        result = scraper.run(lift_types=["Squat"], limit_per_type=10)

        mock_storage.save_post.assert_not_called()
        assert result.posts_skipped >= 1

    def test_run_skips_posts_without_quality_feedback(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        post = make_lift_post(post_score=50, num_quality_comments=0)
        mock_client.get_formcheck_posts.return_value = [post]

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=1,
        )
        result = scraper.run(lift_types=["Squat"], limit_per_type=10)

        mock_storage.save_post.assert_not_called()
        assert result.posts_skipped >= 1

    def test_run_downloads_video_for_qualifying_post(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        post = make_lift_post(post_score=20, num_quality_comments=3)
        mock_client.get_formcheck_posts.return_value = [post]

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=5,
        )
        scraper.run(lift_types=["Squat"], limit_per_type=10)

        mock_downloader.download.assert_called_once()

    def test_run_continues_on_download_failure(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        posts = [make_lift_post(id=f"p{i}", num_quality_comments=3) for i in range(3)]
        mock_client.get_formcheck_posts.return_value = posts
        mock_downloader.download.return_value = None  # all downloads fail

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=1,
        )
        result = scraper.run(lift_types=["Squat"], limit_per_type=10)

        # Should not raise; errors are recorded
        assert len(result.errors) == 3

    def test_run_passes_seen_ids_to_client(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.load_seen_ids.return_value = {"already_seen_1", "already_seen_2"}
        mock_client.get_formcheck_posts.return_value = []

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
        )
        scraper.run(lift_types=["Squat"], limit_per_type=10)

        call_kwargs = mock_client.get_formcheck_posts.call_args
        seen_ids_passed = call_kwargs.kwargs.get("seen_ids") or call_kwargs.args[2]
        assert "already_seen_1" in seen_ids_passed

    def test_run_updates_seen_ids_after_run(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        post = make_lift_post(id="new_post", num_quality_comments=3)
        mock_client.get_formcheck_posts.return_value = [post]

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=1,
        )
        scraper.run(lift_types=["Squat"], limit_per_type=10)

        mock_storage.save_seen_ids.assert_called_once()
        saved_ids = mock_storage.save_seen_ids.call_args[0][0]
        assert "new_post" in saved_ids

    def test_run_counts_posts_found_and_saved(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        qualifying = make_lift_post(id="p1", post_score=20, num_quality_comments=3)
        low_score = make_lift_post(id="p2", post_score=1, num_quality_comments=3)
        mock_client.get_formcheck_posts.return_value = [qualifying, low_score]

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=10,
        )
        result = scraper.run(lift_types=["Squat"], limit_per_type=10)

        assert result.posts_found == 2
        assert result.posts_saved == 1
        assert result.posts_skipped == 1


# ---------------------------------------------------------------------------
# PostRepository integration
# ---------------------------------------------------------------------------


class TestFormcheckScraperWithRepository:
    def test_repository_save_called_for_qualifying_post(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        post = make_lift_post(post_score=20, num_quality_comments=3)
        mock_client.get_formcheck_posts.return_value = [post]
        mock_repo = MagicMock()

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            post_repository=mock_repo,
        )
        scraper.run(lift_types=["Squat"], limit_per_type=10)

        mock_repo.save.assert_called_once_with(post)

    def test_repository_not_called_for_skipped_post(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        post = make_lift_post(post_score=1, num_quality_comments=3)
        mock_client.get_formcheck_posts.return_value = [post]
        mock_repo = MagicMock()

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            min_post_score=10,
            post_repository=mock_repo,
        )
        scraper.run(lift_types=["Squat"], limit_per_type=10)

        mock_repo.save.assert_not_called()

    def test_seen_ids_merged_from_repository(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        mock_storage.load_seen_ids.return_value = {"from_storage"}
        mock_repo = MagicMock()
        mock_repo.get_seen_ids.return_value = {"from_db_1", "from_db_2"}
        mock_client.get_formcheck_posts.return_value = []

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
            post_repository=mock_repo,
        )
        scraper.run(lift_types=["Squat"], limit_per_type=10)

        call_kwargs = mock_client.get_formcheck_posts.call_args
        seen_ids_passed = call_kwargs.kwargs.get("seen_ids") or call_kwargs.args[2]
        assert {"from_storage", "from_db_1", "from_db_2"}.issubset(seen_ids_passed)

    def test_no_repository_runs_without_error(
        self,
        mock_client: MagicMock,
        mock_downloader: MagicMock,
        mock_storage: MagicMock,
    ) -> None:
        """Passing no repository keeps existing behaviour intact."""
        mock_client.get_formcheck_posts.return_value = []

        scraper = FormcheckScraper(
            client=mock_client,
            downloader=mock_downloader,
            storage=mock_storage,
        )
        result = scraper.run(lift_types=["Squat"], limit_per_type=10)

        assert isinstance(result, ScrapeResult)
