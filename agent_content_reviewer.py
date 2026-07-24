"""Independent, source-grounded agent review for Kō content.

Two research passes and a separate adversarial verifier use Anthropic's
server-side web search. Only unanimous >=90% decisions are written to the
manifest; the deterministic content auditor remains the publication gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import anthropic
from dotenv import load_dotenv

from content_auditor import (
    DEFAULT_CACHE,
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    DEFAULT_SEASONS,
    MIN_AGENT_CONFIDENCE,
    content_hash,
    iter_claims,
    load_json,
)

load_dotenv()

MODEL = os.environ.get("CONTENT_REVIEW_MODEL", "claude-opus-4-5")
MAX_OUTPUT_TOKENS = int(os.environ.get("CONTENT_REVIEW_MAX_TOKENS", "24000"))
MAX_REPAIR_ATTEMPTS = int(os.environ.get("CONTENT_REVIEW_REPAIR_ATTEMPTS", "1"))
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 20,
}

REVIEW_SYSTEM = """You are an exacting Japanese seasonal-culture fact checker.
Search Japanese primary and authoritative sources. Prefer national/prefectural
government, public market/agriculture/fisheries bodies, museums, universities,
and official festival organizations. Never use another AI answer as evidence.
Distinguish peak season from mere year-round availability and national claims
from regional ones. Return JSON only."""

CLAIM_STATUS = ["verified", "rejected", "non_factual", "needs_review"]


def _strict_object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


RESEARCH_CLAIM_SCHEMA = _strict_object(
    {
        "path": {"type": "string"},
        "status": {"type": "string", "enum": CLAIM_STATUS},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "region_context": {"type": ["string", "null"]},
        "source_urls": {"type": "array", "items": {"type": "string"}},
    }
)
SOURCE_SCHEMA = _strict_object(
    {
        "title": {"type": "string"},
        "publisher": {"type": "string"},
        "url": {"type": "string"},
        "tier": {
            "type": "string",
            "enum": ["government", "public_industry", "culinary_reference"],
        },
    }
)
SEASON_WINDOW_SCHEMA = _strict_object(
    {
        "start": {"type": "string"},
        "end": {"type": "string"},
        "regions": {"type": "array", "items": {"type": "string"}},
    }
)
FACT_SCHEMA = _strict_object(
    {
        "fact_id": {"type": "string"},
        "kind": {
            "type": "string",
            "enum": [
                "ingredient",
                "dish",
                "dish_description",
                "nature",
                "culture",
                "calendar",
                "prose",
                "poetic",
            ],
        },
        "category": {"enum": [None, "fruit", "vegetable", "fish"]},
        "claim": {"type": "string"},
        "names": _strict_object(
            {
                "en": {"type": "array", "items": {"type": "string"}},
                "ja": {"type": "array", "items": {"type": "string"}},
            }
        ),
        "season_windows": {"type": "array", "items": SEASON_WINDOW_SCHEMA},
        "sources": {"type": "array", "items": SOURCE_SCHEMA},
    }
)
VERIFIER_CLAIM_SCHEMA = _strict_object(
    {
        "path": {"type": "string"},
        "status": {"type": "string", "enum": CLAIM_STATUS},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "region_context": {"type": ["string", "null"]},
        "facts": {"type": "array", "items": FACT_SCHEMA},
    }
)
RESEARCH_OUTPUT_SCHEMA = _strict_object(
    {"claims": {"type": "array", "items": RESEARCH_CLAIM_SCHEMA}}
)
VERIFIER_OUTPUT_SCHEMA = _strict_object(
    {"claims": {"type": "array", "items": VERIFIER_CLAIM_SCHEMA}}
)
REPAIR_OUTPUT_SCHEMA = _strict_object(
    {
        "replacements": {
            "type": "array",
            "items": _strict_object(
                {
                    "path": {"type": "string"},
                    "value": {"type": "string"},
                }
            ),
        }
    }
)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Reviewer did not return a JSON object")
    return json.loads(text[start : end + 1])


def _message_text(message) -> str:
    return "\n".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )


def _claims_by_path(result: dict) -> dict[str, dict]:
    claims = result.get("claims")
    if not isinstance(claims, list):
        raise ValueError("Reviewer response must contain a claims array")
    indexed: dict[str, dict] = {}
    for claim in claims:
        path = claim.get("path") if isinstance(claim, dict) else None
        if not isinstance(path, str) or not path:
            raise ValueError("Every reviewer claim must have a non-empty path")
        if path in indexed:
            raise ValueError(f"Reviewer returned duplicate claim path: {path}")
        indexed[path] = claim
    return indexed


def _stream_message(client: anthropic.Anthropic, messages: list, output_schema: dict):
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=REVIEW_SYSTEM,
        messages=messages,
        tools=[WEB_SEARCH_TOOL],
        output_config={
            "format": {"type": "json_schema", "schema": output_schema}
        },
    ) as stream:
        return stream.get_final_message()


def _call_with_search(
    client: anthropic.Anthropic, prompt: str, output_schema: dict
) -> dict:
    messages = [{"role": "user", "content": prompt}]
    response = _stream_message(client, messages, output_schema)
    # Server tools can pause a long-running turn. Continue with the exact
    # assistant content so search state and citations are preserved.
    for _ in range(3):
        if response.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": response.content})
        response = _stream_message(client, messages, output_schema)
    if response.stop_reason != "end_turn":
        raise RuntimeError(
            "Reviewer did not complete a schema-valid response "
            f"(stop_reason={response.stop_reason!r})"
        )
    return _extract_json(_message_text(response))


def _review_prompt(season: dict, claims: list[dict], label: str) -> str:
    return f"""Independent review run {label}.

