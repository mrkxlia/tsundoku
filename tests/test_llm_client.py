"""llm_client.py のネットワーク非依存な純関数(429解釈・設定パース・JSONパース)のテスト。"""

from __future__ import annotations

import json
import unittest

import llm_client


def _429_body(*details: dict) -> str:
    return json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": list(details)}})


QUOTA = "type.googleapis.com/google.rpc.QuotaFailure"
RETRY = "type.googleapis.com/google.rpc.RetryInfo"


class Parse429Test(unittest.TestCase):
    def test_per_day_quota_is_rpd(self):
        body = _429_body({"@type": QUOTA, "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]})
        self.assertEqual(llm_client._parse_429(body), ("rpd", None))

    def test_per_minute_quota_with_retry_delay_is_rpm(self):
        body = _429_body(
            {"@type": QUOTA, "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
            {"@type": RETRY, "retryDelay": "58s"},
        )
        self.assertEqual(llm_client._parse_429(body), ("rpm", 58.0))
        self.assertEqual(llm_client._parse_429(_429_body({"@type": RETRY, "retryDelay": "3.5s"})), ("unknown", 3.5))

    def test_rpd_wins_over_rpm_regardless_of_order(self):
        body = _429_body(
            {"@type": QUOTA, "violations": [{"quotaId": "X-PerMinute"}, {"quotaId": "Y-PerDay"}]},
        )
        self.assertEqual(llm_client._parse_429(body)[0], "rpd")

    def test_unparseable_bodies_degrade_to_unknown(self):
        for body in ("", "not json", "[]", json.dumps({"error": "string"}), json.dumps({"error": {"details": "x"}})):
            with self.subTest(body=body):
                self.assertEqual(llm_client._parse_429(body), ("unknown", None))
        self.assertEqual(llm_client._parse_429(_429_body({"@type": RETRY, "retryDelay": "later"})), ("unknown", None))


class ParseSleepOverridesTest(unittest.TestCase):
    def test_blank_is_none(self):
        self.assertIsNone(llm_client._parse_sleep_overrides(None))
        self.assertIsNone(llm_client._parse_sleep_overrides("  "))

    def test_pairs_are_parsed_and_malformed_ones_skipped(self):
        self.assertEqual(llm_client._parse_sleep_overrides("flash-lite=4, gemma=2.5,broken,x=abc"), {"flash-lite": 4.0, "gemma": 2.5})
        self.assertIsNone(llm_client._parse_sleep_overrides("broken,x=abc"))


class L2NormalizeTest(unittest.TestCase):
    def test_unit_vector_and_zero_vector(self):
        out = llm_client.l2_normalize([3.0, 4.0])
        self.assertAlmostEqual(out[0], 0.6)
        self.assertAlmostEqual(out[1], 0.8)
        self.assertEqual(llm_client.l2_normalize([0.0, 0.0]), [0.0, 0.0])


class ParseSuggestionsJsonTest(unittest.TestCase):
    def test_code_fence_is_stripped_and_entries_normalized(self):
        text = '```json\n[{"url": " https://a.example/ ", "title": "", "reason": "r"}, {"url": "ftp://x"}, "junk"]\n```'
        self.assertEqual(
            llm_client._parse_suggestions_json(text),
            [{"url": "https://a.example/", "title": "https://a.example/", "reason": "r"}],
        )

    def test_empty_array_is_a_valid_no_candidates_result(self):
        self.assertEqual(llm_client._parse_suggestions_json("[]"), [])
        self.assertEqual(llm_client._parse_suggestions_json("候補: []"), [])

    def test_non_array_returns_none_for_retry(self):
        self.assertIsNone(llm_client._parse_suggestions_json('{"url": "https://a.example"}'))
        self.assertIsNone(llm_client._parse_suggestions_json("no json here"))

    def test_candidates_are_capped(self):
        items = [{"url": f"https://a.example/{i}", "title": str(i)} for i in range(llm_client.MAX_SUGGEST_CANDIDATES + 3)]
        self.assertEqual(len(llm_client._parse_suggestions_json(json.dumps(items))), llm_client.MAX_SUGGEST_CANDIDATES)


if __name__ == "__main__":
    unittest.main()
