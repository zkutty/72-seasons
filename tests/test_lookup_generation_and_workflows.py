import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ingredient_generator
from ingredient_generator import LookupGenerationLimitError, run
import archive_builder
import email_sender
import season_mailer


def cache_with_items(*, ingredients=None, dishes=None):
    return {
        "1": {
            "seasonal_produce": {"fruits": ingredients or [], "vegetables": [], "fish": []},
            "seasonal_dishes": [{"name": name} for name in (dishes or [])],
        }
    }


class LookupGenerationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        data_dir = Path(self.tempdir.name)
        self.cache_path = data_dir / "content_cache.json"
        self.ingredients_path = data_dir / "ingredients.json"
        self.dishes_path = data_dir / "dishes.json"
        self.paths = patch.multiple(
            ingredient_generator,
            CACHE_PATH=self.cache_path,
            INGREDIENTS_P=self.ingredients_path,
            DISHES_P=self.dishes_path,
        )
        self.paths.start()

    def tearDown(self):
        self.paths.stop()
        self.tempdir.cleanup()

    def write(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_unchanged_lookup_data_makes_zero_paid_generation_calls(self):
        self.write(self.cache_path, cache_with_items(ingredients=["White peach"], dishes=["Peach salad"]))
        self.write(self.ingredients_path, {"white-peach": {"source": "White peach"}})
        self.write(self.dishes_path, {"peach-salad": {"source": "Peach salad"}})

        with patch.object(ingredient_generator, "_client") as client:
            self.assertEqual(run(max_api_calls=0), {"ingredients_added": 0, "dishes_added": 0})

        client.assert_not_called()

    def test_cap_blocks_all_paid_calls_with_a_clear_diagnostic(self):
        self.write(self.cache_path, cache_with_items(ingredients=["White peach"], dishes=["Peach salad"]))

        with patch.object(ingredient_generator, "_client") as client:
            with self.assertRaisesRegex(
                LookupGenerationLimitError,
                r"2 call\(s\) requested, but the per-run cap is 1",
            ):
                run(max_api_calls=1)

        client.assert_not_called()

    def test_explicit_batch_is_bounded_persists_progress_and_reruns_remaining_work(self):
        self.write(self.cache_path, cache_with_items(ingredients=["One", "Two", "Three"]))
        with (
            patch.object(ingredient_generator, "_client", return_value=object()) as client,
            patch.object(ingredient_generator, "generate_ingredient", side_effect=lambda _c, raw, _kind: {"name_en": raw}) as generate,
        ):
            first = run(max_api_calls=2, batch_size=2)
            self.assertEqual(first, {"ingredients_added": 2, "dishes_added": 0})
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(len(json.loads(self.ingredients_path.read_text())), 2)
            second = run(max_api_calls=2, batch_size=2)
        self.assertEqual(second, {"ingredients_added": 1, "dishes_added": 0})
        self.assertEqual(generate.call_count, 3)
        client.assert_called()


class SeasonMailerLookupCapTests(unittest.TestCase):
    def test_cached_delivery_and_static_build_continue_when_lookup_cap_is_exceeded(self):
        cache = season_mailer.load_cache()
        content = cache["44"]

        with (
            patch("sys.argv", ["season_mailer.py", "--force"]),
            patch.object(season_mailer, "load_cache", return_value={"44": content}),
            patch.object(season_mailer, "save_cache"),
            patch.object(
                ingredient_generator,
                "run",
                side_effect=LookupGenerationLimitError("207 call(s) requested, but the per-run cap is 24."),
            ) as generate_lookups,
            patch.object(email_sender, "send_email") as send_email,
            patch.object(archive_builder, "build_archive") as build_archive,
            patch.object(archive_builder, "build_website") as build_website,
        ):
            with self.assertLogs("season_mailer", level="WARNING") as logs:
                season_mailer.main()

        generate_lookups.assert_called_once_with()
        send_email.assert_called_once()
        build_archive.assert_called_once()
        build_website.assert_called_once()
        self.assertIn("LOOKUP API CALL CAP REACHED", "\n".join(logs.output))


class GeneratedOutputManifestTests(unittest.TestCase):
    def test_both_workflows_stage_the_complete_generated_output_manifest(self):
        root = Path(__file__).parents[1]
        required_paths = (
            "archive/",
            "ja/archive/",
            "index.html",
            "ja/index.html",
            "sitemap.xml",
            "unsubscribe.html",
            "ja/unsubscribe.html",
            "data/content_cache.json",
            "data/ingredients.json",
            "data/dishes.json",
        )
        for workflow in ("newsletter.yml", "season_check.yml"):
            with self.subTest(workflow=workflow):
                text = (root / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
                self.assertIn("git add --", text)
                for path in required_paths:
                    self.assertIn(path, text)


if __name__ == "__main__":
    unittest.main()
