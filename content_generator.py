"""
Generate poetic newsletter content for a 72 micro-seasons entry using Claude.
"""

import json
import os

import anthropic


SYSTEM_PROMPT = """You are a poetic writer specializing in Japanese nature, culture, and the traditional \
calendar. Your prose is evocative, precise, and infused with wabi-sabi sensibility — finding beauty in \
impermanence and the subtle rhythms of the natural world. You have deep knowledge of traditional Japanese \
seasonal customs, food culture, natural phenomena, and the classical literature that celebrates them.

When writing about a micro-season (七十二候, shichijūni-kō), you ground each piece in concrete, sensory \
detail: the exact quality of morning light, the specific texture of a vegetable, the way a sound carries \
in certain weather. You avoid generic nature writing and instead find the particular.

Always respond with valid JSON only — no markdown, no preamble, no explanation."""


def generate_content(season: dict) -> dict:
    """Call the Claude API to generate rich content for a micro-season.

    Args:
        season: A season dict from seasons.json with keys:
                id, sekki, sekki_jp, ko_number, start_month, start_day,
                name_jp, name_romaji, name_en, major_season

    Returns:
        A dict with generated content fields.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    from datetime import date as _date
    def _fmt(m, d): return _date(2000, m, d).strftime("%-d %b")
    start_str = _fmt(season["start_month"], season["start_day"])
    end_str = _fmt(season["end_month"], season["end_day"]) if "end_month" in season else "unknown"
    duration = season.get("duration_days", 5)

    user_prompt = f"""Generate newsletter content for this Japanese micro-season (七十二候):

Season #{season['id']} of 72
Major solar term: {season['sekki']} ({season['sekki_jp']})
Micro-season name: {season['name_jp']} ({season['name_romaji']})
English meaning: {season['name_en']}
Major season: {season['major_season']}
Dates: {start_str} – {end_str} ({duration} days)

Return a JSON object with exactly these fields:

{{
  "summary": "One sentence, plain language, what defines this micro-season — what you'd notice if you stepped outside",
  "opening": "A poetic 2-3 sentence description evoking the atmosphere of this specific 5-day \
micro-season. Ground it in the senses — what one sees, hears, smells, or feels outside in Japan right now.",
  "nature_notes": "2-3 sentences describing what is happening in nature during this exact period: \
which animals are behaving how, what plants are doing, what the sky and water look like.",
  "seasonal_produce": {{
    "fruits": ["3-4 fruits at their peak right now in Japan"],
    "vegetables": ["3-4 vegetables at their peak right now in Japan"],
    "fish": ["2-3 fish that are most prized or abundant right now"]
  }},
  "seasonal_dishes": [
    {{"name": "Japanese dish name", "description": "One sentence: what it is and why it belongs to this exact moment"}},
    {{"name": "Japanese dish name", "description": "One sentence: what it is and why it belongs to this exact moment"}}
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
}}"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
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

    return json.loads(text)
