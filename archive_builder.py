"""
Build static HTML archive pages for published micro-seasons.
"""

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


ARCHIVE_DIR = Path(__file__).parent / "archive"
TEMPLATE_DIR = Path(__file__).parent / "templates"


def _season_filename(season: dict) -> str:
    return f"{season['id']:02d}-{season['slug']}.html"


def build_archive(season: dict, content: dict, all_seasons: list) -> None:
    """Render and write an individual season page, then regenerate the index.

    Args:
        season: Season metadata dict from seasons.json.
        content: Generated content dict from content_generator.
        all_seasons: Full list of season dicts (for the index).
    """
    ARCHIVE_DIR.mkdir(exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    # ── individual season page ──────────────────────────────────────────────
    page_template = env.get_template("archive_page.html")
    today = date.today()
    html = page_template.render(season=season, content=content, today=today)

    filename = _season_filename(season)
    (ARCHIVE_DIR / filename).write_text(html, encoding="utf-8")
    print(f"Archive page written: archive/{filename}")

    # ── regenerate index ────────────────────────────────────────────────────
    _build_index(env, all_seasons)


def _build_index(env: Environment, all_seasons: list) -> None:
    """Regenerate archive/index.html listing all published seasons."""
    published = []
    for s in all_seasons:
        filename = _season_filename(s)
        if (ARCHIVE_DIR / filename).exists():
            published.append({"season": s, "filename": filename})

    index_template = env.get_template("archive_index.html")
    html = index_template.render(published=published)
    (ARCHIVE_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Archive index updated — {len(published)} season(s) published.")
