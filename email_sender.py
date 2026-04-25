"""
Send the HTML newsletter email via the Resend API.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import date


def _fmt(month: int, day: int) -> str:
    return date(2000, month, day).strftime("%b %-d")
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from ingredient_generator import slugify

ACCENT_COLORS = {
    "Spring": "#6b8f71",
    "Summer": "#c9734a",
    "Autumn": "#d4a853",
    "Winter": "#4a7fa5",
}


def _load_lookup_keys() -> tuple[set[str], set[str]]:
    """Return the slug sets we have lookup entries for.

    The email only needs to know whether a given item has a popup on the
    archive page; the popup content itself lives there.
    """
    data_dir = Path(__file__).parent / "data"

    def _keys(name: str) -> set[str]:
        path = data_dir / name
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


def _get_subscribers() -> list[str]:
    """Fetch subscribers from Buttondown, falling back to SUBSCRIBER_EMAILS."""
    subscribers: set[str] = set()

    bd_key = os.environ.get("BUTTONDOWN_API_KEY", "").strip()
    if bd_key:
        req = urllib.request.Request(
            "https://api.buttondown.email/v1/subscribers?status=regular",
            headers={"Authorization": f"Token {bd_key}"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                for sub in data.get("results", []):
                    email = sub.get("email_address", "").strip()
                    if email:
                        subscribers.add(email)
        except urllib.error.URLError as e:
            print(f"Warning: could not fetch Buttondown subscribers: {e}")

    # Always include hardcoded fallback addresses
    for addr in os.environ.get("SUBSCRIBER_EMAILS", "").split(","):
        addr = addr.strip()
        if addr:
            subscribers.add(addr)

    return sorted(subscribers)


def send_email(season: dict, content: dict, worker_url: str = "https://subscribe.ko-72.com") -> None:
    resend.api_key = os.environ["RESEND_API_KEY"]

    recipients = _get_subscribers()
    if not recipients:
        raise ValueError("No subscribers found. Set SUBSCRIBER_EMAILS or BUTTONDOWN_API_KEY.")

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("email.html")

    today = date.today()
    accent_color = ACCENT_COLORS.get(season["major_season"].capitalize(), "#888780")
    archive_url = f"https://ko-72.com/archive/{season['id']:02d}-{season['slug']}.html"

    ingredient_keys, dish_keys = _load_lookup_keys()
    produce = _keyed_produce(content, ingredient_keys)
    dishes = _keyed_dishes(content, dish_keys)

    date_range = f"{_fmt(season['start_month'], season['start_day'])} – {_fmt(season['end_month'], season['end_day'])}"
    html = template.render(
        season=season,
        content=content,
        today=today,
        accent_color=accent_color,
        archive_url=archive_url,
        unsubscribe_url="https://ko-72.com/unsubscribe.html",
        date_range=date_range,
        duration_days=season["duration_days"],
        produce=produce,
        dishes=dishes,
    )

    sent = 0
    for recipient in recipients:
        params: resend.Emails.SendParams = {
            "from": "Kō <seasons@ko-72.com>",
            "to": [recipient],
            "subject": f"Kō · {season['name_en']} ({season['name_romaji']})",
            "html": html,
        }
        resend.Emails.send(params)
        sent += 1

    print(f"Email sent to {sent} subscriber(s).")
