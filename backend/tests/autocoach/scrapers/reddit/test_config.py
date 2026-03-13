"""Unit tests for Reddit scraper configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from autocoach.scrapers.reddit.config import RedditConfig, ScrapeConfig

pytestmark = pytest.mark.unit


class TestRedditConfig:
    """Tests for Reddit API credentials config."""

    def test_loads_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDDIT_CLIENT_ID", "test_id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "test_secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "test_agent/1.0")

        config = RedditConfig()

        assert config.client_id == "test_id"
        assert config.client_secret == "test_secret"
        assert config.user_agent == "test_agent/1.0"

    def test_raises_if_client_id_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
        monkeypatch.setenv("REDDIT_USER_AGENT", "agent/1.0")

        with pytest.raises(ValidationError):
            RedditConfig()

    def test_raises_if_client_secret_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
        monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("REDDIT_USER_AGENT", "agent/1.0")

        with pytest.raises(ValidationError):
            RedditConfig()

    def test_raises_if_user_agent_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
        monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
        monkeypatch.delenv("REDDIT_USER_AGENT", raising=False)

        with pytest.raises(ValidationError):
            RedditConfig()

    def test_accepts_explicit_values(self) -> None:
        config = RedditConfig(
            client_id="explicit_id",
            client_secret="explicit_secret",
            user_agent="explicit_agent/1.0",
        )

        assert config.client_id == "explicit_id"


class TestScrapeConfig:
    """Tests for scrape run parameters."""

    def test_default_subreddit(self) -> None:
        config = ScrapeConfig()
        assert config.subreddit == "formcheck"

    def test_default_lift_types_covers_big_three(self) -> None:
        config = ScrapeConfig()
        assert "Squat" in config.lift_types
        assert "Deadlift" in config.lift_types
        assert "Bench Press" in config.lift_types

    def test_default_post_limit_is_reasonable(self) -> None:
        config = ScrapeConfig()
        assert 10 <= config.post_limit_per_type <= 500

    def test_default_min_post_score_is_non_negative(self) -> None:
        config = ScrapeConfig()
        assert config.min_post_score >= 0

    def test_default_request_delay_is_non_negative(self) -> None:
        config = ScrapeConfig()
        assert config.request_delay_seconds >= 0.0

    def test_output_dir_is_path(self) -> None:
        config = ScrapeConfig()
        assert isinstance(config.output_dir, Path)

    def test_custom_lift_types(self) -> None:
        config = ScrapeConfig(lift_types=["Squat"])
        assert config.lift_types == ["Squat"]
        assert "Deadlift" not in config.lift_types

    def test_custom_post_limit(self) -> None:
        config = ScrapeConfig(post_limit_per_type=10)
        assert config.post_limit_per_type == 10

    def test_custom_output_dir(self, tmp_path: Path) -> None:
        config = ScrapeConfig(output_dir=tmp_path)
        assert config.output_dir == tmp_path

    def test_empty_lift_types_raises(self) -> None:
        with pytest.raises(ValidationError):
            ScrapeConfig(lift_types=[])
