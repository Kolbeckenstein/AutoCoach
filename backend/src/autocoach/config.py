"""Application-wide configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Top-level settings shared across all autocoach modules.

    Values are read from the environment (and .env files loaded by the CLI).
    All fields have sensible defaults matching the devcontainer docker-compose.
    """

    model_config = SettingsConfigDict(extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "autocoach_dev"
    postgres_user: str = "autocoach"
    postgres_password: str = "autocoach_dev_password"

    redis_host: str = "localhost"
    redis_port: int = 6379

    blob_storage_root: str = "/tmp/autocoach-blobs"

    log_level: str = "INFO"

    @property
    def redis_url(self) -> str:
        """Redis URL for Celery broker and result backend."""
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def db_url(self) -> str:
        """Sync PostgreSQL URL for SQLAlchemy (psycopg2 driver)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def db_url_async(self) -> str:
        """Async PostgreSQL URL for SQLAlchemy (asyncpg driver, Phase 5+)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
