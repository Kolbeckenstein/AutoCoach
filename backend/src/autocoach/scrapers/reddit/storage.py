"""JSON-based persistence for scraped Reddit posts."""

import json
import logging
from pathlib import Path

from autocoach.scrapers.reddit.models import LiftPost

logger = logging.getLogger(__name__)

_MANIFEST_FILENAME = "seen_ids.json"


class ScraperStorage:
    """Persist LiftPost objects as JSON files organised by lift type.

    Directory layout::

        output_dir/
            Squat/
                <post_id>.json
                ...
            Deadlift/
                ...
            seen_ids.json   ← manifest of all known post IDs
    """

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Post persistence
    # ------------------------------------------------------------------

    def save_post(self, post: LiftPost) -> Path:
        """Serialise post to <output_dir>/<lift_type>/<post_id>.json.

        Overwrites any existing file for the same post ID.

        Returns:
            Path to the written file.
        """
        dest_dir = self.output_dir / post.lift_type
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest = dest_dir / f"{post.id}.json"
        dest.write_text(post.model_dump_json(indent=2), encoding="utf-8")
        logger.debug("Saved post %s → %s", post.id, dest)
        return dest

    # ------------------------------------------------------------------
    # Seen-ID manifest
    # ------------------------------------------------------------------

    def load_seen_ids(self) -> set[str]:
        """Return all post IDs that are already on disk.

        Merges two sources so neither can go missing:
        - The manifest file (fast, written by save_seen_ids)
        - A scan of existing post JSON files (catches files written without
          going through save_seen_ids)
        """
        ids: set[str] = set()

        # Source 1: manifest file
        manifest = self.output_dir / _MANIFEST_FILENAME
        if manifest.exists():
            ids.update(json.loads(manifest.read_text(encoding="utf-8")))

        # Source 2: post files already on disk
        for json_file in self.output_dir.rglob("*.json"):
            if json_file.name == _MANIFEST_FILENAME:
                continue
            ids.add(json_file.stem)

        return ids

    def save_seen_ids(self, ids: set[str]) -> None:
        """Persist the seen-ID set to the manifest file.

        This is a convenience cache — load_seen_ids() works without it, but
        writing the manifest avoids a full directory scan on subsequent runs.
        """
        manifest = self.output_dir / _MANIFEST_FILENAME
        manifest.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")
        logger.debug("Saved %d seen IDs to manifest", len(ids))
