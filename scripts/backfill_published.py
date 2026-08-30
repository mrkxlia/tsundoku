"""既存ノートのfrontmatterに published_at が無い場合、発行日をページ実測で一括バックフィルするスクリプト。

organize.py は新規ノート作成時に media_types.enrich() 経由で発行日を取得するため、
このスクリプトは既存ノートの一括バックフィルと、取り込み時に到達不能だったノートの
再試行専用。LLMは使わない(発行日をLLMに聞かない規約はsuggest_similarと同じ)。

published_at の3状態(冪等キー = キーの存在):
  キー無し     = 未取得/前回到達不能 → このスクリプトの処理対象
  ''           = 到達したが発行日なしと確定 → スキップ(再取得しない)
  'YYYY-MM-DD' = 取得済み → スキップ

到達不能(fetch_published_dateがNone)だったノートはキーを書かずに残す = 次回実行で
自動的に再試行される(一時的なbotブロック・障害を''で恒久封印しないための設計)。
type: post はツイートIDからのオフライン算出、type: image は常に確定不明なので
ネットワークアクセスも --sleep も発生しない。

Usage: python scripts/backfill_published.py [--max-items N] [--sleep SECONDS]
"""

from __future__ import annotations

import argparse
import sys
import time

import fm_edit
import media_types
import organize
import page_meta

# ネットワークアクセスを伴わずに発行日を確定できるtype(sleep不要)
OFFLINE_TYPES = ("post", "image")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="このジョブでネットワーク取得するノート数の上限(超過分は次回実行へ)",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="ページGET間の待機秒数(取得先への負荷配慮。オフライン算出には適用しない)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    library = organize.load_library()
    updated = skipped = failed = 0
    fetched = 0  # --max-items のカウント対象(ネットワークを使った件数。失敗も含む)

    for note in library:
        if "published_at" in note.fm:
            skipped += 1
            continue

        url = str(note.fm.get("url") or "")
        if not url:
            # deepdiveノート等、urlを持たないノートは対象外(deepdiveは生成時に自分で書く)
            skipped += 1
            continue
        note_type = str(note.fm.get("type") or "article")

        uses_network = note_type not in OFFLINE_TYPES
        if uses_network and args.max_items is not None and fetched >= args.max_items:
            continue  # 上限到達分は次回実行へ持ち越し(オフライン算出分は上限に関係なく処理)

        value = media_types.fetch_published_date(url, note_type)
        if uses_network:
            fetched += 1

        if value is None:
            failed += 1
            print(f"  [warn] {note.path.name}: 到達できず(次回再試行)", file=sys.stderr)
        else:
            value = page_meta.sanitize_published(value, str(note.fm.get("created") or ""))
            if fm_edit.edit_note_file(note.path, published_at=value):
                updated += 1
                shown = value if value else "''(発行日なしと確定)"
                print(f"  {note.path.relative_to(organize.ROOT)} -> published_at: {shown}")

        if uses_network and args.sleep > 0:
            time.sleep(args.sleep)

    print(
        f"完了: 更新 {updated} / スキップ(処理済み・url無し) {skipped} / 到達不能(次回再試行) {failed}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
