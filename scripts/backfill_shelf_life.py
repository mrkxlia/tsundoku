"""既存ノートのfrontmatterに shelf_life が無い場合、一括で分類してバックフィルするone-offスクリプト。

organize.py は新規ノート作成時に generate_note_meta の一部として shelf_life を取得するため、
このスクリプトは既存ノートの一括バックフィル専用。タイトル+要約のみを渡す軽量な専用分類
(llm_client.classify_shelf_life)を使い、本文全体の再送信は行わない。
冪等(既にshelf_lifeがあるノートはスキップ)。レジューム可能(--max-itemsで1回の処理件数を制限)。

Usage: python scripts/backfill_shelf_life.py [--max-items N]
"""

from __future__ import annotations

import argparse
import sys

import fm_edit
import llm_client
import organize


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="このジョブで新規に分類するノート数の上限(レート制限対策。超過分は次回実行へ)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    client = llm_client.create_client()
    library = organize.load_library()
    updated = skipped = failed = 0

    for note in library:
        if note.fm.get("shelf_life") in llm_client.VALID_SHELF_LIVES:
            skipped += 1
            continue
        if args.max_items is not None and updated >= args.max_items:
            continue  # 上限到達分は次回実行へ持ち越し

        title = str(note.fm.get("title", ""))
        summary = str(note.fm.get("summary", ""))
        try:
            shelf_life = client.classify_shelf_life(title, summary)
        except llm_client.LLMError as e:
            failed += 1
            print(f"  [warn] {note.path.name}: shelf_life分類に失敗(次回再試行): {e}", file=sys.stderr)
            continue

        if fm_edit.edit_note_file(note.path, shelf_life=shelf_life):
            updated += 1
            print(f"  {note.path.relative_to(organize.ROOT)} -> shelf_life: {shelf_life}")

    print(f"完了: 更新 {updated} / 既にshelf_lifeあり(スキップ) {skipped} / 失敗(次回再試行) {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