Season: {json.dumps(season, ensure_ascii=False)}
Claims: {json.dumps(claims, ensure_ascii=False)}

For every claim path, search for direct evidence and return:
{{
  "claims": [{{
      "path": "<path>",
      "status": "verified" | "rejected" | "non_factual" | "needs_review",
      "confidence": 0.0-1.0,
      "reason": "concise evidence analysis",
      "region_context": null | "region identifier",
      "source_urls": ["direct URLs actually consulted"]
  }}]
}}

Use non_factual only for genuinely poetic summary/opening/closing text with no
concrete assertion. Reject a seasonal claim when evidence only proves general
availability. A claim cannot be verified without direct source URLs."""


def _verifier_prompt(
    season: dict,
    claims: list[dict],
    research_a: dict,
    research_b: dict,
) -> str:
    return f"""Act as an adversarial verifier. Independently search the web and
try to falsify both research reports. Approve only claims supported for the
exact date and stated national/ regional scope.

Season: {json.dumps(season, ensure_ascii=False)}
Claims: {json.dumps(claims, ensure_ascii=False)}
Research A: {json.dumps(research_a, ensure_ascii=False)}
Research B: {json.dumps(research_b, ensure_ascii=False)}

Return JSON:
{{
  "claims": [{{
      "path": "<path>",
      "status": "verified" | "rejected" | "non_factual" | "needs_review",
      "confidence": 0.0-1.0,
      "reason": "why the evidence survives adversarial review",
      "region_context": null | "region identifier",
      "facts": [{{
        "fact_id": "stable-kebab-case-id",
        "kind": "ingredient|dish|dish_description|nature|culture|calendar|prose|poetic",
        "category": null | "fruit|vegetable|fish",
        "claim": "minimal supported assertion",
        "names": {{"en": [], "ja": []}},
        "season_windows": [{{"start": "MM-DD", "end": "MM-DD", "regions": ["national"]}}],
        "sources": [{{
          "title": "source title",
          "publisher": "publisher",
          "url": "direct URL",
          "tier": "government|public_industry|culinary_reference"
        }}]
      }}]
  }}]
}}

For verified claims, facts and sources are mandatory. Use culinary_reference
only when two independent publishers support the same fact. Equivalent EN/JA
paths must reuse the same stable fact IDs."""


def _repair_prompt(season: dict, content: dict, failed_claims: list[dict]) -> str:
    return f"""Act as a corrective Japanese seasonal-content editor. Search
authoritative Japanese sources and replace every failed claim with a concise,
directly supportable alternative for this exact date and region. Preserve each
path and its language. For paired EN/JA items, keep the underlying ingredient,
dish, or fact equivalent. Avoid claims that merely describe year-round
availability. Poetic fields may be rewritten to remove unsupported factual
assertions.

Season: {json.dumps(season, ensure_ascii=False)}
Current content: {json.dumps(content, ensure_ascii=False)}
Failed claims: {json.dumps(failed_claims, ensure_ascii=False)}

