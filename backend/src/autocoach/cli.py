"""Central CLI for the AutoCoach data pipeline.

Entry point declared in pyproject.toml:
    autocoach = "autocoach.cli:main"

Usage examples:
    autocoach pipeline scrape
    autocoach pipeline scrape --lift-types Squat --lift-types Deadlift --limit 50
    autocoach pipeline scrape --output-dir ./data/raw --min-score 10
"""

import sys
from pathlib import Path

import click
from dotenv import find_dotenv, load_dotenv
from rich.console import Console

# Load .env by searching upward from cwd — works whether invoked from the repo
# root or the backend/ subdirectory.
load_dotenv(find_dotenv(usecwd=True))

from autocoach.config import AppConfig  # noqa: E402
from autocoach.db.models import Base  # noqa: E402
from autocoach.db.repository import PostRepository  # noqa: E402
from autocoach.db.session import make_engine, make_session_factory  # noqa: E402
from autocoach.scrapers.reddit.client import AuthError, RedditClient  # noqa: E402
from autocoach.scrapers.reddit.config import RedditConfig, ScrapeConfig  # noqa: E402
from autocoach.scrapers.reddit.downloader import VideoDownloader  # noqa: E402
from autocoach.scrapers.reddit.scraper import FormcheckScraper  # noqa: E402
from autocoach.scrapers.reddit.storage import ScraperStorage  # noqa: E402

_console = Console()
_err = Console(stderr=True)


# ---------------------------------------------------------------------------
# Factories — isolated here so tests can patch them without touching internals
# ---------------------------------------------------------------------------


def _build_scraper(
    reddit_cfg: RedditConfig,
    scrape_cfg: ScrapeConfig,
    post_repository: PostRepository | None = None,
) -> FormcheckScraper:
    """Construct a ready-to-run FormcheckScraper from config objects."""
    client = RedditClient(
        client_id=reddit_cfg.client_id,
        client_secret=reddit_cfg.client_secret,
        user_agent=reddit_cfg.user_agent,
    )
    downloader = VideoDownloader()
    storage = ScraperStorage(scrape_cfg.output_dir)
    return FormcheckScraper(
        client=client,
        downloader=downloader,
        storage=storage,
        min_post_score=scrape_cfg.min_post_score,
        request_delay_seconds=scrape_cfg.request_delay_seconds,
        post_repository=post_repository,
    )


def _try_connect_db(app_cfg: AppConfig) -> PostRepository | None:
    """Attempt to open a DB session; return None with a warning if unavailable.

    Keeps the scraper working without a running database so that the CLI can
    be used during development before PostgreSQL is set up.
    """
    try:
        engine = make_engine(app_cfg.db_url)
        Base.metadata.create_all(engine)  # no-op if tables already exist
        factory = make_session_factory(engine)
        session = factory()
        return PostRepository(session)
    except Exception as exc:
        _err.print(f"[yellow]DB unavailable — running without persistence:[/yellow] {exc}")
        return None


# ---------------------------------------------------------------------------
# CLI groups and commands
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(package_name="autocoach")
def main() -> None:
    """AutoCoach — AI-powered workout form coaching pipeline."""


@main.group()
def pipeline() -> None:
    """Manual pipeline step execution for development and debugging."""


@pipeline.command()
@click.option(
    "--lift-types",
    multiple=True,
    metavar="LIFT",
    help=(
        "Lift type to scrape (repeatable, e.g. --lift-types Squat --lift-types Deadlift). "
        "Defaults to all types in ScrapeConfig."
    ),
)
@click.option(
    "--limit",
    default=None,
    type=int,
    metavar="N",
    help="Max posts to fetch per lift type before filtering. Overrides ScrapeConfig default.",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(),
    help="Root directory for scraped JSON and video files. Overrides ScrapeConfig default.",
)
@click.option(
    "--min-score",
    default=None,
    type=int,
    help="Minimum Reddit post score for a post to qualify. Overrides ScrapeConfig default.",
)
@click.option(
    "--delay",
    default=None,
    type=float,
    help="Seconds to pause between Reddit API requests. Overrides ScrapeConfig default.",
)
def scrape(
    lift_types: tuple[str, ...],
    limit: int | None,
    output_dir: str | None,
    min_score: int | None,
    delay: float | None,
) -> None:
    """Scrape r/formcheck for form-check videos and save locally.

    Reads Reddit credentials from environment variables:
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT.

    Persists post metadata to PostgreSQL when a database is available.
    Runs in JSON-only mode if the database cannot be reached.
    """
    # ---- Load Reddit credentials from environment -------------------------
    try:
        reddit_cfg = RedditConfig()
    except Exception as exc:
        _err.print(f"[red]Missing or invalid Reddit credentials:[/red] {exc}")
        _err.print(
            "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT "
            "in your environment or .env file."
        )
        sys.exit(1)

    # ---- Build ScrapeConfig, applying any CLI overrides ------------------
    scrape_overrides: dict[str, object] = {}
    if output_dir is not None:
        scrape_overrides["output_dir"] = Path(output_dir)
    if min_score is not None:
        scrape_overrides["min_post_score"] = min_score
    if delay is not None:
        scrape_overrides["request_delay_seconds"] = delay

    scrape_cfg = ScrapeConfig(**scrape_overrides)  # type: ignore[arg-type]

    effective_lift_types = list(lift_types) if lift_types else scrape_cfg.lift_types
    effective_limit = limit if limit is not None else scrape_cfg.post_limit_per_type

    # ---- Connect to database (optional) -----------------------------------
    app_cfg = AppConfig()
    post_repository = _try_connect_db(app_cfg)
    db_status = "[green]connected[/green]" if post_repository else "[yellow]unavailable[/yellow]"

    # ---- Print run summary ------------------------------------------------
    _console.print("[bold]AutoCoach · Reddit Scraper[/bold]")
    _console.print(f"  Lift types : {', '.join(effective_lift_types)}")
    _console.print(f"  Limit/type : {effective_limit}")
    _console.print(f"  Min score  : {scrape_cfg.min_post_score}")
    _console.print(f"  Output dir : {scrape_cfg.output_dir}")
    _console.print(f"  Database   : {db_status}")
    _console.print()

    # ---- Run the scraper --------------------------------------------------
    scraper = _build_scraper(reddit_cfg, scrape_cfg, post_repository)
    try:
        result = scraper.run(
            lift_types=effective_lift_types,
            limit_per_type=effective_limit,
        )
    except AuthError as exc:
        _err.print(f"[red]Authentication error:[/red] {exc}")
        _err.print("Check that your Reddit API credentials are correct.")
        sys.exit(1)

    # ---- Display results --------------------------------------------------
    _console.print("[bold]Results[/bold]")
    _console.print(f"  Posts found   : {result.posts_found}")
    _console.print(f"  Posts saved   : [green]{result.posts_saved}[/green]")
    _console.print(f"  Posts skipped : {result.posts_skipped}")

    if result.errors:
        _console.print(f"  Errors        : [red]{len(result.errors)}[/red]")
        _console.print()
        _console.print("[red]Error details:[/red]")
        for error in result.errors:
            _console.print(f"  • {error}")


