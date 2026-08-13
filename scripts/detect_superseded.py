"""既存/新規ノート間の重複・矛盾(superseded)を検知し、frontmatterへ status/superseded_by を
付与するスクリプト。

新規ノート(またはorganize.pyが今回処理した更新ノート)ごとに、埋め込みindex
(index/embeddings.json、build_embeddings.py が生成)上でチャンク最大コサイン類似度が閾値以上の、
自分より created が古い既存ノートの上位1〜2件を候補にし、judge_supersession(LLM)で
「新ノートが旧ノートの内容を上書き/矛盾させるか」を判定する。該当すれば旧ノートに
status: superseded / superseded_by を行レベル編集(fm_edit)で付与する。

index自体(status反映)は更新しない。build_embeddings.py --metadata-only を後続で実行し、
frontmatterの実体からindexのメタデータを再同期する(責務分離)。

対象ノートの決め方:
- 既定: index/new_notes.txt (organize.py が今回処理した新規/更新ノートの相対パス一覧) を読む。
  ファイルが無い/空ならチェック対象なし(何もしない)。
- --all: library/ の全ノートを対象にする(初回導入時の一括バックフィル用。無料枠を消費するため
  通常運用では使わない)。

前提: index/embeddings.json が事前にダウンロードされていること(埋め込み未生成のノートは
判定材料が無いためスキップする)。

環境変数: organize.py / llm_client.py と共通(GEMINI_API_KEY, DRY_RUN等)
"""

from __future__ import annotations

import argparse
import json
import sys

import fm_edit
import llm_client
import organize

INDEX_PATH = organize.ROOT / "index" / "embeddings.json"
NEW_NOTES_PATH = organize.ROOT / "index" / "new_notes.txt"

SIMILARITY_THRESHOLD = 0.80
MAX_CANDIDATES = 2


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--all", action="store_true", help="library/ の全ノートを対象に一括チェックする(初回導入用)"
    )
    return p.parse_args()


def load_index() -> dict | None:
    if not INDEX_PATH.exists():
        return None
    try:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def target_notes(index: dict, use_all: bool) -> list[str]:
    if use_all:
        return sorted(index["notes"].keys())
    if not NEW_NOTES_PATH.exists():
        return []
    lines = [ln.strip() for ln in NEW_NOTES_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [ln for ln in lines if ln in index["notes"]]


def chunk_max_similarity(chunks_a: list[dict], chunks_b: list[dict]) -> float:
    """2ノート間の全チャンク組み合わせのうち最大コサイン類似度(ベクトルは単位ベクトル済みなので内積)。"""
    best = -1.0
    for ca in chunks_a:
        va = ca.get("vector")
        if not va:
            continue
        for cb in chunks_b:
            vb = cb.get("vector")
            if not vb:
                continue
            sim = sum(x * y for x, y in zip(va, vb))
            if sim > best:
                best = sim
    return best


def find_candidates(index: dict, new_id: str) -> list[tuple[str, float]]:
    """new_idより古いcreatedを持つノートのうち、チャンク最大類似度が閾値以上の上位MAX_CANDIDATES件。"""
    new_note = index["notes"][new_id]
    new_created = new_note.get("created")
    new_chunks = new_note.get("chunks") or []
    if not new_created or not new_chunks:
        return []

    scored: list[tuple[str, float]] = []
    for other_id, other in index["notes"].items():
        if other_id == new_id or other.get("status") == "superseded":
            continue
        other_created = other.get("created")
        other_chunks = other.get("chunks") or []
        # created はISO8601形式('YYYY-MM-DDTHH:MM:SS')で統一されているため辞書順比較で時系列判定できる
        if not other_created or not other_chunks or other_created >= new_created:
            continue
        sim = chunk_max_similarity(new_chunks, other_chunks)
        if sim >= SIMILARITY_THRESHOLD:
            scored.append((other_id, sim))

    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:MAX_CANDIDATES]


def excerpt_of(note: dict) -> str:
    chunks = note.get("chunks") or []
    return chunks[0]["text"] if chunks and chunks[0].get("text") else ""


def main() -> int:
    args = parse_args()
    index = load_index()
    if index is None:
        print("index/embeddings.json が見つかりません(埋め込み未生成のためスキップ)")
        return 0

    targets = target_notes(index, args.all)
    if not targets:
        print("対象ノートはありません(新規ノートなし)")
        return 0
    print(f"{len(targets)}件を対象にsupersession判定します")

    client = llm_client.create_client()
    updated = 0

    for new_id in targets:
        new_note = index["notes"][new_id]
        candidates = find_candidates(index, new_id)
        if not candidates:
            continue

        for old_id, sim in candidates:
            old_note = index["notes"][old_id]
            print(f"* {new_id} vs {old_id} (類似度 {sim:.3f})")
            try:
                result = client.judge_supersession(
                    new_title=str(new_note.get("title", "")),
                    new_summary=str(new_note.get("summary", "")),
                    new_excerpt=excerpt_of(new_note),
                    old_title=str(old_note.get("title", "")),
                    old_summary=str(old_note.get("summary", "")),
                    old_excerpt=excerpt_of(old_note),
                )
            except llm_client.LLMError as e:
                print(f"  [warn] 判定に失敗(次回再試行): {e}", file=sys.stderr)
                continue

            if not result["supersedes"]:
                print(f"  -> 上書きなし({result['reason']})")
                continue

            old_path = organize.ROOT / old_id
            if not old_path.exists():
                print(f"  [warn] {old_id} がlibrary/に見つかりません(削除済み?)スキップ", file=sys.stderr)
                continue
            fm_edit.edit_note_file(old_path, status="superseded", superseded_by=new_id)
            old_note["status"] = "superseded"  # 同一run内で同じ旧ノートを二重に判定しないため
            updated += 1
            print(f"  -> {old_id} を superseded に設定(理由: {result['reason']})")

    print(f"完了: 対象 {len(targets)} / superseded付与 {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
