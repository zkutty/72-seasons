# Kō Brand Kit
> Japan's 72 micro-seasons, one at a time

---

## Identity

| | |
|---|---|
| Name | Kō |
| Kanji | 候 |
| Tagline | Japan's 72 micro-seasons, one at a time |
| Subject line format | `Kō · {season_name_en} ({name_romaji})` |
| Email from-name | Kō |
| Established | April 2026 |

---

## Color Palette

| Name | CSS var | Hex | Usage |
|---|---|---|---|
| Ink | `--ink` | `#1a1a18` | Dark surfaces, email header bg, topbars |
| Earth | `--earth` | `#4a3728` | Subheadings, rich accents, JP season names on web |
| Deep ink | `--deep` | `#2c2c2a` | Body text on light backgrounds |
| Stone | `--stone` | `#888780` | Muted text, secondary elements, metadata |
| Rule | `--rule` | `#d8d5ce` | Dividers, borders, section rules |
| Shell | `--shell` | `#e8e5de` | Opening band background (slightly darker than washi) |
| Tint | `--tint` | `#edeae3` | Hover states, subtle panel fills |
| Washi | `--washi` | `#f5f3ee` | Page/email body bg, light surfaces |

### Seasonal Accent Colors

One accent color flows through the entire surface via a single `--accent` CSS variable, set per season.

| Season | Color name | Hex | CSS var |
|---|---|---|---|
| Spring | Bamboo | `#6b8f71` | `--spring` |
| Summer | Persimmon | `#c9734a` | `--summer` |
| Autumn | Harvest gold | `#d4a853` | `--autumn` |
| Winter | Winter sky | `#4a7fa5` | `--winter` |

In code (note: `major_season` field is **lowercase** in `seasons.json`):
```python
ACCENT_COLORS = {
    "spring": "#6b8f71",
    "summer": "#c9734a",
    "autumn": "#d4a853",
    "winter": "#4a7fa5",
}
```

---

## Typography

### Fonts

| Role | Stack | CSS var |
|---|---|---|
| Serif | `Georgia, 'Times New Roman', serif` | `--serif` |
| Sans | `system-ui, -apple-system, 'Segoe UI', sans-serif` | `--sans` |
| Mincho (Japanese) | `'Hiragino Mincho ProN', 'Yu Mincho', 'MS Mincho', Georgia, serif` | `--mincho` |
| Mono | `ui-monospace, 'SF Mono', Menlo, monospace` | `--mono` |

### Rules
- **Season names, opening paragraphs, haiku** → serif (`--serif`)
- **Japanese characters** → Mincho (`--mincho`) for display, sans otherwise
- **UI labels, metadata, section headers, body copy** → sans-serif (`--sans`)
- **Numbers, dates, codes** → mono (`--mono`)
- Never mix serif and sans-serif within the same element

### Scale — Email

| Role | Size | Weight | Style | Color |
|---|---|---|---|---|
| Logo "Kō" | 22px | 400 | serif | Washi `#f5f3ee` |
| Season label | 11px uppercase, 0.1em tracking | 500 | sans | Seasonal accent |
| Display (season name) | 26–32px | 400 | serif | Washi `#f5f3ee` |
| Romaji subtitle | 14px | 400 | sans | Stone `#888780` |
| Body copy | 15px, line-height 1.8 | 400 | sans | Deep ink `#2c2c2a` |
| Haiku | 15px, line-height 2.2 | 400 | serif italic | Stone `#888780` |
| Footer / meta | 11px | 400 | sans | Stone `#888780` |

### Scale — Web (landing + archive)

| Role | Size | Weight | Style | Color |
|---|---|---|---|---|
| Archive index title | 96px, line-height 0.95, tracking -0.04em | 400 | serif | Deep `#2c2c2a` |
| Landing h1 display | 72px, line-height 0.98, tracking -0.03em | 400 | serif | Deep `#2c2c2a` |
| Archive page title | 56px, line-height 1.05, tracking -0.02em | 400 | serif | Deep `#2c2c2a` |
| Giant kanji (rail) | 108px, line-height 1, tracking 0.04em | — | Mincho | Deep `#2c2c2a` |
| Haiku JP (archive page) | 32px Mincho, line-height 1.9 | — | Mincho | Deep `#2c2c2a` |
| Haiku JP (landing) | 34px Mincho | — | Mincho | Deep `#2c2c2a` |
| Opening dropcap | 140px (landing) / 72px (archive page) | — | serif | Accent |
| Section kicker | 11px uppercase, 0.14–0.16em tracking | — | sans | Accent |
| Body copy | 15px, line-height 1.6 | 400 | sans | Deep `#2c2c2a` |
| Meta / mono labels | 11px | — | mono | Stone `#888780` |

