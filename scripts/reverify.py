"""古くなった可能性のあるノートをGoogle Searchグラウンディングで再検証するスクリプト。

docs/future-reverification.md(Stage⑤設計メモ)の実装。

対象選定: `shelf_life` が short/medium(`--all` で long も含む全件)かつ `status` が
superseded でなく、`needs-recheck` タグが未付与で、`(last_verified または created)` から
一定日数(short=30日、medium=180日)経過したノートを、最も古い順に `--max-items` 件処理する。
処理後に `last_verified` が更新されキュー後方へ回るため、状態ファイルなしでレジュームが
成立する(build_embeddings.pyの`--max-embeds`と同様の思想)。

判定結果の反映(すべてfm_editによる行レベル編集):
    current   -> last_verified を更新するのみ
    outdated  -> needs-recheckタグを追加 + recheck_reason(1行に整形)+ last_verified を更新
    uncertain -> last_verified を更新するのみ
    判定失敗(LLMError/レスポンス解釈失敗) -> 何も更新せず次回に持ち越し

**status変更・archive/への移動は一切行わない。** 古い/誤りの疑いは needs-recheck タグに
留め、最終判断は人間のレビューを介在させる(Web検索ベースの判定はハルシネーションの
リスクがdetect_superseded.pyより高いため)。

`--clear PATH...` は誤判定解除用: 指定ノートの needs-recheck タグを外し、recheck_reason を
空にする(判定は行わない、API呼び出しなし)。

環境変数: organize.py / llm_client.py と共通(GEMINI_API_KEY, DRY_RUN等)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fm_edit
import llm_client
import organize

ROOT = organize.ROOT
REPORT_PATH = ROOT / "index" / "reverify_report.json"

THRESHOLD_DAYS = {"short": 30, "medium": 180}
DEFAULT_MAX_ITEMS = 40
EXCERPT_CHARS = 2000  # llm_client.VERIFY_EXCERPT_CHARSと同程度。抜粋のみで十分
REASON_MAX_CHARS = 200


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-items", type=int, default=DEFAULT_MAX_ITEMS)
    p.add_argument("--all", action="store_true", help="shelf_life:longも含め全件を対象にする")
    p.add_argument(
        "--clear", nargs="+", metavar="PATH", help="指定ノート(library/xxx.md)のneeds-recheckを解除する"
    )
    return p.parse_args()


def is_dry_run() -> bool:
    return organize.is_dry_run()


def is_real_vault() -> bool:
    """gitのorigin remoteが実Vault(mrkxlia/tsundoku)を指しているか。絶対パスの
    ハードコードだと複製先(rsyncコピー、.git無し)や別マシンで判定が崩れるため、
    remote URLで判定する(merge_notes.pyのis_real_vault()と同じ設計)。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    if result.returncode != 0:
        return False
    url = result.stdout.strip()
    return "mrkxlia/tsundoku" in url and "tsundoku-site" not in url


def sanitize_reason(reason: str) -> str:
    """fm_editの単一行スカラー制約(改行不可)に合わせ、改行・連続空白を潰して切り詰める。"""
    flat = " ".join((reason or "").split())
    return flat[:REASON_MAX_CHARS]


def parse_timestamp(value: object) -> datetime | None:
    """created(タイムゾーンなし)とlast_verified(UTC offset付き)の両方の形式を
    比較可能なnaive UTC datetimeとして解釈する。解釈できなければNone。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def is_target(note: organize.LibraryNote, now: datetime, use_all: bool) -> bool:
    if note.fm.get("status") == "superseded":
        return False
    if "needs-recheck" in (note.fm.get("tags") or []):
        return False

    shelf_life = note.fm.get("shelf_life")
    threshold_days = THRESHOLD_DAYS.get(shelf_life)
    if threshold_days is None:
        # long、または未設定/不正値のノート。--all時のみ経過日数を問わず対象にする
        return bool(use_all and shelf_life == "long")

    baseline = parse_timestamp(note.fm.get("last_verified") or note.fm.get("created"))
    if baseline is None:
        return True  # 日時が解釈できない場合は安全側で対象に含める
    return (now - baseline) >= timedelta(days=threshold_days)


def select_targets(
    notes: list[organize.LibraryNote], now: datetime, use_all: bool, max_items: int
) -> list[organize.LibraryNote]:
    candidates = [n for n in notes if is_target(n, now, use_all)]

    def sort_key(n: organize.LibraryNote) -> datetime:
        return parse_timestamp(n.fm.get("last_verified") or n.fm.get("created")) or datetime.min

    candidates.sort(key=sort_key)
    return candidates[:max_items]


def excerpt_of(note: organize.LibraryNote) -> str:
    return note.body[:EXCERPT_CHARS]


def clear_recheck(paths: list[str]) -> int:
    cleared = 0
    for rel in paths:
        path = ROOT / rel
        if not path.exists():
            print(f"警告: {rel} が見つかりません", file=sys.stderr)
            continue
        changed = fm_edit.edit_note_tags(path, remove=["needs-recheck"])
        fm_edit.edit_note_file(path, recheck_reason="")
        if changed:
            cleared += 1
        print(f"  -> {rel} のneeds-recheckを解除{'' if changed else '(タグは元々無し)'}")
    print(f"完了: {cleared}件解除")
    return 0


def main() -> int:
    args = parse_args()

    if args.clear:
        return clear_recheck(args.clear)

    if is_dry_run() and is_real_vault():
        print(
            "エラー: DRY_RUN=1 のまま実Vault(このリポジトリのorigin)へ再検証結果を"
            "書き込もうとしています。MockClientの決定的だが無意味な判定が実ノートに"
            "書き込まれるため拒否します。隔離コピー上で検証するか、DRY_RUNを解除してください。",
            file=sys.stderr,
        )
        return 1

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    notes = organize.load_library()
    targets = select_targets(notes, now, args.all, args.max_items)
    if not targets:
        print("対象ノートはありません")
        return 0
    print(f"{len(targets)}件を対象に再検証します")

    client = llm_client.create_client()
    stats = {"current": 0, "outdated": 0, "uncertain": 0, "failed": 0}
    results = []

    for note in targets:
        rel = str(note.path.relative_to(ROOT))
        title = str(note.fm.get("title", ""))
        print(f"* {rel}")
        try:
            verdict = client.verify_currency(
                title, str(note.fm.get("url", "")), str(note.fm.get("summary", "")), excerpt_of(note)
            )
        except llm_client.LLMError as e:
            print(f"  [warn] 判定に失敗(次回再試行): {e}", file=sys.stderr)
            stats["failed"] += 1
            continue

        v = verdict["verdict"]
        reason = sanitize_reason(verdict.get("reason", ""))
        stats[v] += 1
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if v == "outdated":
            fm_edit.edit_note_tags(note.path, add=["needs-recheck"])
            fm_edit.edit_note_file(note.path, recheck_reason=reason, last_verified=now_iso)
        else:
            fm_edit.edit_note_file(note.path, last_verified=now_iso)

        print(f"  -> {v}({reason})")
        results.append(
            {"path": rel, "verdict": v, "reason": reason, "sources": verdict.get("sources", [])}
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": stats,
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"\n完了: 対象{len(targets)} / current {stats['current']} / outdated {stats['outdated']}"
        f" / uncertain {stats['uncertain']} / 失敗 {stats['failed']}"
    )
    outdated = [r for r in results if r["verdict"] == "outdated"]
    if outdated:
        print("\noutdated一覧(needs-recheckタグを付与、人間のレビュー待ち):")
        for r in outdated:
            print(f"  - {r['path']}: {r['reason']}")
    print(f"レポート: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
