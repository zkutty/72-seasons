"""
Build static HTML archive pages, index, and website homepage.
"""

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from wheel import cardinal_labels, sekki_ring, sekki_ring_small

ARCHIVE_DIR = Path(__file__).parent / "archive"
TEMPLATE_DIR = Path(__file__).parent / "templates"
ROOT_DIR     = Path(__file__).parent

ACCENT_COLORS = {
    "spring": "#6b8f71",
    "summer": "#c9734a",
    "autumn": "#d4a853",
    "winter": "#4a7fa5",
}


def _fmt(month: int, day: int) -> str:
    return date(2000, month, day).strftime("%b %-d")  # "Apr 20"


def _date_range(season: dict) -> str:
    return f"{_fmt(season['start_month'], season['start_day'])} – {_fmt(season['end_month'], season['end_day'])}"


def _season_filename(season: dict) -> str:
    return f"{season['id']:02d}-{season['slug']}.html"


def _accent(season: dict) -> str:
    return ACCENT_COLORS.get(season["major_season"].lower(), "#888780")


def _published_ids(all_seasons: list) -> set:
    return {s["id"] for s in all_seasons if (ARCHIVE_DIR / _season_filename(s)).exists()}


# ── Individual archive page ────────────────────────────────────────────────────

def build_archive(season: dict, content: dict, all_seasons: list) -> None:
    ARCHIVE_DIR.mkdir(exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    pub_ids = _published_ids(all_seasons)
    # prev = nearest lower published id; next = nearest higher published id
    lower  = [s for s in all_seasons if s["id"] < season["id"] and s["id"] in pub_ids]
    higher = [s for s in all_seasons if s["id"] > season["id"] and s["id"] in pub_ids]
    prev   = lower[-1]  if lower  else None
    next_s = higher[0]  if higher else None

    today = date.today()
    published_date = date(today.year, season["start_month"], season["start_day"]).isoformat()

    html = env.get_template("archive_page.html").render(
        season=season,
        content=content,
        accent_color=_accent(season),
        date_range=_date_range(season),
        duration_days=season["duration_days"],
        published_date=published_date,
        prev=prev,
        next=next_s,
        all_seasons=all_seasons,
        sekki_ring_sm=sekki_ring_small(all_seasons),
    )

    filename = _season_filename(season)
    (ARCHIVE_DIR / filename).write_text(html, encoding="utf-8")
    print(f"Archive page written: archive/{filename}")

    _build_index(env, all_seasons)
    _build_sitemap(all_seasons)


# ── Archive index ──────────────────────────────────────────────────────────────

def _build_index(env: Environment, all_seasons: list) -> None:
    pub_ids = _published_ids(all_seasons)
    published_count = len(pub_ids)
    html = env.get_template("archive_index.html").render(
        all_seasons=all_seasons,
        published_count=published_count,
        published_ids=pub_ids,
    )
    (ARCHIVE_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"Archive index updated — {published_count} season(s) published.")


# ── Sitemap ────────────────────────────────────────────────────────────────────

def _build_sitemap(all_seasons: list) -> None:
    today = date.today().isoformat()

    def url(loc: str, changefreq: str, priority: str) -> str:
        return (
            f"  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    entries = [
        url("https://ko-72.com/", "weekly", "1.0"),
        url("https://ko-72.com/archive/", "monthly", "0.8"),
    ]
    for s in all_seasons:
        if (ARCHIVE_DIR / _season_filename(s)).exists():
            entries.append(url(
                f"https://ko-72.com/archive/{_season_filename(s)}",
                "yearly", "0.6",
            ))

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    (ROOT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    print("Sitemap rebuilt: sitemap.xml")


# ── Website homepage ───────────────────────────────────────────────────────────

def build_website(
    season: dict,
    content: dict,
    all_seasons: list,
    worker_url: str = "https://subscribe.ko-72.com",
) -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)

    # Recent: last 5 published seasons (for the "Recently" block)
    recent = [
        {"season": s, "url": s["url"]}
        for s in all_seasons
        if (ARCHIVE_DIR / _season_filename(s)).exists()
    ][-5:]

    html = env.get_template("website.html").render(
        season=season,
        content=content,
        accent_color=_accent(season),
        date_range=_date_range(season),
        duration_days=season["duration_days"],
        all_seasons=all_seasons,
        recent=recent,
        worker_url=worker_url,
        cardinals=cardinal_labels(),
        sekki_ring=sekki_ring(all_seasons),
    )
    (ROOT_DIR / "index.html").write_text(html, encoding="utf-8")
    print("Website homepage rebuilt: index.html")
