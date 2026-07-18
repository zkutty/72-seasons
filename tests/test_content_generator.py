import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from content_generator import validate_english_produce
from season_mailer import generate_with_dish_variety


VALID_PAYLOAD = {
    "en": {
        "seasonal_produce": {
            "fruits": ["桃 (white peach)", "blueberry"],
            "vegetables": ["茗荷 (myoga ginger)"],
            "fish": ["鱧 (pike conger)"],
        }
    },
    "ja": {
        "seasonal_produce": {
            "fruits": ["桃", "ブルーベリー"],
            "vegetables": ["茗荷"],
            "fish": ["鱧"],
        }
    },
}


class EnglishProduceValidationTests(unittest.TestCase):
    def test_accepts_english_and_bilingual_labels_without_modifying_them(self):
        payload = copy.deepcopy(VALID_PAYLOAD)

        validate_english_produce(payload)

        self.assertEqual(payload, VALID_PAYLOAD)

    def test_rejects_japanese_only_values_in_english_block(self):
        payload = copy.deepcopy(VALID_PAYLOAD)
        payload["en"]["seasonal_produce"]["vegetables"] = ["茗荷", "空芯菜"]

        with self.assertRaisesRegex(ValueError, "茗荷.*空芯菜"):
            validate_english_produce(payload)

    def test_ignores_japanese_only_values_in_japanese_block(self):
        validate_english_produce(copy.deepcopy(VALID_PAYLOAD))

    def test_all_cached_english_seasons_have_english_labels_for_every_item(self):
        cache_path = Path(__file__).parents[1] / "data" / "content_cache.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8"))

        for season_id, payload in cache.items():
            if "en" in payload:
                with self.subTest(season_id=season_id):
                    validate_english_produce(payload)

    def test_generation_retries_after_invalid_english_produce(self):
        valid = copy.deepcopy(VALID_PAYLOAD)
        valid["en"]["seasonal_dishes"] = [
            {"name": "Dish one"},
            {"name": "Dish two"},
        ]
        valid["ja"]["seasonal_dishes"] = [
            {"name": "料理一"},
            {"name": "料理二"},
        ]

        with patch(
            "content_generator.generate_content",
            side_effect=[ValueError("Japanese-only produce"), valid],
        ) as generate:
            result = generate_with_dish_variety(
                season={},
                used={"en": set(), "ja": set()},
            )

        self.assertEqual(result, valid)
        self.assertEqual(generate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
