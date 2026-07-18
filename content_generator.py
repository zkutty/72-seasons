"""
Generate poetic newsletter content for a 72 micro-seasons entry using Claude.

Returns a bilingual payload of the shape ``{"en": {...}, "ja": {...}}`` so the
website, archive pages and email can render in either language from a single
LLM call.
"""

import json
import os
import re

import anthropic


_ASCII_LETTER_RE = re.compile(r"[A-Za-z]")
_PRODUCE_CATEGORIES = ("fruits", "vegetables", "fish")


def validate_english_produce(payload: dict) -> None:
    """Reject English produce entries that contain no readable Latin label.

    Japanese names are welcome in the English block, but they must be paired
    with an English common name such as ``茗荷 (myoga ginger)``. This guard runs
    before newly generated content is cached or sent, preventing a prompt miss
    from becoming a Japanese-only English newsletter.
    """
    en = payload.get("en") if isinstance(payload, dict) else None
    produce = en.get("seasonal_produce") if isinstance(en, dict) else None
    if not isinstance(produce, dict):
        raise ValueError("English content is missing seasonal_produce.")

    missing: list[str] = []
    for category in _PRODUCE_CATEGORIES:
        items = produce.get(category)
        if not isinstance(items, list):
            raise ValueError(f"English seasonal_produce.{category} must be a list.")
        for index, item in enumerate(items):
            if not isinstance(item, str) or not _ASCII_LETTER_RE.search(item):
                missing.append(f"{category}[{index}]={item!r}")

    if missing:
        raise ValueError(
            "English seasonal produce must include an English-readable name; "
            "Japanese-only entries: " + ", ".join(missing)
        )


def normalize_dish_name(name: str) -> str:
    """Normalize a dish name for duplicate detection.

    Strips parenthetical glosses, collapses whitespace, lowercases. Used so
    "Katsuo no tataki" and "Katsuo no tataki (seared bonito)" compare equal.
    """
    if not name:
        return ""
    stripped = re.sub(r"[（(][^）)]*[)）]", "", name)
    return " ".join(stripped.split()).strip().lower()


SYSTEM_PROMPT = """You are a poetic writer specializing in Japanese nature, culture, and the traditional \
calendar. Your prose is evocative, precise, and infused with wabi-sabi sensibility — finding beauty in \
impermanence and the subtle rhythms of the natural world. You have deep knowledge of traditional Japanese \
seasonal customs, food culture, natural phenomena, and the classical literature that celebrates them.

When writing about a micro-season (七十二候, shichijūni-kō), you ground each piece in concrete, sensory \
detail: the exact quality of morning light, the specific texture of a vegetable, the way a sound carries \
in certain weather. You avoid generic nature writing and instead find the particular.

You write fluently in two registers:
- English prose with a wabi-sabi sensibility — quiet, sensory, restrained.
- Japanese prose in the same register — natural, literary 日本語 that reads as if written for a Japanese \
reader, never as a translation. Use plain form (です・ます or である as appropriate to the passage), \
classical-leaning vocabulary where it fits the season, and the natural rhythm of Japanese sentence \
structure. Do not romanize, do not gloss in parentheses unless it is genuinely useful (e.g. produce \
names where the kanji is uncommon).

Always respond with valid JSON only — no markdown, no preamble, no explanation."""


def generate_content(season: dict, exclude_dishes: dict | None = None) -> dict:
    """Call the Claude API to generate rich bilingual content for a micro-season.

    Args:
        season: A season dict from seasons.json with keys:
                id, sekki, sekki_jp, ko_number, start_month, start_day,
                name_jp, name_romaji, name_en, major_season
        exclude_dishes: Optional dict ``{"en": iterable[str], "ja": iterable[str]}``
                of dish names already featured in other cached seasons. Claude is
                instructed to include at least two dishes that are NOT in these
                lists, so consecutive seasons don't keep surfacing the same dish.

    Returns:
        A dict of the shape ``{"en": {...flat fields...}, "ja": {...flat fields...}}``.
        Each language block has the same field names and shape.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    from datetime import date as _date
    def _fmt(m, d): return _date(2000, m, d).strftime("%-d %b")
    start_str = _fmt(season["start_month"], season["start_day"])
    end_str = _fmt(season["end_month"], season["end_day"]) if "end_month" in season else "unknown"
    duration = season.get("duration_days", 5)

    user_prompt = f"""Generate newsletter content for this Japanese micro-season (七十二候), \
in **both English and Japanese**. Each language must read as native prose, not as a translation of \
the other — share the same observations, imagery and cultural anchors, but let each language find its \
own rhythm.

Season #{season['id']} of 72
Major solar term: {season['sekki']} ({season['sekki_jp']})
Micro-season name: {season['name_jp']} ({season['name_romaji']})
English meaning: {season['name_en']}
Major season: {season['major_season']}
Dates: {start_str} – {end_str} ({duration} days)

