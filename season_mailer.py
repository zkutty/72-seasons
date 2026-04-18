"""
Kō — orchestrator.

Checks whether today is the first day of a new Japanese micro-season and,
if so, generates content, sends the newsletter, and builds the archive page.

Usage:
    python season_mailer.py            # runs only on a season-start date
    python season_mailer.py --force    # runs regardless of date (for testing)
"""

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CACHE_PATH = Path(__file__).parent / "data" / "content_cache.json"


# ── data helpers ───────────────────────────────────────────────────────────────

def enrich_seasons_with_end_dates(seasons: list, year: int = None) -> list:
    year = year or date.today().year
    enriched = []
    for i, season in enumerate(seasons):
        s = season.copy()
        next_s = seasons[i + 1] if i < len(seasons) - 1 else seasons[0]
        next_year = year if i < len(seasons) - 1 else year + 1
        next_start = date(next_year, next_s["start_month"], next_s["start_day"])
        end = next_start - timedelta(days=1)
        s["end_month"] = end.month
        s["end_day"] = end.day
        s["duration_days"] = (end - date(year, s["start_month"], s["start_day"])).days + 1
        enriched.append(s)
    return enriched


def load_seasons() -> list:
    path = Path(__file__).parent / "data" / "seasons.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)["seasons"]


def find_todays_season(seasons: list, today: date) -> dict | None:
    for s in seasons:
        if s["start_month"] == today.month and s["start_day"] == today.day:
            return s
    return None


def find_active_season(seasons: list, today: date) -> dict:
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


# ── content cache ──────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kō newsletter mailer",
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
    seasons = enrich_seasons_with_end_dates(seasons)
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
    from archive_builder import build_archive, build_website

    worker_url = os.environ.get("WORKER_URL", "https://subscribe.ko-72.com")

    # Step 1: content (from cache if available)
    cache = load_cache()
    cache_key = str(season["id"])
    if cache_key in cache:
        log.info("Step 1/4 · Using cached content for season #%d.", season["id"])
        content = cache[cache_key]
    else:
        log.info("Step 1/4 · Generating content with Claude …")
        content = generate_content(season)
        cache[cache_key] = content
        save_cache(cache)
        log.info("Content generated and cached.")

    log.info("Step 2/4 · Sending email …")
    send_email(season, content, worker_url=worker_url)

    log.info("Step 3/4 · Building archive page …")
    build_archive(season, content, seasons)

    log.info("Step 4/4 · Rebuilding website homepage …")
    build_website(season, content, worker_url=worker_url)

    log.info("Done ✓")


if __name__ == "__main__":
    main()
