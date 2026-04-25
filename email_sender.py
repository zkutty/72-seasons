"""
Send the HTML newsletter email via the Resend API, in each subscriber's preferred language.

Subscribers are tagged ``lang:en`` or ``lang:ja`` in Buttondown. Untagged
subscribers default to English. Each language is rendered from the same
bilingual content payload via ``templates/email.html``.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from content_generator import normalize_content
from ingredient_generator import slugify

ACCENT_COLORS = {
    "Spring": "#6b8f71",
    "Summer": "#c9734a",
    "Autumn": "#d4a853",
    "Winter": "#4a7fa5",
}

LANGS = ("en", "ja")
DEFAULT_LANG = "en"
DATA_DIR = Path(__file__).parent / "data"
STRINGS_PATH = DATA_DIR / "strings.json"


def _fmt(month: int, day: int) -> str:
    return date(2000, month, day).strftime("%b %-d")


def _fmt_ja(month: int, day: int) -> str:
    return f"{month}月{day}日"


def _date_range(season: dict, lang: str) -> str:
    fmt = _fmt_ja if lang == "ja" else _fmt
    return f"{fmt(season['start_month'], season['start_day'])} – {fmt(season['end_month'], season['end_day'])}"


def _load_strings() -> dict:
    return json.loads(STRINGS_PATH.read_text(encoding="utf-8"))


def _load_lookup_keys() -> tuple[set[str], set[str]]:
    def _keys(name: str) -> set[str]:
        path = DATA_DIR / name
        if not path.exists():
            return set()
        return set(json.loads(path.read_text(encoding="utf-8")).keys())

    return _keys("ingredients.json"), _keys("dishes.json")


def _keyed_produce(content: dict, ingredient_keys: set[str]) -> dict:
    out: dict[str, list] = {}
    for category, items in content.get("seasonal_produce", {}).items():
        out[category] = [
            {"raw": raw, "key": slugify(raw) if slugify(raw) in ingredient_keys else None}
            for raw in items
        ]
    return out


def _keyed_dishes(content: dict, dish_keys: set[str]) -> list:
    out = []
    for d in content.get("seasonal_dishes", []):
        key = slugify(d.get("name", ""))
        out.append({
            "name": d.get("name", ""),
            "description": d.get("description", ""),
            "key": key if key in dish_keys else None,
        })
    return out


def _lang_from_tags(tags) -> str:
    """Extract language preference from Buttondown subscriber tags."""
    if not tags:
        return DEFAULT_LANG
    for tag in tags:
        # Tags may be objects ({"name": "lang:ja"}) or plain strings.
        name = tag.get("name") if isinstance(tag, dict) else tag
        if isinstance(name, str) and name.startswith("lang:"):
            value = name.split(":", 1)[1].strip().lower()
            if value in LANGS:
                return value
    return DEFAULT_LANG


def _get_subscribers() -> list[tuple[str, str]]:
    """Fetch (email, language) pairs from Buttondown, plus the env fallback."""
    subscribers: dict[str, str] = {}

    bd_key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if bd_key:
        url = "https://api.buttondown.email/v1/subscribers?status=regular"
        while url:
            req = urllib.request.Request(
                url,
                headers={"Authorization": f"Token {bd_key}"},
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    data = json.loads(resp.read())
            except urllib.error.URLError as e:
                print(f"Warning: could not fetch Buttondown subscribers: {e}")
                break
            for sub in data.get("results", []):
                email = sub.get("email_address", "").strip()
                if email:
                    subscribers[email] = _lang_from_tags(sub.get("tags"))
            url = data.get("next") or None

    fallback_lang = os.environ.get("SUBSCRIBER_FALLBACK_LANG", DEFAULT_LANG).strip().lower()
    if fallback_lang not in LANGS:
        fallback_lang = DEFAULT_LANG
    for addr in os.environ.get("SUBSCRIBER_EMAILS", "").split(","):
        addr = addr.strip()
        if addr and addr not in subscribers:
            subscribers[addr] = fallback_lang

    return sorted(subscribers.items())


def _render(template, season, content, lang, strings, accent_color, archive_url, unsubscribe_url):
    ingredient_keys, dish_keys = _load_lookup_keys()
    return template.render(
        lang=lang,
        t=strings[lang],
        season=season,
        content=content,
        accent_color=accent_color,
        archive_url=archive_url,
        unsubscribe_url=unsubscribe_url,
        date_range=_date_range(season, lang),
        duration_days=season["duration_days"],
        produce=_keyed_produce(content, ingredient_keys),
        dishes=_keyed_dishes(content, dish_keys),
    )


def _subject(season: dict, lang: str, strings: dict) -> str:
    if lang == "ja":
        return f"{strings['ja']['email_subject_prefix']} · {season['name_jp']}（{season['name_romaji']}）"
    return f"Kō · {season['name_en']} ({season['name_romaji']})"


def send_email(season: dict, content: dict, worker_url: str = "https://subscribe.ko-72.com") -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]

    recipients = _get_subscribers()
    if not recipients:
        raise ValueError("No subscribers found. Set SUBSCRIBER_EMAILS or BUTTONDOWN_API_KEY.")

    bilingual = normalize_content(content)
    strings = _load_strings()
    accent_color = ACCENT_COLORS.get(season["major_season"].capitalize(), "#888780")

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("email.html")

    rendered: dict[str, tuple[str, str]] = {}
    for lang in LANGS:
        if lang not in bilingual:
            continue
        slug_path = f"{season['id']:02d}-{season['slug']}.html"
        archive_url = (
            f"https://ko-72.com/ja/archive/{slug_path}" if lang == "ja"
            else f"https://ko-72.com/archive/{slug_path}"
        )
        unsubscribe_url = (
            "https://ko-72.com/ja/unsubscribe.html" if lang == "ja"
            else "https://ko-72.com/unsubscribe.html"
        )
        html = _render(
            template, season, bilingual[lang], lang, strings,
            accent_color, archive_url, unsubscribe_url,
        )
        rendered[lang] = (_subject(season, lang, strings), html)

    sent = {lang: 0 for lang in rendered}
    skipped: list[str] = []
    for recipient, lang in recipients:
        if lang not in rendered:
            # JA subscriber but no JA content yet (legacy cache before backfill) — fall back to EN.
            fallback = "en" if "en" in rendered else next(iter(rendered))
            skipped.append(f"{recipient} (wanted {lang}, sent {fallback})")
            lang = fallback
        subject, html = rendered[lang]
        params: resend.Emails.SendParams = {
            "from": "Kō <seasons@ko-72.com>",
            "to": [recipient],
            "subject": subject,
            "html": html,
        }
        resend.Emails.send(params)
        sent[lang] += 1

    summary = ", ".join(f"{lang}: {n}" for lang, n in sent.items() if n)
    print(f"Email sent — {summary}.")
    for note in skipped:
        print(f"  fallback: {note}")
