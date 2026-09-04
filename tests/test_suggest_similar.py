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
