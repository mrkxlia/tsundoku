"""library/ 内の関連ノートを統合する提案・適用スクリプト。

suggest: (1) 本文が薄い短小ノートを、埋め込みindex(index/embeddings.json)上の最近傍
ノートへの統合候補として、(2) 全ノート対の高類似ペアを統合候補として検出し、人間
レビュー用の統合計画ファイル(既定 index/merge_plan.json)を出力する。
**実際の統合は一切行わない。**

apply: suggest が出力した計画ファイルのうち "approved": true になっているペアだけを
対象に、決定的な統合処理を行う。1ペアごとに:
  - 情報量(本文の長さ)が多い側を keep、少ない側を merge とする(同値なら created が
    古い方を keep)
  - keep側のファイル名・title・url・created・read は変更しない(画像/PDF/スライド
    アセットが <ノートstem>-<連番> で紐づくため)
  - merge側の本文を keep側の末尾に「## 統合: <タイトル>」セクションとして原文のまま
    追記する(見出しはフェンスコード外のみ1段降格し、"## スライド"等のH2重複による
    site側プラグインの誤動作を避ける)
  - sources はURL正規化した重複排除で集約、tags は内容タグのみ generate_merged_meta
    (Gemini)で絞り込みシステムタグは機械的に温存、summary も同メソッドで再生成
    (--no-llm 時は keep の summary を維持しタグは和集合そのまま)、shelf_life は
    短い方(安全側)を採用
  - merge側を archive/ へ移動する
  - merge側を指す superseded_by 参照があれば keep側の新しいパスへ書き換える

このスクリプトはActionsには組み込まず、ローカルで手動実行する
(gh release download で事前に index/embeddings.json を取得しておくこと)。

環境変数: organize.py / llm_client.py と共通(GEMINI_API_KEY, DRY_RUN等)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import detect_superseded
import fm_edit
import llm_client
import organize
import page_meta

ROOT = organize.ROOT
LIBRARY = organize.LIBRARY
ARCHIVE = organize.ARCHIVE
PLAN_PATH = ROOT / "index" / "merge_plan.json"
REPORT_PATH = ROOT / "index" / "merge_report.json"

DEFAULT_SHORT_CHARS = 300
DEFAULT_SHORT_THRESHOLD = 0.60
DEFAULT_PAIR_THRESHOLD = 0.85
DEFAULT_PAIR_THRESHOLD_NO_LLM = 0.90  # LLMゲートが無い分、閾値側を厳しくする

# 運用系(システム)タグの定義は organize.is_operational_tag() に集約。統合時のタグ絞り込みでは
# LLMに渡さず機械的に温存する(README「システムタグ」を参照)。

SHELF_LIFE_ORDER = {"short": 0, "medium": 1, "long": 2}
SHELF_LIFE_BY_ORDER = {v: k for k, v in SHELF_LIFE_ORDER.items()}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("suggest", help="統合候補を検出し計画ファイルを出力する(実行はしない)")
    s.add_argument("--short-chars", type=int, default=DEFAULT_SHORT_CHARS)
    s.add_argument("--short-threshold", type=float, default=DEFAULT_SHORT_THRESHOLD)
    s.add_argument(
        "--pair-threshold",
        type=float,
        default=None,
        help=f"既定 {DEFAULT_PAIR_THRESHOLD}(--no-llm指定時は {DEFAULT_PAIR_THRESHOLD_NO_LLM})",
    )
    s.add_argument("--no-llm", action="store_true", help="judge_mergeによるLLM判定を行わない")
    s.add_argument("--plan-out", type=Path, default=PLAN_PATH)

    a = sub.add_parser("apply", help="承認済み(approved: true)のペアを実行する")
    a.add_argument("--plan", type=Path, default=PLAN_PATH)
    a.add_argument("--no-llm", action="store_true", help="summary/tags再生成をkeep維持+和集合にする")

    return p.parse_args()


# ---------------------------------------------------------------- 共通ヘルパー

def rel_id(note: organize.LibraryNote) -> str:
    return str(note.path.relative_to(ROOT))


def body_weight(body: str) -> int:
    return len(organize.normalize_body(body))


def is_real_vault() -> bool:
    """gitのorigin remoteが実Vault(mrkxlia/tsundoku)を指しているか。絶対パスの
    ハードコードだと複製先(rsyncコピー、.git無し)や別マシンで判定が崩れるため、
    remote URLで判定する(隔離コピーは.gitごと除外して作る運用のため、コピー先では
    git自体が失敗し False になる)。"""
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


def is_dry_run() -> bool:
    return os.environ.get("DRY_RUN") == "1"


# ---------------------------------------------------------------- suggest

def load_notes_with_index() -> tuple[list[organize.LibraryNote], dict]:
    index = detect_superseded.load_index()
    if index is None:
        print(
            "index/embeddings.json が見つかりません。先に取得してください:\n"
            "  gh release download embeddings-index --repo mrkxlia/tsundoku "
            "--pattern embeddings.json --dir index --clobber",
            file=sys.stderr,
        )
        sys.exit(1)
    return organize.load_library(), index


def eligible_notes(
    notes: list[organize.LibraryNote], index: dict
) -> list[tuple[organize.LibraryNote, str, dict]]:
    """(note, rel_id, indexのmeta)のうち統合候補として検討可能なもの
    (status:superseded除外、index未収載/チャンク空は除外)。"""
    out = []
    skipped = []
    for note in notes:
        rid = rel_id(note)
        if note.fm.get("status") == "superseded":
            continue
        meta = index.get("notes", {}).get(rid)
        if meta is None or not meta.get("chunks"):
            skipped.append(rid)
            continue
        out.append((note, rid, meta))
    if skipped:
        head = ", ".join(skipped[:5]) + ("..." if len(skipped) > 5 else "")
        print(f"警告: index未収載/チャンク空のため{len(skipped)}件をスキップ: {head}", file=sys.stderr)
    return out


def find_short_candidates(
    eligible: list[tuple[organize.LibraryNote, str, dict]], short_chars: int, threshold: float
) -> list[dict]:
    candidates = []
    for note, rid, meta in eligible:
        if body_weight(note.body) >= short_chars:
            continue
        best_rid, best_sim = None, -1.0
        for _, other_rid, other_meta in eligible:
            if other_rid == rid:
                continue
            sim = detect_superseded.chunk_max_similarity(meta["chunks"], other_meta["chunks"])
            if sim > best_sim:
                best_sim, best_rid = sim, other_rid
        if best_rid is None or best_sim < threshold:
            print(f"  (統合先なし: {rid} 最大類似度={best_sim:.3f})")
            continue
        candidates.append({"kind": "short", "a": rid, "b": best_rid, "similarity": round(best_sim, 4)})
    return candidates


def find_pair_candidates(
    eligible: list[tuple[organize.LibraryNote, str, dict]], threshold: float
) -> list[dict]:
    candidates = []
    n = len(eligible)
    for i in range(n):
        _, rid_a, meta_a = eligible[i]
        for j in range(i + 1, n):
            _, rid_b, meta_b = eligible[j]
            sim = detect_superseded.chunk_max_similarity(meta_a["chunks"], meta_b["chunks"])
            if sim >= threshold:
                candidates.append({"kind": "pair", "a": rid_a, "b": rid_b, "similarity": round(sim, 4)})
    return candidates


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    """類似度の高い順に採用し、1ノートが複数の統合ペアに登場しないようにする
    (貪欲法: 既に採用済みのノートを含む候補は捨てる)。"""
    used: set[str] = set()
    out = []
    for c in sorted(candidates, key=lambda c: c["similarity"], reverse=True):
        if c["a"] in used or c["b"] in used:
            continue
        used.add(c["a"])
        used.add(c["b"])
        out.append(c)
    return out


def decide_direction(
    note_a: organize.LibraryNote, note_b: organize.LibraryNote
) -> tuple[organize.LibraryNote, organize.LibraryNote]:
    """情報量(本文の長さ)が多い方を keep にする。同値なら created が古い方(先に
    存在したノート)を keep にし、ファイル名・URLの安定性を優先する。"""
    wa, wb = body_weight(note_a.body), body_weight(note_b.body)
    if wa != wb:
        return (note_a, note_b) if wa > wb else (note_b, note_a)
    ca, cb = str(note_a.fm.get("created") or ""), str(note_b.fm.get("created") or "")
    return (note_a, note_b) if ca <= cb else (note_b, note_a)


def print_report(pairs: list[dict]) -> None:
    if not pairs:
        print("\n統合候補は見つかりませんでした")
        return
    print(f"\n統合候補 {len(pairs)}件:")
    for i, p in enumerate(pairs, 1):
        llm = p.get("llm")
        llm_str = f"\n    LLM判定: merge={llm['merge']}({llm['reason']})" if llm else ""
        note_str = f"\n    注意: {p['note']}" if "note" in p else ""
        print(
            f"[{i}] kind={p['kind']} 類似度={p['similarity']:.3f}\n"
            f"    残す: {p['keep']} 「{p['keep_title']}」(created={p['keep_created']})\n"
            f"    統合: {p['merge']} 「{p['merge_title']}」(created={p['merge_created']})"
            f"{note_str}{llm_str}"
        )


def suggest(args: argparse.Namespace) -> int:
    pair_threshold = args.pair_threshold
    if pair_threshold is None:
        pair_threshold = DEFAULT_PAIR_THRESHOLD_NO_LLM if args.no_llm else DEFAULT_PAIR_THRESHOLD

    notes, index = load_notes_with_index()
    eligible = eligible_notes(notes, index)
    print(f"{len(eligible)}件を候補選定の対象にします(status:supersededとindex未収載を除く)")

    raw = find_short_candidates(eligible, args.short_chars, args.short_threshold)
    raw += find_pair_candidates(eligible, pair_threshold)

    # 同一ペアがshort/pair両方で検出された場合は、より強いシグナルであるpairを優先して1件化
    merged_by_key: dict[tuple[str, str], dict] = {}
    for c in raw:
        key = tuple(sorted((c["a"], c["b"])))
        cur = merged_by_key.get(key)
        if cur is None or (c["kind"] == "pair" and cur["kind"] != "pair"):
            merged_by_key[key] = c
    candidates = dedupe_candidates(list(merged_by_key.values()))

    notes_by_rid = {rid: note for note, rid, _ in eligible}
    client = None if args.no_llm else llm_client.create_client()

    pairs = []
    for c in candidates:
        keep, merge = decide_direction(notes_by_rid[c["a"]], notes_by_rid[c["b"]])
        entry = {
            "kind": c["kind"],
            "keep": rel_id(keep),
            "merge": rel_id(merge),
            "similarity": c["similarity"],
            "keep_title": str(keep.fm.get("title", "")),
            "merge_title": str(merge.fm.get("title", "")),
            "keep_created": keep.fm.get("created"),
            "merge_created": merge.fm.get("created"),
            "keep_type": keep.fm.get("type"),
            "merge_type": merge.fm.get("type"),
            "approved": False,
        }
        if keep.fm.get("type") == "slides" and merge.fm.get("type") == "slides":
            entry["note"] = "両方ともslidesノート — 統合後の「## スライド」見出し重複に注意"
        if client is not None:
            try:
                entry["llm"] = client.judge_merge(
                    str(keep.fm.get("title", "")),
                    str(keep.fm.get("summary", "")),
                    keep.body,
                    str(merge.fm.get("title", "")),
                    str(merge.fm.get("summary", "")),
                    merge.body,
                )
            except llm_client.LLMError as e:
                entry["llm"] = {"merge": None, "reason": f"判定失敗: {e}"}
        pairs.append(entry)

    print_report(pairs)

    plan = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {
            "short_chars": args.short_chars,
            "short_threshold": args.short_threshold,
            "pair_threshold": pair_threshold,
        },
        "pairs": pairs,
    }
    args.plan_out.parent.mkdir(parents=True, exist_ok=True)
    args.plan_out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"\n計画ファイル: {args.plan_out}\n"
        f"承認する組を \"approved\": true に書き換えてから `merge_notes.py apply` を実行してください"
        f"(このスクリプトはここで停止し、統合は一切実行していません)"
    )
    return 0


# ---------------------------------------------------------------- apply

def demote_headings(body: str) -> str:
    """フェンスコードブロック(```)内を除きATX見出し(#...)を1段降格する
    (統合先本文へH2以下を差し込む際、"## スライド"等の重複によるsite側プラグインの
    誤動作を避けるため)。"""
    lines = body.splitlines()
    out = []
    in_fence = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and re.match(r"^#{1,5}\s", line):
            out.append("#" + line)
        else:
            out.append(line)
    return "\n".join(out)


def build_merged_body(keep_body: str, merge_fm: dict, merge_body: str) -> str:
    merge_title = str(merge_fm.get("title", "")) or "(無題)"
    merge_url = str(merge_fm.get("url", ""))
    header = f"\n\n## 統合: {merge_title}\n\n(取り込み元: {merge_url})\n\n"
    return keep_body.rstrip() + header + demote_headings(merge_body.strip())


def split_system_tags(tags: object) -> tuple[list[str], list[str]]:
    """(内容タグ, システムタグ) に分離する(順序保持)。"""
    content, system = [], []
    for t in tags or []:
        t = str(t)
        (system if organize.is_operational_tag(t) else content).append(t)
    return content, system


def merge_sources(keep_fm: dict, merge_fm: dict) -> list[str]:
    keep_url_norm = organize.normalize_url(str(keep_fm.get("url", "")))
    raw = list(keep_fm.get("sources") or [])
    raw += [merge_fm.get("url", "")] + list(merge_fm.get("sources") or [])
    seen_norm = {keep_url_norm}
    out = []
    for u in raw:
        if not u:
            continue
        norm = organize.normalize_url(str(u))
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        out.append(u)
    return out


def merge_shelf_life(keep_fm: dict, merge_fm: dict) -> str:
    ka = SHELF_LIFE_ORDER.get(keep_fm.get("shelf_life"), SHELF_LIFE_ORDER["medium"])
    kb = SHELF_LIFE_ORDER.get(merge_fm.get("shelf_life"), SHELF_LIFE_ORDER["medium"])
    return SHELF_LIFE_BY_ORDER[min(ka, kb)]


def merge_published(keep_fm: dict, merge_fm: dict) -> str:
    """published_at の統合: keep側の実日付を優先、無ければmerge側。どちらも無ければ ''。

    createdのような blind str() 強制はしない — iPhoneのObsidianが `published_at: ''` を
    YAML null(値なし)に書き換えることがあり、str(None) だと文字列 'None' が焼き付く。
    日付形状の文字列だけを採用し、それ以外は ''(確定不明)へ落とす。
    """
    for fm in (keep_fm, merge_fm):
        v = fm.get("published_at")
        if isinstance(v, str):
            m = page_meta.DATE_RE.match(v)
            if m:
                return m.group(0)
    return ""


def resolve_merged_meta(
    client: llm_client.LLMClient | None,
    keep_fm: dict,
    merged_body: str,
    candidate_content_tags: list[str],
) -> tuple[str, list[str]]:
    if client is None:
        return str(keep_fm.get("summary", "")), candidate_content_tags or ["未分類"]
    try:
        meta = client.generate_merged_meta(str(keep_fm.get("title", "")), merged_body, candidate_content_tags)
        return meta["summary"], meta["tags"]
    except llm_client.LLMError as e:
        print(f"  [warn] summary/tags再生成に失敗、keep維持+和集合にフォールバック: {e}", file=sys.stderr)
        return str(keep_fm.get("summary", "")), candidate_content_tags or ["未分類"]


def load_note(rid: str) -> tuple[dict, str, Path]:
    path = ROOT / rid
    if not path.exists():
        raise FileNotFoundError(rid)
    parsed = organize.split_frontmatter(path.read_text(encoding="utf-8"))
    if parsed is None:
        raise ValueError(f"{rid}: frontmatterを解析できません")
    fm, body = parsed
    return fm, body, path


def apply_pair(entry: dict, client: llm_client.LLMClient | None) -> Path:
    keep_fm, keep_body, keep_path = load_note(entry["keep"])
    merge_fm, merge_body, merge_path = load_note(entry["merge"])

    merged_body = build_merged_body(keep_body, merge_fm, merge_body)

    keep_content, keep_system = split_system_tags(keep_fm.get("tags"))
    merge_content, merge_system = split_system_tags(merge_fm.get("tags"))
    candidate_content_tags = list(dict.fromkeys(keep_content + merge_content))
    system_tags = list(dict.fromkeys(keep_system + merge_system))

    summary, content_tags = resolve_merged_meta(client, keep_fm, merged_body, candidate_content_tags)

    new_fm = dict(keep_fm)
    new_fm["summary"] = summary
    new_fm["tags"] = list(dict.fromkeys(list(content_tags) + system_tags))
    new_fm["shelf_life"] = merge_shelf_life(keep_fm, merge_fm)
    new_fm["created"] = str(keep_fm.get("created", ""))  # YAMLのdatetime化を防ぐ(str強制)
    if "published_at" in keep_fm or "published_at" in merge_fm:
        new_fm["published_at"] = merge_published(keep_fm, merge_fm)
    sources = merge_sources(keep_fm, merge_fm)
    if sources:
        new_fm["sources"] = sources
    elif "sources" in new_fm:
        del new_fm["sources"]

    keep_path.write_text(organize.dump_note(new_fm, merged_body), encoding="utf-8")

    archived_path = organize.unique_path(ARCHIVE, merge_path.name)
    merge_path.rename(archived_path)

    print(f"  -> {entry['keep']} に統合(取り込み: {entry['merge']} -> archive/{archived_path.name})")
    return archived_path


def realign_superseded_by(applied: list[dict]) -> None:
    """merge側(archive行き)を指す superseded_by を keep側の新しいパスへ書き換える。"""
    rewrite_map = {e["merge"]: e["keep"] for e in applied}
    if not rewrite_map:
        return
    for path in sorted(LIBRARY.glob("*.md")):
        parsed = organize.split_frontmatter(path.read_text(encoding="utf-8"))
        if parsed is None:
            continue
        fm, _ = parsed
        target = fm.get("superseded_by")
        if isinstance(target, str) and target in rewrite_map:
            fm_edit.edit_note_file(path, superseded_by=rewrite_map[target])
            print(f"  -> {path.relative_to(ROOT)} の superseded_by を {rewrite_map[target]} へ更新")


def apply(args: argparse.Namespace) -> int:
    if is_dry_run() and is_real_vault():
        print(
            "エラー: DRY_RUN=1 のまま実Vault(このリポジトリのorigin)へ apply しようとしています。"
            "MockClientの適当なsummary/tagsが実ノートに書き込まれるため拒否します。"
            "隔離コピー上で検証するか、DRY_RUNを解除してください。",
            file=sys.stderr,
        )
        return 1

    if not args.plan.exists():
        print(f"計画ファイルが見つかりません: {args.plan}", file=sys.stderr)
        return 1
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    approved = [p for p in plan.get("pairs", []) if p.get("approved") is True]
    if not approved:
        print("承認済み(approved: true)のペアがありません")
        return 0

    # 事前検証: 1ノートが複数の承認済みペアに登場していないか、両ファイルが実在するか
    seen: set[str] = set()
    errors = []
    for p in approved:
        for rid in (p["keep"], p["merge"]):
            if rid in seen:
                errors.append(f"{rid} が複数の承認済みペアに登場しています(分割実行してください)")
            seen.add(rid)
            if not (ROOT / rid).exists():
                errors.append(f"{rid} が存在しません")
    if errors:
        for e in dict.fromkeys(errors):
            print(f"エラー: {e}", file=sys.stderr)
        return 1

    client = None if args.no_llm else llm_client.create_client()
    applied = []
    for p in approved:
        try:
            apply_pair(p, client)
            applied.append(p)
        except (FileNotFoundError, ValueError, llm_client.LLMError) as e:
            print(f"エラー: {p['keep']} <- {p['merge']} の統合に失敗: {e}", file=sys.stderr)
            return 1

    realign_superseded_by(applied)

    report = {"applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pairs": applied}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n完了: {len(applied)}件を統合しました(レポート: {REPORT_PATH})")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "suggest":
        return suggest(args)
    return apply(args)


if __name__ == "__main__":
    sys.exit(main())
