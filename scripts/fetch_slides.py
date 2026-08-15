"""library/ の type: slides ノートのうち、スライド実体(PDF+ページ画像)が
未取得のものを対象に取得・保存する。

新規クリップの処理(organize.py経由、media_types.enrich()が同じ取得ロジックを呼ぶ)とは別に、
以下の用途で使う独立スクリプト:
- 既存ノートのバックフィル(導入時に一括で過去分を処理する)
- 取得失敗(元サイトのページ構造変化・一時的なネットワークエラー等)ノートのリカバリ
  (再実行するだけで再挑戦できる、冪等)

対象判定は assets/ の実体有無で行う(<stem>.pdf または <stem>-slide-01.jpg が既にあれば
処理済みとみなしスキップする)。assets/ 自体はpublicなvaultリポジトリにはcommitされず、
CI実行中のみ tsundoku-site(private)側 vault-assets/ の内容を一時的にコピーして使う。

環境変数:
    (外部アクセスの認証情報等は不要。単純なHTTP GET/POSTのみ)
"""

from __future__ import annotations

import argparse
import sys

import media_types
import organize

LIBRARY = organize.LIBRARY
ASSETS = organize.ASSETS


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="このジョブで新規に処理するノート数の上限(レート制限対策。超過分は次回実行へ)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="外部アクセスをせず対象件数のみ表示する",
    )
    return p.parse_args()


def already_fetched(stem: str) -> bool:
    return (ASSETS / f"{stem}.pdf").exists() or (ASSETS / f"{stem}-slide-01.jpg").exists()


def find_targets() -> list[tuple]:
    """(path, frontmatter, body) のリストを、type: slidesかつ未取得のノートのみ返す。"""
    targets = []
    for path in sorted(LIBRARY.glob("*.md")):
        parsed = organize.split_frontmatter(path.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        fm, body = parsed
        if fm.get("type") != "slides":
            continue
        if organize.SLIDE_SECTION_HEADER in body or already_fetched(path.stem):
            continue
        targets.append((path, fm, body))
    return targets


def process_one(path, fm: dict, body: str) -> bool:
    """1ノートを処理する。実体を1つ以上取得できたら True。"""
    url = fm.get("url", "")
    if not url:
        print(f"  -> {path.name}: frontmatterにurlが無いためスキップ", file=sys.stderr)
        return False
    print(f"* {path.name}")
    info = media_types.fetch_slide_assets(url, body)
    pdf_path, image_paths = organize.write_slide_assets(path.stem, info.slide_pdf, info.slide_images)
    if pdf_path is None and not image_paths:
        print("  -> 取得できず(needs-review継続、次回再実行時に再挑戦する)")
        return False
    body_final = organize.append_slide_section(body, pdf_path, image_paths)
    path.write_text(organize.dump_note(fm, body_final), encoding="utf-8")
    print(f"  -> PDF={'あり' if pdf_path else 'なし'}, 画像{len(image_paths)}枚")
    return True


def main() -> int:
    args = parse_args()
    ASSETS.mkdir(exist_ok=True)
    targets = find_targets()

    if args.dry_run:
        print(f"対象: {len(targets)}件(DRY_RUN、実際の取得は行わない)")
        return 0

    processed = 0
    fetched = 0
    for path, fm, body in targets:
        if args.max_items is not None and processed >= args.max_items:
            break
        processed += 1
        if process_one(path, fm, body):
            fetched += 1

    deferred = len(targets) - processed
    print(
        f"完了: 取得成功 {fetched} / 試行 {processed}"
        + (f" / 上限到達で次回へ持ち越し {deferred}" if deferred > 0 else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
