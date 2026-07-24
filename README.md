# Kō 候

*Japan's 72 micro-seasons, one at a time.*

Kō is a bilingual newsletter and static site following Japan's 72 traditional
micro-seasons (七十二候, *shichijūni-kō*). Every five or six days it publishes a
short English and Japanese letter about the change in nature, what is in
season, a cultural practice, and a haiku.

## How it works

The production system has four parts:

1. `.github/workflows/newsletter.yml` runs daily at 01:00 UTC. On a
   micro-season's start date, `season_mailer.py` generates or loads bilingual
   content, sends the newsletter, and rebuilds the static site. Pushes to
   `main` and manual runs rebuild the site without sending email.
2. Claude generates bilingual content. `data/content_cache.json` stores one
   evergreen entry per season so subsequent builds do not regenerate it.
3. Buttondown is the subscriber source of truth and stores the `lang:en` or
   `lang:ja` preference. Resend delivers the rendered email. The optional
   `SUBSCRIBER_EMAILS` value is a bootstrap fallback, not a second subscriber
   list; normalized duplicates and addresses unsubscribed in Buttondown are
   skipped.
4. The Cloudflare Worker in `worker/` handles website subscribe and
   unsubscribe requests, updates Buttondown, and sends the bilingual welcome
   email through Resend.

`.github/workflows/season_check.yml` is retained as a manual-only recovery
workflow. It must not be scheduled alongside `newsletter.yml`, because two
scheduled mailers can send the same letter twice.

## Repository layout

```text
.
├── .github/workflows/
│   ├── newsletter.yml          # Production schedule and build workflow
│   └── season_check.yml        # Manual recovery workflow only
├── data/
│   ├── seasons.json            # All 72 seasons and calendar metadata
│   ├── strings.json            # English and Japanese interface strings
│   ├── content_cache.json      # Generated bilingual season content
│   ├── ingredients.json        # Generated ingredient reference data
│   └── dishes.json             # Generated dish reference data
├── templates/                  # Jinja templates for email and static pages
├── archive/                    # Generated English archive
├── ja/                         # Generated Japanese homepage and archive
├── season_mailer.py            # Pipeline orchestrator
├── content_generator.py        # Claude content generation
├── email_sender.py             # Buttondown subscriber fetch + Resend delivery
├── ingredient_generator.py     # Ingredient and dish lookup generation
├── archive_builder.py          # Homepage, archive, sitemap, unsubscribe pages
└── worker/
    ├── index.js                # Subscribe/unsubscribe Worker
    └── wrangler.toml           # Cloudflare Worker configuration
```

The generated English homepage is `index.html`. English archive pages live in
`archive/`; Japanese equivalents live under `ja/`. Builds also update
`sitemap.xml`, unsubscribe pages, the content cache, and lookup data.

## Local setup

Requires Python 3.12 or newer and Node.js for Worker development.

```bash
git clone https://github.com/zkutty/ko-72.git
cd ko-72
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a local `.env` when you need API-backed generation or delivery:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
RESEND_API_KEY=re_...
BUTTONDOWN_API_KEY=...
WORKER_URL=https://subscribe.ko-72.com

# Optional bootstrap fallback only. Prefer leaving this unset once Buttondown
# contains the real subscriber list.
SUBSCRIBER_EMAILS=
SUBSCRIBER_FALLBACK_LANG=en
```

Secrets and `.env` files are ignored by Git.

## Run the mailer

The normal command exits without changes unless today starts a micro-season:

```bash
python season_mailer.py
```

For a local static rebuild of the currently active season, without sending
mail:

```bash
python season_mailer.py --force --build-only
```

`--force` without `--build-only` sends email and bypasses the normal date and
send guards. Use it only for an intentional recovery or end-to-end delivery
test.

The build writes generated files directly into the repository. Review the Git
diff before committing them.

## GitHub Actions configuration

Add these repository secrets under **Settings → Secrets and variables →
Actions**:

| Secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Generate season content and ingredient/dish references |
| `RESEND_API_KEY` | Deliver newsletters |
| `BUTTONDOWN_API_KEY` | Read subscribers and language preferences |
| `WORKER_URL` | Public subscribe endpoint, normally `https://subscribe.ko-72.com` |
| `SUBSCRIBER_EMAILS` | Optional comma-separated bootstrap fallback; normally unset |

The production workflow runs every day at 01:00 UTC. A scheduled run sends
only when a new season begins. A push to `main` or a manual dispatch runs
`python season_mailer.py --force --build-only`, so it rebuilds static files but
does not email subscribers.

The workflow stages the English archive, homepage, sitemap, and content cache
and commits them back to `main` when they change. The build also renders the
Japanese tree, unsubscribe pages, and ingredient/dish lookup files locally;
review and stage those outputs explicitly when they change.

## Cloudflare Worker

The Worker requires its own Buttondown and Resend secrets. Set them with
Wrangler; they are separate from GitHub Actions secrets:

```bash
cd worker
npx wrangler secret put BUTTONDOWN_API_KEY
npx wrangler secret put RESEND_API_KEY
```

Run it locally:

```bash
npx wrangler dev
```

Deploy the configured `ko-72-subscribe` Worker:

```bash
npx wrangler deploy
```

Wrangler's `.wrangler/` directory is local cache/state and must never be
committed.

## Content and design

- Edit `templates/email.html` for the newsletter and the remaining templates
  for the website surfaces.
- Edit the prompts in `content_generator.py` and `ingredient_generator.py` to
  change generated content.
- Follow `BRAND.md` for colors, typography, and editorial voice.
- Season dates and names are defined in `data/seasons.json`.

## License

MIT
