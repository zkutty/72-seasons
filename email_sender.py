"""
Send the HTML newsletter email via the Resend API.
"""

import os
from datetime import date
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

ACCENT_COLORS = {
    "Spring": "#6b8f71",
    "Summer": "#c9734a",
    "Autumn": "#d4a853",
    "Winter": "#4a7fa5",
}


def send_email(season: dict, content: dict) -> None:
    """Render the email template and dispatch to all subscribers.

    Args:
        season: Season metadata dict from seasons.json.
        content: Generated content dict from content_generator.
    """
    resend.api_key = os.environ["RESEND_API_KEY"]

    subscriber_str = os.environ.get("SUBSCRIBER_EMAILS", "").strip()
    if not subscriber_str:
        raise ValueError(
            "SUBSCRIBER_EMAILS environment variable is not set or empty. "
            "Provide a comma-separated list of recipient addresses."
        )
    recipients = [addr.strip() for addr in subscriber_str.split(",") if addr.strip()]
    if not recipients:
        raise ValueError("No valid email addresses found in SUBSCRIBER_EMAILS.")

    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
    template = env.get_template("email.html")

    today = date.today()
    accent_color = ACCENT_COLORS.get(season["major_season"].capitalize(), "#888780")
    archive_url = "https://github.com/zkutty/ko-72/tree/main/archive"
    html = template.render(season=season, content=content, today=today,
                           accent_color=accent_color, archive_url=archive_url)

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    date_str = f"{month_names[season['start_month']]} {season['start_day']}"

    subject = (
        f"Kō · {season['name_en']} ({season['name_romaji']})"
    )

    params: resend.Emails.SendParams = {
        "from": "Kō <seasons@ko-72.com>",
        "to": recipients,
        "subject": subject,
        "html": html,
    }

    response = resend.Emails.send(params)
    print(f"Email sent. Resend ID: {response['id']}")
