"""Configuration for the Reddit scraper."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedditConfig(BaseSettings):
    """Reddit API credentials, loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="REDDIT_", extra="ignore")

    client_id: str
    client_secret: str
    user_agent: str


class ScrapeConfig(BaseSettings):
    """Parameters controlling a scrape run."""

    model_config = SettingsConfigDict(extra="ignore")

    subreddit: str = "formcheck"
    lift_types: list[str] = ["Squat", "Deadlift", "Bench Press"]
    post_limit_per_type: int = 100
    min_post_score: int = 5
    request_delay_seconds: float = 2.0
    output_dir: Path = Path("data/scraped")

    @field_validator("lift_types")
    @classmethod
    def lift_types_not_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("lift_types must contain at least one lift type")
        return v
