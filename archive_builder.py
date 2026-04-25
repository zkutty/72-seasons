"""
Build static HTML archive pages, index, website homepage and unsubscribe page,
in both English and Japanese.

Each surface is rendered once per language. English output goes to current
paths under the repo root; Japanese output goes under /ja/.
"""

import json
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from content_generator import normalize_content
from ingredient_generator import slugify
from wheel import cardinal_labels

ROOT_DIR     = Path(__file__).parent
ARCHIVE_DIR  = ROOT_DIR / "archive"
JA_ROOT_DIR  = ROOT_DIR / "ja"
JA_ARCHIVE_DIR = JA_ROOT_DIR / "archive"
TEMPLATE_DIR = ROOT_DIR / "templates"
DATA_DIR     = ROOT_DIR / "data"
STRINGS_PATH = DATA_DIR / "strings.json"

LANGS = ("en", "ja")

ACCENT_COLORS = {
    "spring": "#6b8f71",
    "summer": "#c9734a",
    "autumn": "#d4a853",
    "winter": "#4a7fa5",
}


def _fmt(month: int, day: int) -> str:
    return date(2000, month, day).strftime("%b %-d")  # "Apr 20"


def _fmt_ja(month: int, day: int) -> str:
    return f"{month}月{day}日"


def _date_range(season: dict, lang: str) -> str:
    fmt = _fmt_ja if lang == "ja" else _fmt
    return f"{fmt(season['start_month'], season['start_day'])} – {fmt(season['end_month'], season['end_day'])}"


def _season_filename(season: dict) -> str:
    return f"{season['id']:02d}-{season['slug']}.html"


def _accent(season: dict) -> str:
    return ACCENT_COLORS.get(season["major_season"].lower(), "#888780")


def _archive_dir(lang: str) -> Path:
    return JA_ARCHIVE_DIR if lang == "ja" else ARCHIVE_DIR


def _root_dir(lang: str) -> Path:
    return JA_ROOT_DIR if lang == "ja" else ROOT_DIR


def _published_ids(all_seasons: list) -> set:
    """A season is "published" if its EN archive page exists. Both languages share the same set."""
    return {s["id"] for s in all_seasons if (ARCHIVE_DIR / _season_filename(s)).exists()}


def _load_lookup() -> tuple[dict, dict]:
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _read(DATA_DIR / "ingredients.json"), _read(DATA_DIR / "dishes.json")


def _load_strings() -> dict:
    return json.loads(STRINGS_PATH.read_text(encoding="utf-8"))


def _slice_lookups(content: dict, ingredients: dict, dishes: dict) -> tuple[dict, dict]:
    """Return only the lookup entries that appear on this season's page."""
    page_ing: dict[str, dict] = {}
    page_dish: dict[str, dict] = {}

    for items in content.get("seasonal_produce", {}).values():
        for raw in items:
            key = slugify(raw)
            if key and key in ingredients:
                page_ing[key] = ingredients[key]

    for d in content.get("seasonal_dishes", []):
        key = slugify(d.get("name", ""))
        if key and key in dishes:
            page_dish[key] = dishes[key]

    return page_ing, page_dish


def _keyed_produce(content: dict, ingredients: dict) -> dict:
    out: dict[str, list] = {}
    for category, items in content.get("seasonal_produce", {}).items():
        out[category] = [
            {"raw": raw, "key": slugify(raw) if slugify(raw) in ingredients else None}
            for raw in items
        ]
    return out


def _keyed_dishes(content: dict, dishes: dict) -> list:
    out = []
    for d in content.get("seasonal_dishes", []):
        key = slugify(d.get("name", ""))
        out.append({
            "name": d.get("name", ""),
            "description": d.get("description", ""),
            "key": key if key in dishes else None,
        })
    return out


def _content_for_lang(content: dict, lang: str) -> dict:
    """Return the per-language slice from a bilingual content payload.

    If the requested language is missing (e.g. legacy entry without JA), fall
    back to English so the page still renders.
    """
    bilingual = normalize_content(content)
    return bilingual.get(lang) or bilingual["en"]


def _make_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


# ── Individual archive page ────────────────────────────────────────────────────

