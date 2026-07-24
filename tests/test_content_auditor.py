import copy
import unittest

from content_auditor import audit_season, content_hash, iter_claims
from content_generator import validate_generated_fact_refs


SEASON = {
    "id": 40,
    "start_month": 7,
    "start_day": 23,
}

CONTENT = {
    "en": {
        "summary": "Cucumbers are abundant in midsummer.",
        "opening": "Heat shimmers above the garden.",
        "nature_notes": "Cicadas call in the afternoon.",
        "seasonal_produce": {
            "fruits": ["Watermelon"],
            "vegetables": ["Cucumber"],
            "fish": ["Horse mackerel"],
        },
        "seasonal_dishes": [
            {
                "name": "Kyūri no sunomono",
                "description": "Cucumber dressed with rice vinegar.",
            }
        ],
        "cultural_note": "Summer kitchens favor lightly dressed vegetables.",
        "closing": "A drop of water rests on the knife.",
        "haiku": {"japanese": "test", "romaji": "test", "english": "test"},
    }
}


def catalog(
    content=CONTENT,
    *,
    tier="government",
    regions=None,
    start="07-01",
    end="08-31",
):
    regions = regions or ["national"]
    facts = {}
    for claim in iter_claims(content):
        fact_id = f"fact:{claim.path}"
        facts[fact_id] = {
            "status": "verified",
            "kind": claim.kind,
            "category": {
                "fruits": "fruit",
                "vegetables": "vegetable",
                "fish": "fish",
            }.get(claim.category),
            "claim": claim.text,
            "names": {"en": claim.text},
            "season_windows": [{"start": start, "end": end, "regions": regions}],
            "source_ids": ["source:one"],
        }
    return {
        "sources": {
            "source:one": {
                "title": "Source one",
                "tier": tier,
                "publisher": "Publisher one",
                "url": "https://example.test/one",
                "accessed_at": "2026-07-23",
            }
        },
        "facts": facts,
    }


def manifest(content=CONTENT, *, region_context=None):
    claims = {}
    for claim in iter_claims(content):
        decision = {
            "status": "verified",
            "fact_ids": [f"fact:{claim.path}"],
            "reviewer": "Human reviewer",
            "reviewed_at": "2026-07-23T12:00:00-04:00",
        }
        if region_context:
            decision["region_context"] = region_context
        claims[claim.path] = decision
    return {
        "status": "verified",
        "content_hash": content_hash(content),
        "claims": claims,
    }


class ContentAuditorTests(unittest.TestCase):
    def test_fully_evidenced_content_passes(self):
        findings = audit_season("40", CONTENT, SEASON, catalog(), manifest())
        self.assertEqual(findings, [])

    def test_missing_season_review_is_hard_failure(self):
        findings = audit_season("40", CONTENT, SEASON, catalog(), None)
        self.assertEqual(findings[0].code, "missing-season-review")
        self.assertEqual(findings[0].severity, "hard")

    def test_modified_content_invalidates_approval_hash(self):
        changed = copy.deepcopy(CONTENT)
        changed["en"]["summary"] = "Watermelons are abundant in midsummer."

        findings = audit_season("40", changed, SEASON, catalog(), manifest())

        codes = {finding.code for finding in findings}
        self.assertIn("content-hash-mismatch", codes)

    def test_unknown_fact_is_rejected(self):
        review = manifest()
        review["claims"]["en.summary"]["fact_ids"] = ["fact:invented"]

        findings = audit_season("40", CONTENT, SEASON, catalog(), review)

        self.assertIn("missing-fact", {finding.code for finding in findings})

    def test_fact_outside_microseason_is_rejected(self):
        findings = audit_season(
            "40",
            CONTENT,
            SEASON,
            catalog(start="01-01", end="02-28"),
            manifest(),
        )
        self.assertIn("fact-outside-season-or-region", {finding.code for finding in findings})

    def test_regional_fact_requires_matching_context(self):
        regional_catalog = catalog(regions=["kansai"])
        without_context = audit_season(
            "40", CONTENT, SEASON, regional_catalog, manifest()
        )
        with_context = audit_season(
            "40",
            CONTENT,
            SEASON,
            regional_catalog,
            manifest(region_context="kansai"),
        )

        self.assertIn(
            "fact-outside-season-or-region",
            {finding.code for finding in without_context},
        )
        self.assertEqual(with_context, [])

    def test_one_fallback_source_is_insufficient(self):
        findings = audit_season(
            "40",
            CONTENT,
            SEASON,
            catalog(tier="culinary_reference"),
            manifest(),
        )
        self.assertIn("insufficient-evidence", {finding.code for finding in findings})

    def test_malformed_adjacent_scripts_are_rejected(self):
        changed = copy.deepcopy(CONTENT)
        changed["en"]["seasonal_dishes"][0]["name"] = "Shin-ninniku no醤油漬け"

        findings = audit_season(
            "40",
            changed,
            SEASON,
            catalog(),
            manifest(changed),
        )

        self.assertIn("malformed-mixed-script", {finding.code for finding in findings})

    def test_ingredient_category_mismatch_is_rejected(self):
        mismatched_catalog = catalog()
        mismatched_catalog["facts"][
            "fact:en.seasonal_produce.fruits[0]"
        ]["category"] = "fish"

        findings = audit_season(
            "40", CONTENT, SEASON, mismatched_catalog, manifest()
        )

        self.assertIn(
            "ingredient-category-mismatch",
            {finding.code for finding in findings},
        )

    def test_bilingual_fields_must_share_a_canonical_fact(self):
        bilingual = copy.deepcopy(CONTENT)
        bilingual["ja"] = copy.deepcopy(CONTENT["en"])

        findings = audit_season(
            "40",
            bilingual,
            SEASON,
            catalog(bilingual),
            manifest(bilingual),
        )

        self.assertIn("bilingual-fact-mismatch", {finding.code for finding in findings})

    def test_non_factual_exemption_is_limited_to_poetic_prose(self):
        review = manifest()
        review["claims"]["en.seasonal_produce.fruits[0]"] = {
            "status": "non_factual",
            "reviewer": "Human reviewer",
            "reviewed_at": "2026-07-23T12:00:00-04:00",
        }

        findings = audit_season("40", CONTENT, SEASON, catalog(), review)

        self.assertIn(
            "invalid-non-factual-classification",
            {finding.code for finding in findings},
        )


class GeneratedReferenceTests(unittest.TestCase):
    def _with_refs(self):
        payload = copy.deepcopy(CONTENT)
        payload["en"]["fact_refs"] = {
            claim.path.removeprefix("en."): [f"fact:{claim.path}"]
            for claim in iter_claims(payload)
        }
        return payload

    def test_generated_references_must_cover_every_factual_field(self):
        payload = self._with_refs()
        payload["en"]["fact_refs"].pop("seasonal_dishes[0].description")
        allowed = {
            fact_id
            for fact_ids in payload["en"]["fact_refs"].values()
            for fact_id in fact_ids
        }

        with self.assertRaisesRegex(ValueError, "seasonal_dishes"):
            validate_generated_fact_refs(payload, allowed)

    def test_generated_references_cannot_escape_fact_pack(self):
        payload = self._with_refs()
        payload["en"]["fact_refs"]["summary"] = ["fact:invented"]

        with self.assertRaisesRegex(ValueError, "outside approved fact pack"):
            validate_generated_fact_refs(payload, {"fact:en.summary"})


if __name__ == "__main__":
    unittest.main()
