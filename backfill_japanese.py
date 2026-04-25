"""
One-shot script: regenerate every cached season's content as a bilingual payload
and rebuild every static page in both English and Japanese.

Idempotent — entries that already contain a "ja" block are skipped unless
``--force`` is passed.

Usage:
    python backfill_japanese.py            # backfill missing JA, rebuild pages
    python backfill_japanese.py --force    # regenerate every season
    python backfill_japanese.py --dry-run  # show what would happen, don't call Claude
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from archive_builder import build_archive, build_website
from content_generator import generate_content, normalize_content
from season_mailer import enrich_seasons_with_end_dates, load_cache, load_seasons, save_cache

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

ARCHIVE_DIR = Path(__file__).parent / "archive"


def _season_filename(season: dict) -> str:
    return f"{season['id']:02d}-{season['slug']}.html"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Japanese content into the cache and rebuild.")
    parser.add_argument("--force", action="store_true", help="Regenerate every season, even if JA already present.")
    parser.add_argument("--dry-run", action="store_true", help="Skip Claude calls; only show what would happen.")
    parser.add_argument("--skip-build", action="store_true", help="Skip rebuilding the static pages.")
    args = parser.parse_args()

    seasons = enrich_seasons_with_end_dates(load_seasons())
    from wheel import augment_seasons
    seasons = augment_seasons(seasons)
    seasons_by_id = {str(s["id"]): s for s in seasons}

    cache = load_cache()
    if not cache:
        log.error("Cache is empty — nothing to backfill.")
        sys.exit(1)

    to_process = []
    for key, content in cache.items():
        bilingual = normalize_content(content)
        has_ja = "ja" in bilingual and isinstance(bilingual["ja"], dict)
        if has_ja and not args.force:
            log.info("Season #%s already bilingual — skipping.", key)
            continue
        to_process.append(key)

    if not to_process:
        log.info("Nothing to backfill (use --force to regenerate everything).")
    else:
        log.info("Will process %d season(s): %s", len(to_process), ", ".join(to_process))

    for key in to_process:
        season = seasons_by_id.get(key)
        if not season:
            log.warning("Cache key %s has no matching season in seasons.json — skipping.", key)
            continue
        if args.dry_run:
            log.info("[dry-run] would regenerate season #%s (%s).", key, season["name_en"])
            continue
        log.info("Regenerating season #%s (%s) with bilingual prompt …", key, season["name_en"])
        new_payload = generate_content(season)
        cache[key] = new_payload
        save_cache(cache)
        log.info("  → cached EN+JA for season #%s.", key)

    if args.skip_build:
        log.info("Skipping page rebuild (--skip-build).")
        return

    log.info("Rebuilding all pages in both languages …")
    most_recent = None
    for s in seasons:
        if (ARCHIVE_DIR / _season_filename(s)).exists():
            most_recent = s
        if str(s["id"]) in cache:
            build_archive(s, cache[str(s["id"])], seasons)

    if most_recent and str(most_recent["id"]) in cache:
        build_website(most_recent, cache[str(most_recent["id"])], all_seasons=seasons)
    log.info("Done ✓")


if __name__ == "__main__":
    main()
