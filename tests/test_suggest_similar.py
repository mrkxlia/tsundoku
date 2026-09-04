"""suggest_similar.py の純関数のテスト(tsundoku-site 側 nextRun.ts はこの挙動をミラーしている)。"""

from __future__ import annotations

import unittest

import suggest_similar


class SelectTargetClustersTest(unittest.TestCase):
    HISTORY = {
        "https://a": {"clusterId": "c01", "firstSuggestedAt": "2026-08-20T00:00:00+00:00"},
        "https://b": {"clusterId": "c01", "firstSuggestedAt": "2026-08-25T00:00:00+00:00"},
        "https://c": {"clusterId": "c02", "firstSuggestedAt": "2026-08-22T00:00:00+00:00"},
        "https://d": {"clusterId": "c99", "firstSuggestedAt": "2026-01-01T00:00:00+00:00"},  # 興味なし: 無視
    }

    def test_uninvestigated_first_then_oldest_last_investigation(self):
        # c03 は未調査(最優先)、c02 の最終調査 8/22 < c01 の最終調査 8/25(クラスタ内の最大値で比較)
        self.assertEqual(suggest_similar.select_target_clusters(["c01", "c02", "c03"], self.HISTORY, 3), ["c03", "c02", "c01"])

    def test_truncated_to_max_clusters(self):
        self.assertEqual(suggest_similar.select_target_clusters(["c01", "c02", "c03"], self.HISTORY, 1), ["c03"])
        self.assertEqual(suggest_similar.select_target_clusters(["c01"], self.HISTORY, 0), [])

    def test_ties_keep_input_order(self):
        # 同時刻(および全て未調査)は interests.json のキー順=入力順を保つ(nextRun.ts と同じ規約)
        self.assertEqual(suggest_similar.select_target_clusters(["c05", "c04", "c06"], {}, 3), ["c05", "c04", "c06"])
        history = {"https://x": {"clusterId": "c04", "firstSuggestedAt": "2026-08-20T00:00:00+00:00"},
                   "https://y": {"clusterId": "c05", "firstSuggestedAt": "2026-08-20T00:00:00+00:00"}}
        self.assertEqual(suggest_similar.select_target_clusters(["c05", "c04"], history, 2), ["c05", "c04"])

    def test_history_entries_without_fields_do_not_crash(self):
        history = {"https://x": {}, "https://y": {"clusterId": "c01"}}
        self.assertEqual(suggest_similar.select_target_clusters(["c01", "c02"], history, 2), ["c01", "c02"])


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- 却下フィードバック(tsundoku #33)

import contextlib
import io
from datetime import datetime, timezone
from unittest import mock

import llm_client


def _fb(action: str, ts: str = "2026-09-01T00:00:00.000Z", title: str = "T", cluster: str = "c01") -> dict:
    return {"action": action, "ts": ts, "title": title, "clusterId": cluster}


class NormalizeOrNoneTest(unittest.TestCase):
    def test_site_side_keys_are_pulled_to_python_normalization(self):
        self.assertEqual(suggest_similar.normalize_or_none("https://youtu.be/dQw4w9WgXcQ"), "https://youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(suggest_similar.normalize_or_none("https://x.com/a/status/1"), "https://twitter.com/a/status/1")
        self.assertEqual(suggest_similar.normalized_host("https://m.youtube.com/shorts/dQw4w9WgXcQ"), "youtube.com")

    def test_unparseable_values_are_none_not_exceptions(self):
        for value in ("https://[::1/x", "", "   ", None, 42):
            with self.subTest(value=value):
                self.assertIsNone(suggest_similar.normalize_or_none(value))
                self.assertIsNone(suggest_similar.normalized_host(value))


class ParseTsTest(unittest.TestCase):
    def test_both_timestamp_dialects_are_aware_and_comparable(self):
        js = suggest_similar.parse_ts("2026-09-01T00:00:00.443Z")
        py = suggest_similar.parse_ts("2026-09-01T00:00:00+00:00")
        self.assertIsNotNone(js.tzinfo)
        self.assertIsNotNone(py.tzinfo)
        self.assertLess(py, js)  # 文字列比較だと '+' < '.' で逆転する

    def test_naive_and_garbage_are_none(self):
        for value in ("2026-09-01T00:00:00", "garbage", "", None, 123):
            with self.subTest(value=value):
                self.assertIsNone(suggest_similar.parse_ts(value))


class SanitizeNegativeTitleTest(unittest.TestCase):
    def test_control_chars_collapse_and_length_is_capped(self):
        self.assertEqual(suggest_similar.sanitize_negative_title("a\nb​\tc  d"), "a b c d")
        self.assertEqual(len(suggest_similar.sanitize_negative_title("x" * 500)), llm_client.NEGATIVE_TITLE_MAX_CHARS)
        self.assertEqual(suggest_similar.sanitize_negative_title(None), "")


class CollectNegativeTitlesTest(unittest.TestCase):
    ITEMS = {
        "https://a/1": _fb("rejected", "2026-09-01T00:00:00.000Z", "c1-old"),
        "https://a/2": _fb("rejected", "2026-09-03T00:00:00.000Z", "c1-new"),
        "https://b/1": _fb("rejected", "2026-09-02T00:00:00.000Z", "other", cluster="c02"),
        "https://a/3": _fb("adopted", title="adopted-ignored"),
        "https://a/4": _fb("unrejected", title="unrejected-ignored"),
        "https://a/5": _fb("rejected", title=""),
    }

    def test_cluster_first_newest_then_global_fill_with_marker(self):
        self.assertEqual(
            suggest_similar.collect_negative_titles(self.ITEMS, "c01"),
            ["c1-new", "c1-old", f"{suggest_similar.GLOBAL_NEGATIVE_MARKER}other"],
        )

    def test_cap_and_disable_switch(self):
        with mock.patch.object(llm_client, "NEGATIVE_EXAMPLES_MAX", 2):
            self.assertEqual(suggest_similar.collect_negative_titles(self.ITEMS, "c01"), ["c1-new", "c1-old"])
        with mock.patch.object(llm_client, "NEGATIVE_EXAMPLES_MAX", 0):
            self.assertEqual(suggest_similar.collect_negative_titles(self.ITEMS, "c01"), [])


class PenalizedHostsTest(unittest.TestCase):
    def test_threshold_and_rejected_gt_adopted_rule(self):
        items = {
            "https://example.com/1": _fb("rejected"),
            "https://example.com/2": _fb("rejected"),
            "https://zenn.dev/a": _fb("rejected"),
            "https://zenn.dev/b": _fb("rejected"),
            "https://zenn.dev/c": _fb("adopted"),
            "https://zenn.dev/d": _fb("adopted"),
            "https://note.com/x": _fb("rejected"),
            "https://example.com/3": _fb("unrejected"),  # どちらにも数えない
        }
        penalized, stats = suggest_similar.penalized_hosts(items)
        self.assertEqual(penalized, {"example.com"})
        self.assertEqual(stats, {"example.com": (2, 0)})

    def test_youtube_short_forms_aggregate_to_watch_host_and_bad_keys_are_skipped(self):
        items = {
            "https://youtu.be/dQw4w9WgXcQ": _fb("rejected"),
            "https://www.youtube.com/watch?v=aaaaaaaaaaa": _fb("rejected"),
            "https://[::1/broken": _fb("rejected"),
        }
        penalized, stats = suggest_similar.penalized_hosts(items)
        self.assertEqual(penalized, {"youtube.com"})
        self.assertEqual(stats["youtube.com"], (2, 0))


class PartitionCandidatesTest(unittest.TestCase):
    def test_penalized_go_last_and_order_within_partitions_is_kept(self):
        cands = [
            ({"t": 1}, "https://youtu.be/dQw4w9WgXcQ", "2026-09-03"),  # youtube.com として減点
            ({"t": 2}, "https://example.com/a", "2026-09-02"),
            ({"t": 3}, "https://[::1/broken", "2026-09-01"),  # 解釈不能=減点なし・落ちない
            ({"t": 4}, "https://Example.com:443/b", "2026-08-01"),
        ]
        ordered = suggest_similar.partition_candidates(cands, {"youtube.com", "example.com"})
        self.assertEqual([(c[0]["t"], p) for c, p in ordered], [(3, False), (1, True), (2, True), (4, True)])


class RevivableHistoryKeysTest(unittest.TestCase):
    HISTORY = {
        "https://youtube.com/watch?v=dQw4w9WgXcQ": {"clusterId": "c01", "firstSuggestedAt": "2026-08-20T00:00:00+00:00"},
        "https://example.com/a": {"clusterId": "c01", "firstSuggestedAt": "2026-08-20T00:00:00+00:00"},
        "https://example.com/b": {"clusterId": "c01", "firstSuggestedAt": "2026-08-30T00:00:00+00:00"},
    }

    def _run(self, feedback):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = suggest_similar.revivable_history_keys(feedback, self.HISTORY)
        return result, err.getvalue()

    def test_unrejected_after_first_suggestion_revives_history_key(self):
        feedback = {
            "https://youtu.be/dQw4w9WgXcQ": _fb("unrejected", "2026-08-25T00:00:00.000Z"),  # サイト側キー→history キーへ寄せる
            "https://example.com/a": _fb("unrejected", "2026-08-25T00:00:00.000Z"),
            "https://example.com/b": _fb("unrejected", "2026-08-25T00:00:00.000Z"),  # 取り消し後に再提案済み(8/30)→復活しない
        }
        result, err = self._run(feedback)
        self.assertEqual(result, {"https://youtube.com/watch?v=dQw4w9WgXcQ", "https://example.com/a"})
        self.assertEqual(err, "")

    def test_missing_history_naive_ts_and_rejected_do_not_revive(self):
        feedback = {
            "https://example.com/gone": _fb("unrejected", "2026-08-25T00:00:00.000Z"),  # 履歴に無い(LRU失効等)
            "https://example.com/a": _fb("unrejected", "2026-08-25T00:00:00"),  # naive ts
            "https://example.com/b": _fb("rejected", "2026-09-01T00:00:00.000Z"),
        }
        result, err = self._run(feedback)
        self.assertEqual(result, set())
        self.assertIn("https://example.com/gone", err)