Return exactly one non-empty string replacement for every failed path:
{{"replacements": [{{"path": "<failed path>", "value": "<corrected text>"}}]}}

Do not add paths and do not omit failed paths. These replacements will undergo
a completely fresh two-researcher plus adversarial-verifier quorum."""


def _set_claim_text(content: dict, path: str, value: str) -> None:
    tokens = re.findall(r"[^.\[\]]+", path)
    normalized = [int(token) if token.isdigit() else token for token in tokens]
    target = content
    for token in normalized[:-1]:
        target = target[token]
    final = normalized[-1]
    if not isinstance(target[final], str):
        raise ValueError(f"Repair path does not resolve to text: {path}")
    target[final] = value


def _repair_candidate(
    client: anthropic.Anthropic,
    season: dict,
    content: dict,
    failed_claims: list[dict],
) -> int:
    expected = {item["path"] for item in failed_claims}
    response = _call_with_search(
        client,
        _repair_prompt(season, content, failed_claims),
        REPAIR_OUTPUT_SCHEMA,
    )
    replacements = response.get("replacements")
    if not isinstance(replacements, list):
        raise ValueError("Correction agent did not return replacements")
    indexed: dict[str, str] = {}
    for item in replacements:
        path = item.get("path") if isinstance(item, dict) else None
        value = item.get("value") if isinstance(item, dict) else None
        if path in indexed:
            raise ValueError(f"Correction agent duplicated path: {path}")
        if path not in expected:
            raise ValueError(f"Correction agent returned an unexpected path: {path}")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Correction agent returned empty text for: {path}")
        indexed[path] = value.strip()
    missing = expected - set(indexed)
    if missing:
        raise ValueError(
            "Correction agent omitted paths: " + ", ".join(sorted(missing))
        )
    for path, value in indexed.items():
        _set_claim_text(content, path, value)
    return len(indexed)


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _source_id(url: str) -> str:
    return "source:" + hashlib.sha256(url.encode()).hexdigest()[:16]


def _review_record(role: str, result: dict, path: str, run_id: str) -> dict:
    claim = result.get(path, {})
    return {
        "run_id": run_id,
        "role": role,
        "model": MODEL,
        "verdict": claim.get("status", "needs_review"),
        "confidence": claim.get("confidence", 0),
        "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def review_season(
    season_id: str,
    cache: dict,
    seasons: dict,
    catalog: dict,
    manifest: dict,
) -> dict:
    content = cache.get(season_id)
    if not isinstance(content, dict):
        raise ValueError(f"Season {season_id} has no cached candidate")
    season = next((item for item in seasons["seasons"] if str(item["id"]) == season_id), None)
    if not season:
        raise ValueError(f"Unknown season {season_id}")

    claim_rows = [
        {"path": claim.path, "kind": claim.kind, "category": claim.category, "text": claim.text}
        for claim in iter_claims(content)
    ]
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    run_a, run_b, run_v = (str(uuid4()) for _ in range(3))
    research_a = _claims_by_path(
        _call_with_search(
            client, _review_prompt(season, claim_rows, "A"), RESEARCH_OUTPUT_SCHEMA
        )
    )
    research_b = _claims_by_path(
        _call_with_search(
            client, _review_prompt(season, claim_rows, "B"), RESEARCH_OUTPUT_SCHEMA
        )
    )
    verifier = _claims_by_path(
        _call_with_search(
            client,
            _verifier_prompt(season, claim_rows, research_a, research_b),
            VERIFIER_OUTPUT_SCHEMA,
        )
    )

    decisions: dict[str, dict] = {}
    failed_claims: list[dict] = []
    all_approved = True
    for claim in claim_rows:
        path = claim["path"]
        reviews = [
            _review_record("researcher", research_a, path, run_a),
            _review_record("researcher", research_b, path, run_b),
            _review_record("verifier", verifier, path, run_v),
        ]
        statuses = {review["verdict"] for review in reviews}
        confidence_ok = all(
            isinstance(review["confidence"], (int, float))
            and MIN_AGENT_CONFIDENCE <= review["confidence"] <= 1
            for review in reviews
        )
        final_status = statuses.pop() if len(statuses) == 1 else "needs_review"
        if final_status not in {"verified", "non_factual"} or not confidence_ok:
            final_status = "needs_review"
            all_approved = False

        verifier_claim = verifier.get(path, {})
        fact_ids: list[str] = []
        if final_status == "verified":
            for fact in verifier_claim.get("facts", []):
                fact_id = "fact:" + _safe_id(str(fact.get("fact_id") or path))
                source_ids: list[str] = []
                for source in fact.pop("sources", []):
                    url = str(source.get("url", ""))
                    if not url.startswith(("https://", "http://")):
                        continue
                    source_id = _source_id(url)
                    source["accessed_at"] = datetime.now().date().isoformat()
                    catalog.setdefault("sources", {})[source_id] = source
                    source_ids.append(source_id)
                fact.update(
                    {
                        "status": "verified",
                        "source_ids": source_ids,
                    }
                )
                catalog.setdefault("facts", {})[fact_id] = fact
                fact_ids.append(fact_id)
            if not fact_ids:
                final_status = "needs_review"
                all_approved = False

        decisions[path] = {
            "status": final_status,
            "fact_ids": fact_ids,
            "region_context": verifier_claim.get("region_context"),
            "review_method": "agent_quorum_v1",
            "agent_reviews": reviews,
            "reason": verifier_claim.get("reason"),
        }
        if final_status == "needs_review":
            failed_claims.append(
                {
                    "path": path,
                    "text": claim["text"],
                    "reason": verifier_claim.get("reason"),
                    "agent_verdicts": [
                        {
                            "role": review["role"],
                            "verdict": review["verdict"],
                            "confidence": review["confidence"],
                        }
                        for review in reviews
                    ],
                }
            )

    # A correction to one language must also refresh the equivalent field in
    # the other language so the next verifier sees the same underlying fact.
    claim_by_path = {claim["path"]: claim for claim in claim_rows}
    failed_by_path = {claim["path"]: claim for claim in failed_claims}
    for failed in list(failed_claims):
        language, separator, relative = failed["path"].partition(".")
        if not separator or language not in {"en", "ja"}:
            continue
        paired_path = f"{'ja' if language == 'en' else 'en'}.{relative}"
        paired = claim_by_path.get(paired_path)
        if paired and paired_path not in failed_by_path:
            paired_failure = {
                "path": paired_path,
                "text": paired["text"],
                "reason": "paired bilingual correction",
                "agent_verdicts": [],
            }
            failed_claims.append(paired_failure)
            failed_by_path[paired_path] = paired_failure

    manifest.setdefault("seasons", {})[season_id] = {
        "status": "verified" if all_approved else "needs_review",
        "content_hash": content_hash(content),
        "review_method": "agent_quorum_v1",
        "claims": decisions,
    }
    return {
        "approved": all_approved,
        "claim_count": len(claim_rows),
        "failed_claims": failed_claims,
    }


def _save_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def review_and_save_season(season_id: str) -> dict:
    cache = load_json(DEFAULT_CACHE)
    seasons = load_json(DEFAULT_SEASONS)
    catalog = load_json(DEFAULT_CATALOG)
    manifest = load_json(DEFAULT_MANIFEST)
    result = review_season(season_id, cache, seasons, catalog, manifest)
    season = next(
        item for item in seasons["seasons"] if str(item["id"]) == season_id
    )
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    for _ in range(MAX_REPAIR_ATTEMPTS):
        if result["approved"]:
            break
        corrected = _repair_candidate(
            client, season, cache[season_id], result["failed_claims"]
        )
        if not corrected:
            break
        result = review_season(season_id, cache, seasons, catalog, manifest)
    _save_json(DEFAULT_CACHE, cache)
    _save_json(DEFAULT_CATALOG, catalog)
    _save_json(DEFAULT_MANIFEST, manifest)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run independent agent content review")
    parser.add_argument("--season", action="append", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        cache = load_json(DEFAULT_CACHE)
        seasons = load_json(DEFAULT_SEASONS)
        catalog = load_json(DEFAULT_CATALOG)
        manifest = load_json(DEFAULT_MANIFEST)
        results = {
            season_id: review_season(season_id, cache, seasons, catalog, manifest)
            for season_id in args.season
        }
    else:
        results = {
            season_id: review_and_save_season(season_id)
            for season_id in args.season
        }
    print(json.dumps(results, indent=2))
    if not all(result["approved"] for result in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
