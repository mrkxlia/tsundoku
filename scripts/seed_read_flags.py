"""既存ノートのfrontmatterに read が無い場合、一括で read: false を埋める one-offスクリプト。

新規キーの挿入(read:のような行の追加)は、frontmatter末尾という同じ位置に
複数の書き手(iPhoneのObsidian Git、Cloudflare Functionsの/api/read、organize.py)が
同時に書き込むと git の3-wayマージが衝突しやすい。既存ノート全件へ先に read:false を
埋めておけば、以降のread更新は常に「既存行の置換」になり、通常のマージが素直に成立する
(tsundoku-siteの実装計画にある整合性対策を参照)。organize.py は新規ノート作成時に
read:false を最初から書き込むため、このスクリプトは既存ノートの一括バックフィル専用。
冪等(既にreadがあるノートはスキップ)。

Usage: python scripts/seed_read_flags.py
"""

from __future__ import annotations

import sys

import fm_edit
import organize


def main() -> int:
    library = organize.load_library()
    updated = skipped = 0

    for note in library:
        if "read" in note.fm:
            skipped += 1
            continue
        if fm_edit.edit_note_file(note.path, read=False):
            updated += 1
            print(f"  {note.path.relative_to(organize.ROOT)} -> read: false")

    print(f"完了: 更新 {updated} / 既にreadあり(スキップ) {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