---

## Email Header Structure

Dark band — background: Ink `#1a1a18`, padding: 32px 36px 28px

1. **Logo row** — "Kō" in 22px serif Washi + "候" in 14px sans Stone, baseline-aligned, gap 10px
2. **Hairline rule** — 0.5px, `#333330`, margin 20px 0
3. **Season label** — `Spring · Micro-season 01 of 72 · Feb 4` in 11px uppercase, 0.1em tracking, seasonal accent color
4. **Season name** — serif 26px, Washi `#f5f3ee`, weight 400, letter-spacing -0.01em
5. **Romaji / kanji** — 14px sans, Stone `#888780`

---

## Email Body Structure

Light band — background: Washi `#f5f3ee`, padding: 28px 36px, max-width: 600px centered

Section order:
1. Opening paragraph (serif, 17px, generous line-height)
2. Nature notes (sans body)
3. Produce table — 3 columns: Fruits / Vegetables / Fish, seasonal accent color headers
4. Seasonal dishes — dish name in bold, description in muted text below
5. Cultural note — left-border accent in seasonal color, slightly inset
6. Haiku — centered, serif italic, Stone, generous vertical whitespace
7. Closing line — centered, 13px, Stone
8. Footer — "View in browser · Archive · Unsubscribe", 11px, Stone, centered

Section dividers: `0.5px solid #d8d5ce`

---

## Web Surfaces

### Landing (`templates/website.html`)

- Max-width: **1100px**
- Layout: full-bleed sections, 56px horizontal padding (24px mobile)
- Hero: two-column grid — left meta + h1 display, right 440×440 SVG season wheel
- SVG wheel: 72 arc segments, current season full accent, others at `{accent}28` (~16% alpha)
- Opening band: `background: var(--shell)`, dropcap 140px accent, 22px serif body
- Subscribe band: Ink bg, two-column
- Recent letters: 5-column list (num / JP / EN / romaji / date), links to archive pages
- Footer: Ink bg, 3-col (`2fr 1fr 1fr`)

### Archive Index (`templates/archive_index.html`)

- Full-bleed broadsheet, 48px horizontal padding
- Title: "The Year, in seventy-two." — 96px serif
- Four columns: Spring / Summer / Autumn / Winter, each with 3px top border in its accent color
- Published entries: `<a>` links; unpublished: `<span>` at opacity 0.42
- Bottom meta row: per-season published/total counts

### Archive Page (`templates/archive_page.html`)

- Max-width: **980px**, 64px column gap
- Two-column: 260px left rail + 1fr article (internal max-width 580px)
- Rail: giant 108px kanji, 140×140 year ring SVG, TLDR block, prev/next links
- Article: dropcap opening, nature notes, produce grid, dishes, cultural note, haiku band
- Section-head pattern: 11px uppercase accent, `::before` 14×1px accent dash

### Responsive breakpoint: 860px

Hero, spread, subscribe collapse to single column; rail moves above article.

---

## Voice & Tone

**Observational, specific, never enthusiastic.**
More field notes than lifestyle blog. Lead with nature, then food, then culture.

### Do
- "The warbler has not yet appeared, but the ice is listening."
- "Buri — yellowtail — reaches its peak fat content in winter. The Japanese call this kan-buri, the cold-season fish."
- "A stillness breaks that has held since the solstice — not warmth exactly, but the memory of it."

### Don't
- "Spring is here! Check out these amazing seasonal foods you need to try right now."
- "Yellowtail is a popular fish in Japan that people eat in winter because it tastes good."
- Exclamation marks, superlatives, lifestyle-magazine energy

---

## Copyright & Legal

- Established: April 2026
- Copyright line: `© 2026 Kō. All rights reserved.`
- Privacy: no cookies, no tracking — state this in every page footer
- Email footer: include unsubscribe link on every send

---

## Usage Notes for Claude Code

When any prompt touches `templates/email.html`, `templates/archive_page.html`, `templates/website.html`, or any file that generates content:

1. Read this file first
2. `major_season` in `seasons.json` is **lowercase** (`"spring"`, not `"Spring"`) — use lowercase keys in all dicts and template lookups
3. Apply `ACCENT_COLORS` mapping based on `season["major_season"]`
4. Pass `accent_color` as a template variable; set `--accent` on `:root` in CSS
5. Follow the typography split — Mincho for display Japanese, serif for season names and haiku, sans for everything else
6. Match the voice guidelines when writing or evaluating generated content
7. SVG arc/ring paths are pre-computed by `wheel.py` — never compute trig in Jinja2
