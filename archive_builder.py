"""
Build static HTML archive pages and website homepage for published micro-seasons.
"""

from datetime import date
from pathlib import Path


def _fmt(month: int, day: int) -> str:
    return date(2000, month, day).strftime("%-d %b")

from jinja2 import Environment, FileSystemLoader


ARCHIVE_DIR = Path(__file__).parent / "archive"
TEMPLATE_DIR = Path(__file__).parent / "templates"
ROOT_DIR = Path(__file__).parent

ACCENT_COLORS = {
    "Spring": "#6b8f71",
    "Summer": "#c9734a",
    "Autumn": "#d4a853",
    "Winter": "#4a7fa5",
}


def _season_filename(season: dict) -> str:
    return f"{season['id']:02d}-{season['slug']}.html"


def build_archive(season: dict, content: dict, all_seasons: list) -> None:
    ARCHIVE_DIR.mkdir(exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    page_template = env.get_template("archive_page.html")
    today = date.today()
    accent_color = ACCENT_COLORS.get(season["major_season"].capitalize(), "#888780")
    date_range = f"{_fmt(season['start_month'], season['start_day'])} – {_fmt(season['end_month'], season['end_day'])}"
    html = page_template.render(
        season=season, content=content, today=today,
        accent_color=accent_color,
        date_range=date_range,
        duration_days=season["duration_days"],
    )

    filename = _season_filename(season)
    (ARCHIVE_DIR / filename).write_text(html, encoding="utf-8")
    print(f"Archive page written: archive/{filename}")

    _build_index(env, all_seasons)


def _build_index(env: Environment, all_seasons: list) -> None:
    published = []
    for s in all_seasons:
        filename = _season_filename(s)
        if (ARCHIVE_DIR / filename).exists():
            published.append({"season": s, "filename": filename})

    index_template = env.get_template("archive_index.html")
    html = index_template.render(published=published)
    (ARCHIVE_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Archive index updated — {len(published)} season(s) published.")


def build_website(season: dict, content: dict, worker_url: str = "https://subscribe.ko-72.com") -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("website.html")

    accent_color = ACCENT_COLORS.get(season["major_season"].capitalize(), "#888780")
    archive_page_url = f"/archive/{_season_filename(season)}"

    date_range = f"{_fmt(season['start_month'], season['start_day'])} – {_fmt(season['end_month'], season['end_day'])}"
    html = template.render(
        season=season,
        content=content,
        accent_color=accent_color,
        archive_page_url=archive_page_url,
        worker_url=worker_url,
        date_range=date_range,
        duration_days=season["duration_days"],
    )
    (ROOT_DIR / "index.html").write_text(html, encoding="utf-8")
    print("Website homepage rebuilt: index.html")
