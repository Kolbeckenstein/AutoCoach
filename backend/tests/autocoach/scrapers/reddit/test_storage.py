"""Unit tests for scraper JSON storage."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from autocoach.scrapers.reddit.models import Comment, LiftPost
from autocoach.scrapers.reddit.storage import ScraperStorage

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_post() -> LiftPost:
    comments = [
        Comment(
            id="c1",
            body="Drive your knees out at the bottom.",
            score=22,
            author="coach_pete",
            created_utc=datetime(2024, 3, 1, 10, 0, 0),
        ),
        Comment(
            id="c2",
            body="Good depth, work on bar position.",
            score=8,
            author="powerlifter99",
            created_utc=datetime(2024, 3, 1, 10, 5, 0),
        ),
    ]
    return LiftPost(
        id="post_abc",
        lift_type="Squat",
        title="225lbs squat form check",
        video_url="https://v.redd.it/abc/DASH_720.mp4",
        created_utc=datetime(2024, 3, 1, 9, 0, 0),
        author="new_lifter",
        post_score=18,
        comments=comments,
    )


@pytest.fixture
def storage(tmp_path: Path) -> ScraperStorage:
    return ScraperStorage(output_dir=tmp_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSavePost:
    def test_saves_json_file(self, storage: ScraperStorage, sample_post: LiftPost) -> None:
        storage.save_post(sample_post)

        expected = storage.output_dir / "Squat" / "post_abc.json"
        assert expected.exists()

    def test_saved_json_is_valid(self, storage: ScraperStorage, sample_post: LiftPost) -> None:
        storage.save_post(sample_post)

        path = storage.output_dir / "Squat" / "post_abc.json"
        data = json.loads(path.read_text())

        assert data["id"] == "post_abc"
        assert data["lift_type"] == "Squat"
        assert data["author"] == "new_lifter"

    def test_saved_json_includes_comments(
        self, storage: ScraperStorage, sample_post: LiftPost
    ) -> None:
        storage.save_post(sample_post)

        path = storage.output_dir / "Squat" / "post_abc.json"
        data = json.loads(path.read_text())

        assert len(data["comments"]) == 2
        assert data["comments"][0]["id"] == "c1"

    def test_creates_lift_type_subdirectory(
        self, storage: ScraperStorage, sample_post: LiftPost
    ) -> None:
        storage.save_post(sample_post)

        assert (storage.output_dir / "Squat").is_dir()

    def test_organises_by_lift_type(self, tmp_path: Path) -> None:
        storage = ScraperStorage(output_dir=tmp_path)

        squat_post = LiftPost(
            id="s1",
            lift_type="Squat",
            title="Squat",
            video_url="https://v.redd.it/s1/DASH_720.mp4",
            created_utc=datetime.now(),
            author="u1",
            post_score=5,
        )
        deadlift_post = LiftPost(
            id="d1",
            lift_type="Deadlift",
            title="Deadlift",
            video_url="https://v.redd.it/d1/DASH_720.mp4",
            created_utc=datetime.now(),
            author="u2",
            post_score=5,
        )

        storage.save_post(squat_post)
        storage.save_post(deadlift_post)

        assert (tmp_path / "Squat" / "s1.json").exists()
        assert (tmp_path / "Deadlift" / "d1.json").exists()
        assert not (tmp_path / "Squat" / "d1.json").exists()

    def test_overwrite_existing_post(self, storage: ScraperStorage, sample_post: LiftPost) -> None:
        storage.save_post(sample_post)
        # Save again — should not raise
        storage.save_post(sample_post)

        path = storage.output_dir / "Squat" / "post_abc.json"
        assert path.exists()


class TestSeenIds:
    def test_load_seen_ids_returns_empty_set_when_no_manifest(
        self, storage: ScraperStorage
    ) -> None:
        seen = storage.load_seen_ids()
        assert seen == set()

    def test_save_and_load_seen_ids_roundtrip(self, storage: ScraperStorage) -> None:
        ids = {"abc", "def", "xyz"}
        storage.save_seen_ids(ids)
        loaded = storage.load_seen_ids()
        assert loaded == ids

    def test_save_seen_ids_creates_manifest_file(self, storage: ScraperStorage) -> None:
        storage.save_seen_ids({"id1", "id2"})
        assert (storage.output_dir / "seen_ids.json").exists()

    def test_load_seen_ids_after_multiple_saves(self, storage: ScraperStorage) -> None:
        storage.save_seen_ids({"a", "b"})
        storage.save_seen_ids({"a", "b", "c"})
        loaded = storage.load_seen_ids()
        assert loaded == {"a", "b", "c"}

    def test_seen_ids_from_saved_posts_are_discoverable(
        self, storage: ScraperStorage, sample_post: LiftPost
    ) -> None:
        """load_seen_ids should reflect posts already on disk even without explicit save."""
        storage.save_post(sample_post)
        seen = storage.load_seen_ids()
        assert "post_abc" in seen
