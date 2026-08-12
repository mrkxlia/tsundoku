"""既存ノートのfrontmatterに title が無い場合、一括で埋める one-offスクリプト。

tsundoku-siteの実装検証中に判明した問題への対応: Quartz側のfrontmatterパーサーは
title未設定時に「ファイル名そのもの」をtitleとして扱ってしまい、ページタイトル・見出し・
検索インデックス等サイト全体の表示が崩れる。organize.py は新規ノート作成時にLLM生成titleを
frontmatterへ書き込むようになったため、これは既存ノートの一括バックフィル専用。
冪等(既にtitleがあるノートはスキップ)。

タイトルの取得元は2段階:
1. 本文冒頭の "# 見出し" (article/video/slides/pdf 等はLLM生成タイトルそのもの)
2. 1が無い、または汎用テンプレート("Post by @user on X" — X投稿クリップの共有元アプリが
   常に付与する固定文言で、実際の投稿内容を表さない)の場合、ファイル名から復元する。
   ファイル名は organize.py の slugify(meta['title']) が生成したものなので、
   スペース→ハイフンの変換を逆にたどればLLM生成タイトルにかなり近い文字列が得られる
   (50文字切り詰め・一部記号除去により完全一致はしない場合がある)。

Usage: python scripts/backfill_titles.py
"""

from __future__ import annotations

import re
import sys

import fm_edit
import organize

# ノート本文は基本的に "# タイトル" 見出しで始まる(media_types.py の各type別テンプレート契約)。
# "## 画像の内容" 等のH2以降とは区別できるよう "#" の直後に空白1個以上を要求する。
H1_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)

# X投稿の共有元アプリが本文冒頭に必ず挿入する固定文言(実際のツイート内容を表さない)。
GENERIC_POST_HEADER_RE = re.compile(r"^Post by @\S+ on X$")

DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def title_from_h1(body: str) -> str | None:
    m = H1_RE.search(body)
    if not m:
        return None
    title = m.group(1).strip()
    return None if GENERIC_POST_HEADER_RE.match(title) else title


def title_from_filename(stem: str) -> str | None:
    without_date = DATE_PREFIX_RE.sub("", stem)
    title = without_date.replace("-", " ").strip()
    return title or None


def extract_title(note: organize.LibraryNote) -> tuple[str | None, str]:
    """(タイトル, 由来) を返す。由来は "h1" / "filename" / "none"。"""
    h1 = title_from_h1(note.body)
    if h1:
        return h1, "h1"
    filename_title = title_from_filename(note.path.stem)
    if filename_title:
        return filename_title, "filename"
    return None, "none"


def main() -> int:
    library = organize.load_library()
    updated = skipped_has_title = skipped_none = 0
    from_h1 = from_filename = 0

    for note in library:
        if note.fm.get("title"):
            skipped_has_title += 1
            continue
        title, source = extract_title(note)
        if not title:
            print(f"  [warn] タイトルを復元できずスキップ: {note.path.name}", file=sys.stderr)
            skipped_none += 1
            continue
        if fm_edit.edit_note_file(note.path, title=title):
            updated += 1
            from_h1 += source == "h1"
            from_filename += source == "filename"
            print(f"  [{source}] {note.path.relative_to(organize.ROOT)} -> title: {title}")

    print(
        f"完了: 更新 {updated}(見出しから {from_h1} / ファイル名から {from_filename}) "
        f"/ 既にtitleあり(スキップ) {skipped_has_title} / 復元不可(要確認) {skipped_none}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
