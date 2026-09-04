"""fm_edit.py(frontmatterの行レベル編集)のテスト。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fm_edit

NOTE = "---\ntitle: T\nread: false\ntags:\n- a\n- b\nshelf_life: medium\n---\n\n本文\nstatus: これは本文の行\n"


class SetFrontmatterFieldTest(unittest.TestCase):
    def test_existing_line_is_replaced_in_place(self):
        text, changed = fm_edit.set_frontmatter_field(NOTE, "read", True)
        self.assertTrue(changed)
        self.assertEqual(text, NOTE.replace("read: false", "read: true"))

    def test_missing_key_is_appended_before_closing_fence(self):
        text, changed = fm_edit.set_frontmatter_field(NOTE, "published_at", "2026-08-01")
        self.assertTrue(changed)
        self.assertIn("shelf_life: medium\npublished_at: '2026-08-01'\n---\n", text)
        self.assertTrue(text.endswith("status: これは本文の行\n"))  # 本文は不変

    def test_same_value_is_a_noop(self):
        self.assertEqual(fm_edit.set_frontmatter_field(NOTE, "read", False), (NOTE, False))

    def test_body_lines_are_never_touched(self):
        text, _ = fm_edit.set_frontmatter_field(NOTE, "status", "superseded")
        self.assertIn("status: superseded\n---\n", text)
        self.assertIn("status: これは本文の行\n", text)

    def test_published_at_three_states_are_quoted_as_documented(self):
        # ''(到達したが発行日なし)と日付はクォート付きで書かれ、PyYAMLがdatetime化しない
        self.assertEqual(fm_edit._dump_line("published_at", ""), "published_at: ''")
        self.assertEqual(fm_edit._dump_line("published_at", "2026-08-01"), "published_at: '2026-08-01'")

    def test_multiline_value_and_missing_frontmatter_raise(self):
        with self.assertRaises(ValueError):
            fm_edit.set_frontmatter_field(NOTE, "summary", "1行目\n2行目")
        with self.assertRaises(fm_edit.FrontmatterNotFoundError):
            fm_edit.set_frontmatter_field("本文だけ", "read", True)


class TagsTest(unittest.TestCase):
    def test_append_tag_adds_after_existing_items_once(self):
        text, changed = fm_edit.append_tag(NOTE, "needs-recheck")
        self.assertTrue(changed)
        self.assertIn("tags:\n- a\n- b\n- needs-recheck\nshelf_life", text)
        self.assertEqual(fm_edit.append_tag(text, "needs-recheck"), (text, False))

    def test_remove_tag(self):
        text, changed = fm_edit.remove_tag(NOTE, "a")
        self.assertTrue(changed)
        self.assertIn("tags:\n- b\nshelf_life", text)
        self.assertEqual(fm_edit.remove_tag(NOTE, "zzz"), (NOTE, False))

    def test_removing_last_tag_is_refused(self):
        text, _ = fm_edit.remove_tag(NOTE, "a")
        with self.assertRaises(ValueError):
            fm_edit.remove_tag(text, "b")

    def test_flow_style_and_missing_tags_are_rejected(self):
        with self.assertRaises(ValueError):
            fm_edit.append_tag("---\ntags: [a, b]\n---\n", "c")
        with self.assertRaises(fm_edit.FrontmatterNotFoundError):
            fm_edit.append_tag("---\ntitle: T\n---\n", "c")


class EditNoteFileTest(unittest.TestCase):
    def test_file_is_rewritten_only_when_changed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "note.md"
            path.write_text(NOTE, encoding="utf-8")
            self.assertTrue(fm_edit.edit_note_file(path, read=True, last_verified="2026-09-04T00:00:00+00:00"))
            self.assertIn("read: true\n", path.read_text(encoding="utf-8"))
            self.assertIn("last_verified: '2026-09-04T00:00:00+00:00'\n---\n", path.read_text(encoding="utf-8"))
            self.assertFalse(fm_edit.edit_note_file(path, read=True))
            self.assertTrue(fm_edit.edit_note_tags(path, add=("needs-recheck",), remove=("a",)))
            self.assertIn("tags:\n- b\n- needs-recheck\n", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
