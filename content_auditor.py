"""Evidence-backed auditing for Kō newsletter content.

The auditor deliberately separates research from publication:

* ``data/fact_catalog.json`` stores human-reviewed facts and source metadata.
* ``data/content_audit.json`` records a review decision for the exact hash of a
  cached season.
* this module applies deterministic checks only. It never treats an LLM output
  as evidence or approves content automatically.

Examples:
    python content_auditor.py audit
    python content_auditor.py audit --season 41 --strict
    python content_auditor.py inventory --season 41
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).parent
DEFAULT_CACHE = ROOT / "data" / "content_cache.json"
DEFAULT_CATALOG = ROOT / "data" / "fact_catalog.json"
DEFAULT_MANIFEST = ROOT / "data" / "content_audit.json"
DEFAULT_SEASONS = ROOT / "data" / "seasons.json"

LANGUAGES = ("en", "ja")
PRODUCE_CATEGORIES = ("fruits", "vegetables", "fish")
FACTUAL_FIELDS = ("summary", "opening", "nature_notes", "cultural_note")
NON_FACTUAL_ALLOWED_FIELDS = {"summary", "opening"}
APPROVED_SOURCE_TIERS = {"government", "public_industry"}
FALLBACK_SOURCE_TIER = "culinary_reference"
FINAL_STATUSES = {"verified", "non_factual"}
_ADJACENT_MIXED_SCRIPT_RE = re.compile(
    r"(?:[A-Za-z][\u3040-\u30ff\u3400-\u9fff]|[\u3040-\u30ff\u3400-\u9fff][A-Za-z])"
)


@dataclass(frozen=True)
class Claim:
    path: str
    kind: str
    text: str
    category: str | None = None


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    season_id: str
    path: str
    message: str


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Required audit file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def language_blocks(content: dict) -> Iterable[tuple[str, dict]]:
    """Yield language blocks while supporting the legacy English-only shape."""
    if isinstance(content.get("en"), dict):
        for language in LANGUAGES:
            block = content.get(language)
            if isinstance(block, dict):
                yield language, block
        return
    yield "en", content


def iter_claims(content: dict) -> Iterable[Claim]:
    """Yield every field that requires an editorial evidence decision."""
    for language, block in language_blocks(content):
        for field in FACTUAL_FIELDS:
            value = block.get(field)
            if isinstance(value, str) and value.strip():
                yield Claim(f"{language}.{field}", "prose", value.strip())

        closing = block.get("closing")
        if isinstance(closing, str) and closing.strip():
            yield Claim(f"{language}.closing", "poetic", closing.strip())

        produce = block.get("seasonal_produce")
        if isinstance(produce, dict):
            for category in PRODUCE_CATEGORIES:
                items = produce.get(category)
                if not isinstance(items, list):
                    continue
                for index, item in enumerate(items):
                    if isinstance(item, str) and item.strip():
                        yield Claim(
                            f"{language}.seasonal_produce.{category}[{index}]",
                            "ingredient",
                            item.strip(),
                            category=category,
                        )

        dishes = block.get("seasonal_dishes")
        if isinstance(dishes, list):
            for index, dish in enumerate(dishes):
                if not isinstance(dish, dict):
                    continue
                name = dish.get("name")
                description = dish.get("description")
                if isinstance(name, str) and name.strip():
                    yield Claim(
                        f"{language}.seasonal_dishes[{index}].name",
                        "dish",
                        name.strip(),
                    )
                if isinstance(description, str) and description.strip():
                    yield Claim(
                        f"{language}.seasonal_dishes[{index}].description",
                        "dish_description",
                        description.strip(),
                    )


def canonical_content(content: dict) -> dict:
    """Remove operational metadata before hashing an editorial payload."""
    canonical = copy.deepcopy(content)
    canonical.pop("_sent_on", None)
    canonical.pop("_audit", None)
    return canonical


def content_hash(content: dict) -> str:
    encoded = json.dumps(
        canonical_content(content),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _month_day(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d{2})-(\d{2})", value)
    if not match:
        raise ValueError(f"Expected MM-DD date, got {value!r}")
    month, day = map(int, match.groups())
    date(2000, month, day)
    return month, day


def _date_in_window(month: int, day: int, start: str, end: str) -> bool:
    point = (month, day)
    start_point = _month_day(start)
    end_point = _month_day(end)
    if start_point <= end_point:
        return start_point <= point <= end_point
    return point >= start_point or point <= end_point


def _fact_applies(fact: dict, season: dict, region_context: str | None) -> bool:
    windows = fact.get("season_windows")
    if not isinstance(windows, list) or not windows:
        return False

    start_month = int(season["start_month"])
    start_day = int(season["start_day"])
    for window in windows:
        if not isinstance(window, dict):
            continue
        try:
            date_matches = _date_in_window(
                start_month,
                start_day,
                str(window["start"]),
                str(window["end"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not date_matches:
            continue
        regions = window.get("regions", ["national"])
        if "national" in regions:
            return True
        if region_context and region_context in regions:
            return True
    return False


def _fact_regions_for_date(fact: dict, season: dict) -> set[str]:
    regions: set[str] = set()
    for window in fact.get("season_windows", []):
        if not isinstance(window, dict):
            continue
        try:
            matches = _date_in_window(
                int(season["start_month"]),
                int(season["start_day"]),
                str(window["start"]),
                str(window["end"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if matches:
            regions.update(window.get("regions", ["national"]))
    return regions


def _source_policy(fact: dict, sources: dict) -> tuple[bool, str]:
    source_ids = fact.get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        return False, "fact has no sources"

    resolved = [sources.get(source_id) for source_id in source_ids]
    if any(not isinstance(source, dict) for source in resolved):
        return False, "fact references a missing source"
    for source in resolved:
        required = ("title", "publisher", "url", "tier", "accessed_at")
        missing = [field for field in required if not source.get(field)]
        if missing:
            return False, f"source metadata is missing {', '.join(missing)}"
        if not str(source["url"]).startswith(("https://", "http://")):
            return False, "source URL must be HTTP(S)"
        try:
            date.fromisoformat(str(source["accessed_at"]))
        except ValueError:
            return False, "source accessed_at must be an ISO date"

    if any(source.get("tier") in APPROVED_SOURCE_TIERS for source in resolved):
        return True, ""

    fallback_publishers = {
        source.get("publisher")
        for source in resolved
        if source.get("tier") == FALLBACK_SOURCE_TIER and source.get("publisher")
    }
    if len(fallback_publishers) >= 2:
        return True, ""
    return False, "fact needs one official/public-industry source or two independent culinary references"


def _season_map(seasons_payload: dict) -> dict[str, dict]:
    seasons = seasons_payload.get("seasons")
    if not isinstance(seasons, list):
        raise ValueError("seasons.json must contain a 'seasons' list")
    return {str(season["id"]): season for season in seasons}


def _catalog_maps(catalog: dict) -> tuple[dict, dict]:
    sources = catalog.get("sources", {})
    facts = catalog.get("facts", {})
    if not isinstance(sources, dict) or not isinstance(facts, dict):
        raise ValueError("fact catalog must contain object-valued 'sources' and 'facts'")
    return sources, facts


def audit_season(
    season_id: str,
    content: dict,
    season: dict,
    catalog: dict,
    manifest_entry: dict | None,
) -> list[Finding]:
    findings: list[Finding] = []
    sources, facts = _catalog_maps(catalog)
    claims = list(iter_claims(content))

    if not isinstance(manifest_entry, dict):
        findings.append(
            Finding(
                "hard",
                "missing-season-review",
                season_id,
                "",
                "No audit manifest entry exists for this cached season.",
            )
        )
        manifest_entry = {}

    expected_hash = content_hash(content)
    if manifest_entry.get("content_hash") != expected_hash:
        findings.append(
            Finding(
                "hard",
                "content-hash-mismatch",
                season_id,
                "",
                "The approved content hash does not match the current cached content.",
            )
        )

    if manifest_entry.get("status") != "verified":
        findings.append(
            Finding(
                "hard",
                "season-not-approved",
                season_id,
                "",
                f"Season review status is {manifest_entry.get('status', 'missing')!r}, not 'verified'.",
            )
        )

    decisions = manifest_entry.get("claims")
    if not isinstance(decisions, dict):
        decisions = {}

    expected_paths = {claim.path for claim in claims}
    stale_paths = sorted(set(decisions) - expected_paths)
    for path in stale_paths:
        findings.append(
            Finding(
                "warning",
                "stale-claim-review",
                season_id,
                path,
                "Manifest decision no longer maps to a factual content field.",
            )
        )

    for claim in claims:
        if claim.path.startswith("en.") and _ADJACENT_MIXED_SCRIPT_RE.search(claim.text):
            findings.append(
                Finding(
                    "hard",
                    "malformed-mixed-script",
                    season_id,
                    claim.path,
                    "English content contains adjacent Latin and Japanese text without a separator.",
                )
            )

        decision = decisions.get(claim.path)
        if not isinstance(decision, dict):
            findings.append(
                Finding(
                    "hard",
                    "missing-claim-review",
                    season_id,
                    claim.path,
                    f"No evidence decision exists for: {claim.text}",
                )
            )
            continue

        status = decision.get("status")
        if status not in FINAL_STATUSES:
            findings.append(
                Finding(
                    "hard",
                    "claim-not-approved",
                    season_id,
                    claim.path,
                    f"Claim status is {status!r}; expected 'verified' or a valid 'non_factual' decision.",
                )
            )
            continue

        if status == "non_factual":
            field = claim.path.split(".", 1)[1].split("[", 1)[0]
            if claim.kind != "poetic" and field not in NON_FACTUAL_ALLOWED_FIELDS:
                findings.append(
                    Finding(
                        "hard",
                        "invalid-non-factual-classification",
                        season_id,
                        claim.path,
                        "This field type cannot be exempted as purely poetic.",
                    )
                )
            if not decision.get("reviewer") or not decision.get("reviewed_at"):
                findings.append(
                    Finding(
                        "hard",
                        "incomplete-review-attribution",
                        season_id,
                        claim.path,
                        "A non-factual decision requires reviewer and reviewed_at.",
                    )
                )
            continue

        fact_ids = decision.get("fact_ids")
        if not isinstance(fact_ids, list) or not fact_ids:
            findings.append(
                Finding(
                    "hard",
                    "missing-fact-reference",
                    season_id,
                    claim.path,
                    "Verified claim has no fact references.",
                )
            )
            continue

        if not decision.get("reviewer") or not decision.get("reviewed_at"):
            findings.append(
                Finding(
                    "hard",
                    "incomplete-review-attribution",
                    season_id,
                    claim.path,
                    "Verified claim requires reviewer and reviewed_at.",
                )
            )

        region_context = decision.get("region_context")
        for fact_id in fact_ids:
            fact = facts.get(fact_id)
            if not isinstance(fact, dict):
                findings.append(
                    Finding(
                        "hard",
                        "missing-fact",
                        season_id,
                        claim.path,
                        f"Unknown fact ID: {fact_id}",
                    )
                )
                continue
            if fact.get("status") != "verified":
                findings.append(
                    Finding(
                        "hard",
                        "unverified-fact",
                        season_id,
                        claim.path,
                        f"Fact {fact_id} is not verified.",
                    )
                )
            missing_fact_fields = [
                field
                for field in ("kind", "claim", "names", "season_windows", "source_ids")
                if not fact.get(field)
            ]
            if missing_fact_fields:
                findings.append(
                    Finding(
                        "hard",
                        "incomplete-fact",
                        season_id,
                        claim.path,
                        f"Fact {fact_id} is missing {', '.join(missing_fact_fields)}.",
                    )
                )
            expected_kinds = {
                "ingredient": {"ingredient"},
                "dish": {"dish"},
                "dish_description": {"dish", "dish_description"},
                "prose": {"prose", "nature", "culture", "calendar", "ingredient", "dish"},
                "poetic": {
                    "poetic",
                    "prose",
                    "nature",
                    "culture",
                    "calendar",
                    "ingredient",
                    "dish",
                },
            }[claim.kind]
            if fact.get("kind") not in expected_kinds:
                findings.append(
                    Finding(
                        "hard",
                        "fact-kind-mismatch",
                        season_id,
                        claim.path,
                        f"Fact {fact_id} has kind {fact.get('kind')!r}; expected one of {sorted(expected_kinds)}.",
                    )
                )
            if claim.kind == "ingredient" and fact.get("category"):
                expected_category = {
                    "fruits": "fruit",
                    "vegetables": "vegetable",
                    "fish": "fish",
                }.get(claim.category, claim.category)
                if fact.get("category") != expected_category:
                    findings.append(
                        Finding(
                            "hard",
                            "ingredient-category-mismatch",
                            season_id,
                            claim.path,
                            f"Fact {fact_id} is categorized as {fact.get('category')!r}, "
                            f"not {expected_category!r}.",
                        )
                    )
            source_ok, source_message = _source_policy(fact, sources)
            if not source_ok:
                findings.append(
                    Finding(
                        "hard",
                        "insufficient-evidence",
                        season_id,
                        claim.path,
                        f"Fact {fact_id}: {source_message}.",
                    )
                )
            if not _fact_applies(fact, season, region_context):
                findings.append(
                    Finding(
                        "hard",
                        "fact-outside-season-or-region",
                        season_id,
                        claim.path,
                        f"Fact {fact_id} does not support this micro-season and region context.",
                    )
                )

    # Equivalent EN/JA fields should point to at least one shared canonical
    # fact. This catches translations that silently swap an ingredient, dish,
    # natural event, or custom.
    if isinstance(content.get("en"), dict) and isinstance(content.get("ja"), dict):
        paired: dict[str, dict[str, set[str]]] = {}
        for path, decision in decisions.items():
            if not isinstance(decision, dict) or decision.get("status") != "verified":
                continue
            language, separator, relative = path.partition(".")
            if not separator or language not in LANGUAGES:
                continue
            fact_ids = decision.get("fact_ids")
            if isinstance(fact_ids, list):
                paired.setdefault(relative, {})[language] = set(fact_ids)
        for relative, languages in paired.items():
            if set(languages) == set(LANGUAGES) and not (
                languages["en"] & languages["ja"]
            ):
                findings.append(
                    Finding(
                        "hard",
                        "bilingual-fact-mismatch",
                        season_id,
                        relative,
                        "English and Japanese versions do not share a canonical supporting fact.",
                    )
                )

    return findings


def audit_cache(
    cache: dict,
    catalog: dict,
    manifest: dict,
    seasons_payload: dict,
    season_ids: set[str] | None = None,
) -> tuple[list[Finding], dict[str, dict]]:
    seasons = _season_map(seasons_payload)
    manifest_seasons = manifest.get("seasons", {})
    if not isinstance(manifest_seasons, dict):
        raise ValueError("audit manifest must contain an object-valued 'seasons' field")

    findings: list[Finding] = []
    inventory: dict[str, dict] = {}
    processed: set[str] = set()
    for season_id, content in sorted(cache.items(), key=lambda item: int(item[0])):
        if season_ids is not None and season_id not in season_ids:
            continue
        processed.add(season_id)
        if not isinstance(content, dict):
            findings.append(
                Finding("hard", "invalid-content", season_id, "", "Cached content must be an object.")
            )
            continue
        season = seasons.get(season_id)
        if not season:
            findings.append(
                Finding("hard", "unknown-season", season_id, "", "Season is absent from seasons.json.")
            )
            continue

        claims = list(iter_claims(content))
        inventory[season_id] = {
            "content_hash": content_hash(content),
            "status": "needs_review",
            "claims": {
                claim.path: {
                    "status": "needs_review",
                    "fact_ids": [],
                    "text": claim.text,
                }
                for claim in claims
            },
        }
        findings.extend(
            audit_season(
                season_id,
                content,
                season,
                catalog,
                manifest_seasons.get(season_id),
            )
        )
    if season_ids is not None:
        for missing_id in sorted(season_ids - processed, key=int):
            findings.append(
                Finding(
                    "hard",
                    "missing-cache-entry",
                    missing_id,
                    "",
                    "The selected season has no cached candidate. Prepare it before review.",
                )
            )
    return findings, inventory


def verified_fact_pack(catalog: dict, season: dict) -> list[dict]:
    """Return facts approved for generation during a specific micro-season."""
    sources, facts = _catalog_maps(catalog)
    pack: list[dict] = []
    for fact_id, fact in facts.items():
        if fact.get("status") != "verified":
            continue
        source_ok, _ = _source_policy(fact, sources)
        regions = _fact_regions_for_date(fact, season)
        if not source_ok or not regions:
            continue
        pack.append(
            {
                "id": fact_id,
                "kind": fact.get("kind"),
                "claim": fact.get("claim"),
                "names": fact.get("names", {}),
                "regions": sorted(regions),
            }
        )
    return sorted(pack, key=lambda item: item["id"])


def assert_season_approved(
    season_id: str,
    content: dict,
    *,
    catalog_path: Path = DEFAULT_CATALOG,
    manifest_path: Path = DEFAULT_MANIFEST,
    seasons_path: Path = DEFAULT_SEASONS,
) -> None:
    catalog = load_json(catalog_path)
    manifest = load_json(manifest_path)
    seasons = _season_map(load_json(seasons_path))
    season = seasons.get(str(season_id))
    if not season:
        raise ValueError(f"Unknown season: {season_id}")
    manifest_entry = manifest.get("seasons", {}).get(str(season_id))
    findings = audit_season(str(season_id), content, season, catalog, manifest_entry)
    hard = [finding for finding in findings if finding.severity == "hard"]
    if hard:
        details = "\n".join(
            f"- {finding.path or '(season)'} [{finding.code}]: {finding.message}"
            for finding in hard
        )
        raise RuntimeError(
            f"Season #{season_id} is not approved for publication:\n{details}\n"
            f"Run: python content_auditor.py inventory --season {season_id}"
        )


def _render_text(findings: list[Finding], inventory: dict[str, dict]) -> str:
    hard_count = sum(finding.severity == "hard" for finding in findings)
    warning_count = sum(finding.severity == "warning" for finding in findings)
    lines = [
        f"Audited {len(inventory)} season(s): {hard_count} hard failure(s), "
        f"{warning_count} warning(s)."
    ]
    for finding in findings:
        location = f"season {finding.season_id}"
        if finding.path:
            location += f" · {finding.path}"
        lines.append(f"{finding.severity.upper():7} {location} [{finding.code}] {finding.message}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Kō content against reviewed evidence")
    parser.add_argument("command", choices=("audit", "inventory"))
    parser.add_argument("--season", action="append", help="Season ID; may be repeated")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--seasons", type=Path, default=DEFAULT_SEASONS)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when hard failures exist")
    args = parser.parse_args()

    try:
        cache = load_json(args.cache)
        catalog = load_json(args.catalog)
        manifest = load_json(args.manifest)
        seasons = load_json(args.seasons)
        selected = set(args.season) if args.season else None
        findings, inventory = audit_cache(cache, catalog, manifest, seasons, selected)
    except ValueError as exc:
        print(f"Audit configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.command == "inventory":
        output = {
            "schema_version": 1,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "seasons": inventory,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    elif args.format == "json":
        print(json.dumps([asdict(finding) for finding in findings], ensure_ascii=False, indent=2))
    else:
        print(_render_text(findings, inventory))

    if args.strict and any(finding.severity == "hard" for finding in findings):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
