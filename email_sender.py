"""
Send the HTML newsletter email via the Resend API.
"""

import os
from datetime import date
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader


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
    html = template.render(season=season, content=content, today=today)

    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    date_str = f"{month_names[season['start_month']]} {season['start_day']}"

    subject = (
        f"七十二候 #{season['id']:02d}: {season['name_jp']} — "
        f"{season['name_en']} · {date_str}"
    )

    params: resend.Emails.SendParams = {
        "from": "72 Seasons <seasons@resend.dev>",
        "to": recipients,
        "subject": subject,
        "html": html,
    }

    response = resend.Emails.send(params)
    print(f"Email sent. Resend ID: {response['id']}")