def build_archive(season: dict, content: dict, all_seasons: list) -> None:
    """Render this season's archive page in every supported language."""
    env = _make_env()
    strings = _load_strings()
    all_ingredients, all_dishes = _load_lookup()

    pub_ids = _published_ids(all_seasons)
    lower  = [s for s in all_seasons if s["id"] < season["id"] and s["id"] in pub_ids]
    higher = [s for s in all_seasons if s["id"] > season["id"] and s["id"] in pub_ids]
    prev   = lower[-1]  if lower  else None
    next_s = higher[0]  if higher else None

    today = date.today()
    published_date = date(today.year, season["start_month"], season["start_day"]).isoformat()

    template = env.get_template("archive_page.html")

    for lang in LANGS:
        lang_content = _content_for_lang(content, lang)
        page_ingredients, page_dishes = _slice_lookups(lang_content, all_ingredients, all_dishes)

        out_dir = _archive_dir(lang)
        out_dir.mkdir(parents=True, exist_ok=True)

        html = template.render(
            lang=lang,
            t=strings[lang],
            season=season,
            content=lang_content,
            accent_color=_accent(season),
            date_range=_date_range(season, lang),
            duration_days=season["duration_days"],
            published_date=published_date,
            prev=prev,
            next=next_s,
            all_seasons=all_seasons,
            produce=_keyed_produce(lang_content, all_ingredients),
            dishes=_keyed_dishes(lang_content, all_dishes),
            ingredient_lookup=page_ingredients,
            dish_lookup=page_dishes,
        )

        filename = _season_filename(season)
        (out_dir / filename).write_text(html, encoding="utf-8")
        print(f"Archive page written: {out_dir.relative_to(ROOT_DIR)}/{filename}")

    _build_index(env, strings, all_seasons)
    _build_unsubscribe(env, strings)
    _build_sitemap(all_seasons)


# ── Archive index ──────────────────────────────────────────────────────────────

def _build_index(env: Environment, strings: dict, all_seasons: list) -> None:
    pub_ids = _published_ids(all_seasons)
    published_count = len(pub_ids)
    template = env.get_template("archive_index.html")

    for lang in LANGS:
        out_dir = _archive_dir(lang)
        out_dir.mkdir(parents=True, exist_ok=True)
        html = template.render(
            lang=lang,
            t=strings[lang],
            all_seasons=all_seasons,
            published_count=published_count,
            published_ids=pub_ids,
        )
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"Archive index updated: {out_dir.relative_to(ROOT_DIR)}/index.html — {published_count} season(s) published.")


# ── Unsubscribe page ───────────────────────────────────────────────────────────

def _build_unsubscribe(env: Environment, strings: dict) -> None:
    template = env.get_template("unsubscribe.html")
    for lang in LANGS:
        out_dir = _root_dir(lang)
        out_dir.mkdir(parents=True, exist_ok=True)
        html = template.render(lang=lang, t=strings[lang])
        (out_dir / "unsubscribe.html").write_text(html, encoding="utf-8")
        print(f"Unsubscribe page written: {(out_dir / 'unsubscribe.html').relative_to(ROOT_DIR)}")


# ── Sitemap ────────────────────────────────────────────────────────────────────

def _build_sitemap(all_seasons: list) -> None:
    today = date.today().isoformat()

    def url(en_loc: str, ja_loc: str, changefreq: str, priority: str) -> str:
        return (
            f"  <url>\n"
            f"    <loc>{en_loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f'    <xhtml:link rel="alternate" hreflang="en" href="{en_loc}"/>\n'
            f'    <xhtml:link rel="alternate" hreflang="ja" href="{ja_loc}"/>\n'
            f'    <xhtml:link rel="alternate" hreflang="x-default" href="{en_loc}"/>\n'
            f"  </url>"
        )

    entries = [
        url("https://ko-72.com/",         "https://ko-72.com/ja/",         "weekly",  "1.0"),
        url("https://ko-72.com/archive/", "https://ko-72.com/ja/archive/", "monthly", "0.8"),
    ]
    for s in all_seasons:
        if (ARCHIVE_DIR / _season_filename(s)).exists():
            entries.append(url(
                f"https://ko-72.com/archive/{_season_filename(s)}",
                f"https://ko-72.com/ja/archive/{_season_filename(s)}",
                "yearly", "0.6",
            ))

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
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
    env = _make_env()
    strings = _load_strings()
    all_ingredients, all_dishes = _load_lookup()
    template = env.get_template("website.html")

    recent = [
        {"season": s, "url": s["url"]}
        for s in all_seasons
        if (ARCHIVE_DIR / _season_filename(s)).exists()
    ][-5:]

    for lang in LANGS:
        lang_content = _content_for_lang(content, lang)
        page_ingredients, page_dishes = _slice_lookups(lang_content, all_ingredients, all_dishes)
        # Rewrite recent URLs for the JA homepage so links land on /ja/archive/...
        if lang == "ja":
            recent_lang = [
                {"season": r["season"], "url": r["url"].replace("/archive/", "/ja/archive/")}
                for r in recent
            ]
        else:
            recent_lang = recent

        html = template.render(
            lang=lang,
            t=strings[lang],
            season=season,
            content=lang_content,
            accent_color=_accent(season),
            date_range=_date_range(season, lang),
            duration_days=season["duration_days"],
            all_seasons=all_seasons,
            recent=recent_lang,
            worker_url=worker_url,
            cardinals=cardinal_labels(),
            produce=_keyed_produce(lang_content, all_ingredients),
            dishes=_keyed_dishes(lang_content, all_dishes),
            ingredient_lookup=page_ingredients,
            dish_lookup=page_dishes,
        )
        out_dir = _root_dir(lang)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"Website homepage rebuilt: {(out_dir / 'index.html').relative_to(ROOT_DIR)}")
