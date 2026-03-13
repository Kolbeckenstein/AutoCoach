"""Unit tests for the central AutoCoach CLI."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner, Result

from autocoach.cli import main
from autocoach.scrapers.reddit.client import AuthError
from autocoach.scrapers.reddit.scraper import ScrapeResult

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ENV = {
    "REDDIT_CLIENT_ID": "fake_id",
    "REDDIT_CLIENT_SECRET": "fake_secret",
    "REDDIT_USER_AGENT": "TestAgent/1.0",
}


def _make_result(
    posts_found: int = 10,
    posts_saved: int = 7,
    posts_skipped: int = 3,
    errors: list[str] | None = None,
) -> ScrapeResult:
    return ScrapeResult(
        posts_found=posts_found,
        posts_saved=posts_saved,
        posts_skipped=posts_skipped,
        errors=errors or [],
    )


def _run(args: list[str], env: dict | None = None) -> tuple[CliRunner, Result]:
    """Invoke the CLI and return (runner, result)."""
    runner = CliRunner()
    result = runner.invoke(main, args, env=env if env is not None else _VALID_ENV)
    return runner, result


# ---------------------------------------------------------------------------
# CLI structure
# ---------------------------------------------------------------------------


class TestCLIStructure:
    def test_main_help_exits_cleanly(self) -> None:
        _, result = _run(["--help"])
        assert result.exit_code == 0

    def test_main_help_mentions_pipeline(self) -> None:
        _, result = _run(["--help"])
        assert "pipeline" in result.output

    def test_pipeline_group_help_exits_cleanly(self) -> None:
        _, result = _run(["pipeline", "--help"])
        assert result.exit_code == 0

    def test_pipeline_help_mentions_scrape(self) -> None:
        _, result = _run(["pipeline", "--help"])
        assert "scrape" in result.output

    def test_scrape_help_exits_cleanly(self) -> None:
        _, result = _run(["pipeline", "scrape", "--help"])
        assert result.exit_code == 0

    def test_scrape_help_shows_lift_types_option(self) -> None:
        _, result = _run(["pipeline", "scrape", "--help"])
        assert "--lift-types" in result.output

    def test_scrape_help_shows_limit_option(self) -> None:
        _, result = _run(["pipeline", "scrape", "--help"])
        assert "--limit" in result.output

    def test_scrape_help_shows_output_dir_option(self) -> None:
        _, result = _run(["pipeline", "scrape", "--help"])
        assert "--output-dir" in result.output

    def test_scrape_help_shows_min_score_option(self) -> None:
        _, result = _run(["pipeline", "scrape", "--help"])
        assert "--min-score" in result.output


# ---------------------------------------------------------------------------
# Scrape command — happy path
# ---------------------------------------------------------------------------


class TestScrapeHappyPath:
    def _scrape(
        self,
        extra_args: list[str] | None = None,
        mock_result: ScrapeResult | None = None,
        env: dict | None = None,
    ) -> tuple[Result, MagicMock]:
        """Run `pipeline scrape` with _build_scraper mocked out."""
        result_to_return = mock_result or _make_result()
        mock_scraper = MagicMock()
        mock_scraper.run.return_value = result_to_return

        with patch("autocoach.cli._build_scraper", return_value=mock_scraper):
            _, result = _run(
                ["pipeline", "scrape"] + (extra_args or []),
                env=env if env is not None else _VALID_ENV,
            )

        return result, mock_scraper

    def test_exits_zero_on_success(self) -> None:
        result, _ = self._scrape()
        assert result.exit_code == 0

    def test_output_contains_posts_found_count(self) -> None:
        result, _ = self._scrape(mock_result=_make_result(posts_found=42))
        assert "42" in result.output

    def test_output_contains_posts_saved_count(self) -> None:
        result, _ = self._scrape(mock_result=_make_result(posts_saved=17))
        assert "17" in result.output

    def test_output_contains_posts_skipped_count(self) -> None:
        result, _ = self._scrape(mock_result=_make_result(posts_skipped=5))
        assert "5" in result.output

    def test_runs_scraper_once(self) -> None:
        _, mock_scraper = self._scrape()
        mock_scraper.run.assert_called_once()

    def test_lift_types_option_forwarded_to_scraper(self) -> None:
        _, mock_scraper = self._scrape(
            extra_args=["--lift-types", "Squat", "--lift-types", "Deadlift"]
        )
        call_args = mock_scraper.run.call_args
        lift_types = call_args.kwargs.get("lift_types") or call_args.args[0]
        assert set(lift_types) == {"Squat", "Deadlift"}

    def test_limit_option_forwarded_to_scraper(self) -> None:
        _, mock_scraper = self._scrape(extra_args=["--limit", "25"])
        call_args = mock_scraper.run.call_args
        limit = call_args.kwargs.get("limit_per_type") or call_args.args[1]
        assert limit == 25

    def test_output_dir_option_passed_to_build_scraper(self) -> None:
        with patch("autocoach.cli._build_scraper") as mock_build:
            mock_build.return_value = MagicMock()
            mock_build.return_value.run.return_value = _make_result()
            runner = CliRunner()
            runner.invoke(
                main,
                ["pipeline", "scrape", "--output-dir", "/tmp/test_data"],
                env=_VALID_ENV,
            )
        # _build_scraper(reddit_cfg, scrape_cfg, post_repository)
        _reddit_cfg, scrape_cfg, _repo = mock_build.call_args.args
        assert scrape_cfg.output_dir == Path("/tmp/test_data")

    def test_min_score_option_passed_to_build_scraper(self) -> None:
        with patch("autocoach.cli._build_scraper") as mock_build:
            mock_build.return_value = MagicMock()
            mock_build.return_value.run.return_value = _make_result()
            runner = CliRunner()
            runner.invoke(
                main,
                ["pipeline", "scrape", "--min-score", "10"],
                env=_VALID_ENV,
            )
        _reddit_cfg, scrape_cfg, _repo = mock_build.call_args.args
        assert scrape_cfg.min_post_score == 10

    def test_errors_are_shown_when_present(self) -> None:
        result, _ = self._scrape(mock_result=_make_result(errors=["post_xyz: download failed"]))
        assert "post_xyz" in result.output


# ---------------------------------------------------------------------------
# Scrape command — error handling
# ---------------------------------------------------------------------------


class TestScrapeErrorHandling:
    def test_missing_credentials_exits_nonzero(self) -> None:
        with patch("autocoach.cli.RedditConfig") as mock_cfg_cls:
            mock_cfg_cls.side_effect = Exception("validation error: missing fields")
            runner = CliRunner()
            result = runner.invoke(main, ["pipeline", "scrape"], env={})
        assert result.exit_code != 0

    def test_missing_credentials_shows_helpful_message(self) -> None:
        with patch("autocoach.cli.RedditConfig") as mock_cfg_cls:
            mock_cfg_cls.side_effect = Exception("validation error: missing fields")
            runner = CliRunner()
            result = runner.invoke(main, ["pipeline", "scrape"], env={})
        # CliRunner mixes stderr into output by default
        assert any(kw in result.output.lower() for kw in ("credential", "reddit_client", "missing"))

    def test_auth_error_exits_nonzero(self) -> None:
        mock_scraper = MagicMock()
        mock_scraper.run.side_effect = AuthError("Invalid credentials")
        with patch("autocoach.cli._build_scraper", return_value=mock_scraper):
            _, result = _run(["pipeline", "scrape"])
        assert result.exit_code != 0

    def test_auth_error_shows_helpful_message(self) -> None:
        mock_scraper = MagicMock()
        mock_scraper.run.side_effect = AuthError("Invalid credentials")
        with patch("autocoach.cli._build_scraper", return_value=mock_scraper):
            _, result = _run(["pipeline", "scrape"])
        assert any(kw in result.output.lower() for kw in ("auth", "credential", "invalid"))