Return a JSON object with exactly two top-level keys, "en" and "ja". Each key holds an object with \
exactly these fields:

{{
  "summary": "One sentence, plain language, what defines this micro-season — what you'd notice if you stepped outside",
  "opening": "A poetic 2-3 sentence description evoking the atmosphere of this specific 5-day \
micro-season. Ground it in the senses — what one sees, hears, smells, or feels outside in Japan right now.",
  "nature_notes": "2-3 sentences describing what is happening in nature during this exact period: \
which animals are behaving how, what plants are doing, what the sky and water look like.",
  "seasonal_produce": {{
    "fruits": ["3-4 fruits at their peak right now in Japan; EN block entries must include the common English name"],
    "vegetables": ["3-4 vegetables at their peak right now in Japan; EN block entries must include the common English name"],
    "fish": ["2-3 fish that are most prized or abundant right now; EN block entries must include the common English name"]
  }},
  "seasonal_dishes": [
    {{"name": "Japanese dish name", "description": "One sentence: what it is and why it belongs to this exact moment"}},
    {{"name": "Japanese dish name", "description": "One sentence: what it is and why it belongs to this exact moment"}}
    // 2 to 4 entries — see the variety constraint below
  ],
  "cultural_note": "2-3 sentences about a specific Japanese cultural practice, festival, craft \
tradition, or folk belief that is directly tied to this time of year.",
  "haiku": {{
    "japanese": "haiku in Japanese characters, 5-7-5 on (sound units)",
    "romaji": "romanized transliteration",
    "english": "English translation that preserves the season word (kigo) and the turn"
  }},
  "closing": "A single evocative closing sentence — not a summary, but an image or gesture that \
creates a sense of quiet transition into what comes next."
}}

Notes for the EN block:
- Every value in seasonal_produce.fruits, seasonal_produce.vegetables, and seasonal_produce.fish MUST contain a common English name written in Latin letters.
- A Japanese market name may be retained only when immediately glossed as `Japanese (common English name)`, for example `茗荷 (myoga ginger)` or `鱧 (pike conger)`.
- Never return a Japanese-only produce value in the EN block, including familiar katakana loanwords such as `ブルーベリー` or `マンゴー`.

Notes for the JA block:
- Produce names ("fruits", "vegetables", "fish") should be the natural Japanese forms used at \
markets and on menus — kanji where standard, hiragana/katakana where more common (e.g. 「いちご」, \
「タケノコ」, 「鯛」). Optionally include a brief gloss in parentheses only if a synonym is widely \
used (e.g. 「枇杷（びわ）」).
- Dish names should be the names a Japanese reader would expect (e.g. 「筍ごはん」, 「鰆の西京焼き」).
- The haiku block in JA may share the same Japanese characters as in EN (the haiku itself is \
Japanese-language poetry); romaji and english fields should remain identical across blocks. The other \
fields (summary/opening/nature_notes/cultural_note/closing) must be original Japanese prose."""

    en_excluded = sorted({normalize_dish_name(n): n for n in (exclude_dishes or {}).get("en", []) if n}.values())
    ja_excluded = sorted({normalize_dish_name(n): n for n in (exclude_dishes or {}).get("ja", []) if n}.values())
    if en_excluded or ja_excluded:
        en_list = ", ".join(en_excluded) if en_excluded else "(none)"
        ja_list = "、".join(ja_excluded) if ja_excluded else "（なし）"
        user_prompt += f"""

VARIETY CONSTRAINT — important:
The newsletter has already featured the following dishes in earlier micro-seasons \
this year, and readers will see them on the same page as the new entry. To keep \
the year feeling fresh, return between 2 and 4 entries in "seasonal_dishes" for each \
language block, and ensure that AT LEAST TWO entries per block are dishes whose names \
do NOT appear in the lists below (compare case-insensitively, ignoring any \
parenthetical glosses).

Already-featured English dish names: {en_list}
Already-featured Japanese dish names: {ja_list}

You MAY include up to one or two dishes from the lists above only if they are truly \
iconic and indispensable for this exact micro-season; otherwise pick fresh seasonally \
appropriate dishes. Never let an entire dishes block be made up of repeats."""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=3500,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = message.content[0].text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    payload = json.loads(text)

    if not isinstance(payload, dict) or "en" not in payload or "ja" not in payload:
        raise ValueError(
            "Expected bilingual payload with top-level 'en' and 'ja' keys; got: "
            f"{list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__}"
        )

    validate_english_produce(payload)

    return payload


def normalize_content(content: dict) -> dict:
    """Promote a legacy flat content dict to the bilingual shape.

    Cache entries written before bilingual support was added are flat (top-level
    fields like "summary", "opening", …). Wrap those as English-only so existing
    archive pages keep rendering until the JA backfill runs.
    """
    if isinstance(content, dict) and "en" in content and isinstance(content["en"], dict):
        return content
    return {"en": content}
