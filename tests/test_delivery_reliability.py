import unittest
from datetime import date
from unittest.mock import Mock, patch
import anthropic

import email_sender
from email_sender import AllSendsFailedError
from season_mailer import enrich_seasons_with_end_dates, find_active_season, generate_with_dish_variety, load_seasons, occurrence_start, should_send_occurrence


class CalendarTests(unittest.TestCase):
    def test_all_72_calendar_durations_are_positive_and_contiguous(self):
        enriched = enrich_seasons_with_end_dates(load_seasons(), 2026)
        self.assertEqual(len(enriched), 72)
        self.assertTrue(all(s["duration_days"] > 0 for s in enriched))
    def test_december_to_january_duration_and_occurrence(self):
        seasons = [
            {"id": 71, "start_month": 12, "start_day": 27},
            {"id": 72, "start_month": 1, "start_day": 1},
            {"id": 1, "start_month": 1, "start_day": 5},
        ]
        enriched = enrich_seasons_with_end_dates(seasons, 2026)
        self.assertEqual((enriched[0]["end_month"], enriched[0]["end_day"], enriched[0]["duration_days"]), (12, 31, 5))
        active = find_active_season(enriched, date(2027, 1, 3))
        self.assertEqual(active["id"], 72)
        self.assertEqual(occurrence_start({"start_month": 12, "start_day": 27}, date(2027, 1, 2)), date(2026, 12, 27))

    def test_occurrence_idempotency_keeps_plain_cache_key_policy(self):
        season = {"id": 72, "start_month": 12, "start_day": 27}
        today = date(2027, 1, 2)
        self.assertTrue(should_send_occurrence(None, season, today))
        self.assertTrue(should_send_occurrence("2025-12-27", season, today))
        self.assertFalse(should_send_occurrence("2026-12-27", season, today))
        self.assertEqual(str(season["id"]), "72")


class GenerationRetryTests(unittest.TestCase):
    def test_transient_and_malformed_errors_retry_but_client_error_does_not(self):
        valid = {"en": {"seasonal_dishes": [{"name": "one"}, {"name": "two"}]}, "ja": {"seasonal_dishes": [{"name": "一"}, {"name": "二"}]}}
        response = Mock(request=Mock())
        for error in (ValueError("bad json"), anthropic.APIConnectionError(request=None), anthropic.APITimeoutError(request=None), anthropic.RateLimitError("rate", response=response, body=None), anthropic.InternalServerError("server", response=response, body=None)):
            with self.subTest(error=type(error).__name__), patch("content_generator.generate_content", side_effect=[error, valid]) as generate:
                self.assertEqual(generate_with_dish_variety({}, {"en": set(), "ja": set()}), valid)
                self.assertEqual(generate.call_count, 2)
        with patch("content_generator.generate_content", side_effect=anthropic.AuthenticationError("no", response=response, body=None)) as generate:
            with self.assertRaises(anthropic.AuthenticationError):
                generate_with_dish_variety({}, {"en": set(), "ja": set()})
            self.assertEqual(generate.call_count, 1)


class RecipientIsolationTests(unittest.TestCase):
    season = {"id": 1, "slug": "test", "major_season": "Spring", "name_en": "Test", "name_jp": "試験", "name_romaji": "test", "start_month": 1, "start_day": 1, "end_month": 1, "end_day": 4, "duration_days": 4}
    content = {"en": {"seasonal_produce": {}, "seasonal_dishes": []}}

    def test_partial_failure_continues(self):
        with patch.dict("os.environ", {"RESEND_API_KEY": "test"}, clear=False), patch.object(email_sender, "_get_subscribers", return_value=[("a@example.com", "en"), ("b@example.com", "en")]), patch.object(email_sender, "_load_strings", return_value={"en": {}}), patch.object(email_sender, "_render", return_value="x"), patch.object(email_sender, "_send_with_retry", side_effect=[RuntimeError("bad"), None]), patch.object(email_sender, "_throttle"):
            self.assertIsNone(email_sender.send_email(self.season, self.content))

    def test_all_failures_raise(self):
        with patch.dict("os.environ", {"RESEND_API_KEY": "test"}, clear=False), patch.object(email_sender, "_get_subscribers", return_value=[("a@example.com", "en")]), patch.object(email_sender, "_load_strings", return_value={"en": {}}), patch.object(email_sender, "_render", return_value="x"), patch.object(email_sender, "_send_with_retry", side_effect=RuntimeError("bad")), patch.object(email_sender, "_throttle"):
            with self.assertRaises(AllSendsFailedError):
                email_sender.send_email(self.season, self.content)

    def test_language_tags_accept_object_string_and_default_unknown(self):
        self.assertEqual(email_sender._lang_from_tags([{"name": "lang:ja"}]), "ja")
        self.assertEqual(email_sender._lang_from_tags(["lang:en"]), "en")
        self.assertEqual(email_sender._lang_from_tags(["lang:fr"]), "en")