@pipeline.command("pose-process")
@click.argument("video", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--lift-type",
    default="Squat",
    show_default=True,
    help="Lift type label stored in the output (e.g. Squat, Deadlift, BenchPress).",
)
@click.option(
    "--video-id",
    default=None,
    help="Override the video ID (defaults to the video filename stem).",
)
@click.option(
    "--model",
    default=None,
    type=click.Path(),
    help="Path to the MediaPipe PoseLandmarker .task file. Defaults to backend/models/pose_landmarker_full.task.",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(),
    help="Write BiomechanicalFeatures JSON to this file.",
)
@click.option(
    "--allow-front-view",
    is_flag=True,
    help="Process front-facing videos instead of rejecting them (features will have low view_confidence).",
)
def pose_process(
    video: Path,
    lift_type: str,
    video_id: str | None,
    model: str | None,
    output: str | None,
    allow_front_view: bool,
) -> None:
    """Run the full pose processing pipeline on a local video file.

    \b
    Stages:
      1. MediaPipe landmark extraction
      2. View angle classification
      3. Phase detection (descent / bottom / ascent)
      4. Per-phase resampling to fixed frame counts
      5. Joint angle extraction (knee / hip / back)

    VIDEO is the path to the local video file (mp4, mov, avi, …).
    """
    from autocoach.pose.extractor import PoseExtractionError
    from autocoach.pose.pipeline import PipelineError, PosePipeline

    model_path = Path(model) if model else None
    effective_id = video_id or video.stem

    _console.print("[bold]AutoCoach · Pose Processing Pipeline[/bold]")
    _console.print(f"  Video      : {video}")
    _console.print(f"  Lift type  : {lift_type}")
    _console.print(f"  Video ID   : {effective_id}")
    _console.print()

    pipe = PosePipeline(model_path=model_path, reject_front_view=not allow_front_view)

    try:
        features = pipe.process(video, video_id=video_id, lift_type=lift_type)
    except PoseExtractionError as exc:
        _err.print(f"[red]Extraction error:[/red] {exc}")
        sys.exit(1)
    except PipelineError as exc:
        _err.print(f"[red]Pipeline error:[/red] {exc}")
        sys.exit(1)

    # ---- Display results ---------------------------------------------------
    conf_colour = "green" if features.view_confidence >= 0.7 else "yellow"
    _console.print("[bold]Results[/bold]")
    _console.print(
        f"  View confidence : [{conf_colour}]{features.view_confidence:.2f}[/{conf_colour}]"
    )
    _console.print(f"  Dominant side   : {features.dominant_side}")
    _console.print(f"  Min knee angle  : {features.min_knee_angle:.1f}°")
    _console.print(f"  Min hip angle   : {features.min_hip_angle:.1f}°")
    _console.print(f"  Max back angle  : {features.max_back_angle:.1f}°")
    _console.print(f"  Total frames    : {len(features.knee_angles)}")

    phase_counts: dict[str, int] = {}
    for label in features.phase_labels:
        phase_counts[label] = phase_counts.get(label, 0) + 1
    _console.print()
    _console.print("[bold]Phase breakdown[/bold]")
    for phase, count in phase_counts.items():
        _console.print(f"  {phase:10s}: {count} frames")

    if output:
        out_path = Path(output)
        out_path.write_text(features.model_dump_json(indent=2))
        _console.print()
        _console.print(f"  JSON written to: {out_path}")
