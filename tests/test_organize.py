"""organize.py の純関数(URL正規化・frontmatter分割・slug化)のテスト。ファイルシステム・LLMは使わない。"""

from __future__ import annotations

import unittest

import organize


class NormalizeUrlTest(unittest.TestCase):
    def test_tracking_params_are_stripped_and_host_is_normalized(self):
        self.assertEqual(
            organize.normalize_url("http://www.Example.com/a/?utm_source=x&UTM_Campaign=y&fbclid=1&q=1"),
            "https://example.com/a?q=1",
        )

    def test_non_tracking_query_is_kept_and_trailing_slash_is_removed(self):
        self.assertEqual(organize.normalize_url("https://example.com/path/?page=2&ref=nav"), "https://example.com/path?page=2")
        self.assertEqual(organize.normalize_url("https://example.com/"), "https://example.com")

    def test_x_com_and_mobile_prefix_become_twitter(self):
        self.assertEqual(organize.normalize_url("https://mobile.x.com/user/status/1"), "https://twitter.com/user/status/1")
        self.assertEqual(organize.normalize_url("https://x.com/user/status/1?s=20&t=abc"), "https://twitter.com/user/status/1")

    def test_youtube_variants_collapse_to_watch_url(self):
        for url in (
            "https://youtu.be/dQw4w9WgXcQ?si=abc",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=10s",
            "https://youtube.com/shorts/dQw4w9WgXcQ",
        ):
            with self.subTest(url=url):
                self.assertEqual(organize.normalize_url(url), "https://youtube.com/watch?v=dQw4w9WgXcQ")

    def test_surrounding_whitespace_is_ignored(self):
        self.assertEqual(organize.normalize_url("  https://example.com/x \n"), "https://example.com/x")


class SplitFrontmatterTest(unittest.TestCase):
    def test_text_without_frontmatter_returns_none(self):
        self.assertIsNone(organize.split_frontmatter("# 見出し\n本文"))
        self.assertIsNone(organize.split_frontmatter("---\nunterminated: yes\n"))

    def test_frontmatter_and_body_are_separated(self):
        # 閉じフェンス直後の空行は正規表現の \s* が消費する(本文は最初の非空行から始まる)
        text = "---\ntitle: T\ntags:\n- a\n---\n\n本文1行目\n"
        self.assertEqual(organize.split_frontmatter(text), ({"title": "T", "tags": ["a"]}, "本文1行目\n"))

    def test_only_first_block_is_frontmatter_even_if_body_has_dashes(self):
        text = "---\nstatus: active\n---\n段落\n---\nstatus: superseded\n---\n"
        fm, body = organize.split_frontmatter(text)
        self.assertEqual(fm, {"status": "active"})
        self.assertIn("status: superseded", body)

    def test_invalid_yaml_returns_none_and_scalar_yaml_returns_empty_dict(self):
        self.assertIsNone(organize.split_frontmatter("---\n: [\n---\n"))
        self.assertEqual(organize.split_frontmatter("---\njust a string\n---\nbody"), ({}, "body"))

    def test_dump_note_round_trips_through_split_frontmatter(self):
        fm = {"title": "長い" * 60, "url": "https://example.com/x", "published_at": "2026-08-01", "read": False, "tags": ["a", "b"]}
        parsed_fm, body = organize.split_frontmatter(organize.dump_note(fm, "本文\n"))
        self.assertEqual(parsed_fm, fm)
        self.assertEqual(body.strip(), "本文")
        # fm_edit の「対象キーは常に1行」前提: 長いtitleが折り返されない
        self.assertEqual(organize.dump_note(fm, "").count("title:"), 1)
        self.assertNotIn("\n  ", organize.dump_note(fm, "").split("---")[1])


class SlugifyTest(unittest.TestCase):
    def test_forbidden_characters_and_whitespace(self):
        self.assertEqual(organize.slugify('a/b\\c: "d" | e?  f'), "a-b-c-d-e-f")

    def test_truncation_and_fallback(self):
        self.assertEqual(len(organize.slugify("x" * 80)), 50)
        self.assertEqual(organize.slugify("あ" * 49 + " " + "い" * 10), "あ" * 49)  # 50字目の "-" は落とす
        self.assertEqual(organize.slugify("///"), "untitled")


if __name__ == "__main__":
    unittest.main()
