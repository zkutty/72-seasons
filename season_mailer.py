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


# ── dish variety helpers ───────────────────────────────────────────────────────

_LANG_KEYS = ("en", "ja")


def _entry_lang_block(entry: dict, lang: str) -> dict | None:
    """Return the language block of a cache entry.

    Newer entries have ``{"en": {...}, "ja": {...}}``; legacy entries are flat
    English content (no top-level ``"en"`` key). Treat legacy entries as the EN
    block and as having no JA block.
    """
    if not isinstance(entry, dict):
        return None
    if "en" in entry and isinstance(entry["en"], dict):
        block = entry.get(lang)
        return block if isinstance(block, dict) else None
    return entry if lang == "en" else None


def collect_used_dishes(cache: dict, exclude_id: str | None = None) -> dict:
    """Return ``{"en": set[str], "ja": set[str]}`` of normalized dish names
    already featured in cached seasons (excluding the current season's id)."""
    from content_generator import normalize_dish_name

    used = {lang: set() for lang in _LANG_KEYS}
    for sid, entry in cache.items():
        if exclude_id is not None and sid == exclude_id:
            continue
        for lang in _LANG_KEYS:
            block = _entry_lang_block(entry, lang)
            if not block:
                continue
            for dish in block.get("seasonal_dishes") or []:
                name = normalize_dish_name(dish.get("name", "") if isinstance(dish, dict) else "")
                if name:
                    used[lang].add(name)
    return used


def count_new_dishes_per_lang(content: dict, used: dict) -> dict:
    """Return ``{"en": int, "ja": int}`` — how many dishes in each language
    block are not present in the corresponding ``used`` set."""
    from content_generator import normalize_dish_name

    counts = {}
    for lang in _LANG_KEYS:
        block = _entry_lang_block(content, lang)
        if not block:
            counts[lang] = 0
            continue
        new_count = 0
        for dish in block.get("seasonal_dishes") or []:
            name = normalize_dish_name(dish.get("name", "") if isinstance(dish, dict) else "")
            if name and name not in used.get(lang, set()):
                new_count += 1
        counts[lang] = new_count
    return counts


def generate_with_dish_variety(season: dict, used: dict, min_new: int = 2, max_attempts: int = 2) -> dict:
    """Generate valid content, retrying prompt misses and weak dish variety.

    ``generate_content`` validates that English produce has readable English
    labels. A validation/JSON failure consumes an attempt but is never cached
    or sent. For valid content, the existing dish-variety retry behavior still
    applies.
    """
    from content_generator import generate_content, normalize_dish_name

    exclude = {lang: set(used.get(lang, set())) for lang in _LANG_KEYS}
    last_content: dict | None = None
    last_error: ValueError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            content = generate_content(season, exclude_dishes=exclude)
        except ValueError as exc:
            last_error = exc
            log.warning(
                "Attempt %d returned invalid bilingual content — retrying: %s",
                attempt, exc,
            )
            continue
        counts = count_new_dishes_per_lang(content, used)
        worst_lang = min(counts, key=lambda k: counts[k])
        if counts[worst_lang] >= min_new:
            log.info(
                "Dish variety OK · new dishes per language: %s",
                ", ".join(f"{k}={v}" for k, v in counts.items()),
            )
            return content
        log.warning(
            "Attempt %d returned only %d new dish(es) in '%s' (need %d) — retrying with stronger exclusion list.",
            attempt, counts[worst_lang], worst_lang, min_new,
        )
        for lang in _LANG_KEYS:
            block = _entry_lang_block(content, lang)
            if not block:
                continue
            for dish in block.get("seasonal_dishes") or []:
                name = normalize_dish_name(dish.get("name", "") if isinstance(dish, dict) else "")
                if name:
                    exclude[lang].add(name)
        last_content = content

    if last_content is None:
        raise RuntimeError(
            f"Could not generate valid bilingual content after {max_attempts} attempts."
        ) from last_error

    log.warning(
        "Could not produce %d new dishes per language after %d attempts — using the last attempt anyway.",
        min_new, max_attempts,
    )
    return last_content  # type: ignore[return-value]


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
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="Rebuild static files (archive, sitemap, homepage) without sending email.",
    )
    args = parser.parse_args()

    seasons = load_seasons()
    seasons = enrich_seasons_with_end_dates(seasons)
    from wheel import augment_seasons
    seasons = augment_seasons(seasons)
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
    from email_sender import send_email
    from archive_builder import build_archive, build_website
    from ingredient_generator import run as generate_lookups

    worker_url = os.environ.get("WORKER_URL", "https://subscribe.ko-72.com")

    # Step 1: content (from cache if available)
    cache = load_cache()
    cache_key = str(season["id"])
    if cache_key in cache:
        log.info("Step 1/5 · Using cached content for season #%d.", season["id"])
        content = cache[cache_key]
    else:
        log.info("Step 1/5 · Generating content with Claude …")
        used_dishes = collect_used_dishes(cache, exclude_id=cache_key)
        log.info(
            "Steering away from %d previously used English dish name(s) and %d Japanese.",
            len(used_dishes["en"]), len(used_dishes["ja"]),
        )
        content = generate_with_dish_variety(season, used_dishes)
        cache[cache_key] = content
        save_cache(cache)
        log.info("Content generated and cached.")

    log.info("Step 2/5 · Generating any new ingredient / dish lookups …")
    stats = generate_lookups()
    if stats["ingredients_added"] or stats["dishes_added"]:
        log.info(
            "Added %d ingredient(s) and %d dish(es) to lookup store.",
            stats["ingredients_added"], stats["dishes_added"],
        )

    today_iso = today.isoformat()
    already_sent_on = cache.get(cache_key, {}).get("_sent_on")
    if args.build_only:
        log.info("Step 3/5 · Skipping email (--build-only).")
    elif already_sent_on == today_iso and not args.force:
        log.info(
            "Step 3/5 · Email already sent today (%s) for season #%d — skipping. "
            "Pass --force to resend.",
            today_iso, season["id"],
        )
    else:
        log.info("Step 3/5 · Sending email …")
        send_email(season, content, worker_url=worker_url)
        # Record the send so a second cron run on the same day skips us.
        cache.setdefault(cache_key, {})["_sent_on"] = today_iso
        save_cache(cache)

    log.info("Step 4/5 · Building archive page …")
    build_archive(season, content, seasons)

    log.info("Step 5/5 · Rebuilding website homepage …")
    build_website(season, content, all_seasons=seasons, worker_url=worker_url)

    log.info("Done ✓")


if __name__ == "__main__":
    main()
