# 七十二候 — 72 Seasons

A newsletter automation that sends a beautiful HTML email at the start of each of Japan's 72 micro-seasons (七十二候, *shichijūni-kō*) — the traditional Japanese solar calendar that divides the year into five-day increments, each named for a subtle natural phenomenon.

## What it does

On the first day of each micro-season, a GitHub Actions workflow:

1. Calls the Claude API to generate poetic, seasonally-specific content (nature notes, seasonal produce, dishes, haiku, and a cultural note)
2. Sends a beautiful HTML newsletter to your subscriber list via Resend
3. Commits a static archive page to the repository

## Project structure

```
72-seasons/
├── .github/workflows/season_check.yml   # Daily cron at 7am PT
├── data/seasons.json                    # All 72 micro-seasons with dates & names
├── templates/
│   ├── email.html                       # Jinja2 HTML email template
│   ├── archive_page.html                # Individual season archive page
│   └── archive_index.html              # Archive listing index
├── archive/                             # Generated static pages (auto-committed)
│   └── index.html
├── season_mailer.py                     # Orchestrator — run this
├── content_generator.py                 # Claude API integration
├── email_sender.py                      # Resend email dispatch
├── archive_builder.py                   # Static site generator
└── requirements.txt
```

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/YOUR_USERNAME/72-seasons.git
cd 72-seasons
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a `.env` file

```bash
cp .env.example .env   # or create from scratch
```

Add your credentials to `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
RESEND_API_KEY=re_...
SUBSCRIBER_EMAILS=you@example.com,friend@example.com
```

- **ANTHROPIC_API_KEY** — Get one at [console.anthropic.com](https://console.anthropic.com)
- **RESEND_API_KEY** — Get one at [resend.com](https://resend.com). You'll also need to verify a sending domain and update the `from:` address in `email_sender.py`
- **SUBSCRIBER_EMAILS** — Comma-separated list of recipient email addresses

### 3. Test locally with `--force`

The `--force` flag bypasses the date check and uses the currently active micro-season:

```bash
python season_mailer.py --force
```

This will:
- Call Claude to generate content
- Send an email to your SUBSCRIBER_EMAILS list
- Write a page to `archive/` and regenerate `archive/index.html`

### 4. Check the output

- Open `archive/index.html` in a browser to see the archive listing
- Open `archive/01-seri-sunawachi-sakau.html` (or whichever season ran) to preview the page

## GitHub Actions setup

The workflow runs daily at 15:00 UTC (7:00 AM Pacific Standard Time). It only sends an email when today matches a season's start date — otherwise it exits cleanly.

### Add secrets to your repository

Go to **Settings → Secrets and variables → Actions** and add:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `RESEND_API_KEY` | Your Resend API key |
| `SUBSCRIBER_EMAILS` | Comma-separated email list |

### Manual trigger

You can also trigger the workflow manually from the **Actions** tab with the optional `force` checkbox to run regardless of today's date.

## Customization

- **Sending domain**: Update the `from:` address in `email_sender.py` once you've verified a domain with Resend
- **Email design**: Edit `templates/email.html` — it uses inline CSS for email client compatibility
- **Content style**: Adjust the prompt in `content_generator.py` to shift the tone or add fields
- **Archive**: The `archive/` directory is auto-committed by the GitHub Actions workflow; you can host it on GitHub Pages

## The 72 micro-seasons

The 七十二候 are a Japanese adaptation of the Chinese 72 pentads, tied to the 24 solar terms (二十四節気). Each five-day period is named for a specific natural phenomenon — the cry of a pheasant, the thawing of springs, the first appearance of fireflies. They were first adopted in Japan in 1685 and remain a living part of traditional Japanese culture.

The seasons in `data/seasons.json` use the standard modern Japanese dates.

## License

MIT
