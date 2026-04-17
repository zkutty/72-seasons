"""
72 Seasons — orchestrator.

Checks whether today is the first day of a new Japanese micro-season and,
if so, generates content, sends the newsletter, and builds the archive page.

Usage:
    python season_mailer.py            # runs only on a season-start date
    python season_mailer.py --force    # runs regardless of date (for testing)
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ── data helpers ───────────────────────────────────────────────────────────────

def load_seasons() -> list:
    path = Path(__file__).parent / "data" / "seasons.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["seasons"]


def find_todays_season(seasons: list, today: date) -> dict | None:
    """Return the season that starts exactly today, or None."""
    for s in seasons:
        if s["start_month"] == today.month and s["start_day"] == today.day:
            return s
    return None


def find_active_season(seasons: list, today: date) -> dict:
    """Return the most recently started season (used by --force).

    Handles year wrap correctly: for Jan 1–4, the active season is #72
    (which starts Jan 1); for Jan 5 onwards, season #1 takes over.
    """
    best: dict | None = None
    best_date: date | None = None

    for s in seasons:
        try:
            candidate = date(today.year, s["start_month"], s["start_day"])
        except ValueError:
            continue
        if candidate <= today:
            if best_date is None or candidate > best_date:
                best = s
                best_date = candidate

    if best is None:
        # Shouldn't happen with 72 seasons, but fall back to prior year's latest
        for s in seasons:
            try:
                candidate = date(today.year - 1, s["start_month"], s["start_day"])
            except ValueError:
                continue
            if best_date is None or candidate > best_date:
                best = s
                best_date = candidate

    if best is None:
        raise RuntimeError("Could not determine active season — seasons.json may be empty.")

    return best


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="72 Seasons newsletter mailer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run regardless of today's date, using the currently active micro-season.",
    )
    args = parser.parse_args()

    seasons = load_seasons()
    today = date.today()

    if args.force:
        season = find_active_season(seasons, today)
        log.info(
            "--force flag active · using season #%d: %s (%s)",
            season["id"], season["name_jp"], season["name_en"],
        )
    else:
        season = find_todays_season(seasons, today)
        if season is None:
            log.info("Today (%s) is not the start of a new micro-season — nothing to do.", today)
            sys.exit(0)
        log.info(
            "New micro-season begins today · #%d: %s (%s)",
            season["id"], season["name_jp"], season["name_en"],
        )

    # ── pipeline ──────────────────────────────────────────────────────────────
    from content_generator import generate_content
    from email_sender import send_email
    from archive_builder import build_archive

    log.info("Step 1/3 · Generating content with Claude …")
    content = generate_content(season)
    log.info("Content generated.")

    log.info("Step 2/3 · Sending email …")
    send_email(season, content)

    log.info("Step 3/3 · Building archive page …")
    build_archive(season, content, seasons)

    log.info("Done ✓")


if __name__ == "__main__":
    main()
