"""library/ 全ノートをチャンク分割し、Gemini埋め込みベクトルを生成して
index/embeddings.json (git管理外、ローカル/CI作業用) に書き出す。

方針:
- 文書側は "title: {title} | text: {chunk}" の接頭辞を付けて埋め込む
  (task_typeパラメータが効かないモデルのため、非対称検索用の接頭辞をプロンプト側で与える)。
  クエリ側の接頭辞書式もindexに記録し、site側(ask.ts)がコーパスと構造的に一致させられるようにする。
- 各ノートの再埋め込み要否は contentHash (接頭辞書式+タイトル+summary+本文+画像バイト+
  モデル名+次元数のsha256) で判定する。summaryだけの変更でも再埋め込みされる。
  モデル/次元/接頭辞書式を変えた場合は全ノートのハッシュが変わるため、自然に全件再埋め込みになる。
- 本文は段落(空行)単位でグルーピングしながら ~CHUNK_CHARS 文字ごとにチャンク化する。
  チャンク内にVault内画像(../assets/への相対参照)が含まれる場合は、画像バイトを
  マルチモーダル入力として追加し、その分テキスト予算を控除する(8,192トークンは
  全モダリティ合算のため)。外部ホスト画像(ダウンロードされていないもの)は対象外
  (テキストとしてはそのまま埋め込み対象に含まれる)。
- 1件処理するごとに index/embeddings.json 全体を書き直す(レジューム可能にするため)。
- lintの2値規則: ファイルは在るがfrontmatterを解析できない場合は前回indexのエントリを
  保持したまま警告するだけに留め、library/に実在しなくなったノート(削除/統合でarchiveへ
  移動)のみindexから除外する。

環境変数:
    DRY_RUN : "1" で外部APIを呼ばずMockClientで動作確認する
    (Gemini関連の環境変数は llm_client.py を参照)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import llm_client
import organize

ROOT = organize.ROOT
LIBRARY = organize.LIBRARY
ASSETS = organize.ASSETS
INDEX_PATH = ROOT / "index" / "embeddings.json"

CHUNK_CHARS = 4000
# 画像1枚 ≈600トークン(概算4文字/トークンとして2400字)をチャンクのテキスト予算から控除する
IMAGE_CHARS_BUDGET = 2400
MAX_IMAGES_PER_CHUNK = 4

DOC_PREFIX_TEMPLATE = "title: {title} | text: {text}"
QUERY_PREFIX_TEMPLATE = "task: search result | query: {query}"

LOCAL_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\.\./assets/([^)\s]+)\)")

MIME_BY_EXT = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--full", action="store_true", help="変更検知(contentHash)を無視して全ノートを再埋め込みする"
    )
    p.add_argument(
        "--max-embeds",
        type=int,
        default=None,
        help="このジョブで新規に埋め込むノート数の上限(レート制限対策。超過分は次回実行へ)",
    )
    p.add_argument(
        "--metadata-only",
        action="store_true",
        help="埋め込みは行わず、メタデータ(title/created/summary等)だけ全ノート更新する",
    )
    return p.parse_args()


# ---------------------------------------------------------------- index入出力

def load_index() -> dict:
    if INDEX_PATH.exists():
        try:
            return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"警告: {INDEX_PATH} が壊れています。新規作成します", file=sys.stderr)
    return {
        "version": 1,
        "model": None,
        "dim": None,
        "docPrefixTemplate": DOC_PREFIX_TEMPLATE,
        "queryPrefixTemplate": QUERY_PREFIX_TEMPLATE,
        "generatedAt": None,
        "notes": {},
    }


def save_index(index: dict) -> None:
    INDEX_PATH.parent.mkdir(exist_ok=True)
    index["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------- library走査

def scan_library() -> tuple[dict[str, tuple[dict, str]], set[str]]:
    """(成功にパースできたノートの{相対パス: (frontmatter, body)}, library/に実在する全.mdの相対パス集合)。"""
    parsed_notes: dict[str, tuple[dict, str]] = {}
    all_paths: set[str] = set()
    for path in sorted(LIBRARY.glob("*.md")):
        rel = str(path.relative_to(ROOT))
        all_paths.add(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            print(f"警告: {rel} を読み込めません({e})。前回indexのエントリを保持します", file=sys.stderr)
            continue
        parsed = organize.split_frontmatter(text)
        if parsed is None:
            print(f"警告: {rel} のfrontmatterを解析できません。前回indexのエントリを保持します", file=sys.stderr)
            continue
        parsed_notes[rel] = parsed
    return parsed_notes, all_paths


def local_image_paths(text: str) -> list[Path]:
    return [ASSETS / m.group(1) for m in LOCAL_IMAGE_RE.finditer(text)]


def image_mime(path: Path) -> str:
    return MIME_BY_EXT.get(path.suffix.lower().lstrip("."), "image/jpeg")


def compute_content_hash(fm: dict, body: str, image_paths: list[Path], model: str, dim: int) -> str:
    h = hashlib.sha256()
    for part in (DOC_PREFIX_TEMPLATE, str(fm.get("title", "")), str(fm.get("summary", "")), body):
        h.update(part.encode("utf-8"))
    for p in image_paths:
        try:
            h.update(p.read_bytes())
        except OSError:
            pass
    h.update(model.encode("utf-8"))
    h.update(str(dim).encode("utf-8"))
    return h.hexdigest()


# ---------------------------------------------------------------- チャンク化

def split_chunks(body: str) -> list[str]:
    """段落(空行区切り)単位でグルーピングし、~CHUNK_CHARS文字ごとに分割する。"""
    paragraphs = [p for p in re.split(r"\n{2,}", body.strip()) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        if current and current_len + len(para) > CHUNK_CHARS:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        if len(para) > CHUNK_CHARS:
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            for i in range(0, len(para), CHUNK_CHARS):
                chunks.append(para[i : i + CHUNK_CHARS])
            continue
        current.append(para)
        current_len += len(para)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [""]


def embed_note(
    client: llm_client.LLMClient, rel_path: str, title: str, body: str
) -> list[dict]:
    """1ノート分のチャンクを埋め込み、[{"text": 抜粋, "vector": [...]}] を返す。"""
    out = []
    for i, chunk_text in enumerate(split_chunks(body)):
        chunk_images = [p for p in local_image_paths(chunk_text) if p.exists()][:MAX_IMAGES_PER_CHUNK]
        budget = CHUNK_CHARS - IMAGE_CHARS_BUDGET * len(chunk_images)
        text = chunk_text
        if chunk_images and len(text) > budget:
            print(
                f"  [chunk] {rel_path}#{i}: 画像{len(chunk_images)}枚の予算控除により"
                f"{len(text)}→{max(budget, 200)}字に切り詰め",
                file=sys.stderr,
            )
            text = text[: max(budget, 200)]

        parts: list[dict] = [{"text": DOC_PREFIX_TEMPLATE.format(title=title, text=text)}]
        for img_path in chunk_images:
            try:
                data = img_path.read_bytes()
            except OSError:
                continue
            parts.append(
                {
                    "inline_data": {
                        "mime_type": image_mime(img_path),
                        "data": base64.b64encode(data).decode("ascii"),
                    }
                }
            )
        vector = client.embed_content(parts)
        out.append({"text": text, "vector": vector})
    return out


# ---------------------------------------------------------------- メイン処理

def main() -> int:
    args = parse_args()
    client = llm_client.create_client()
    model = os.environ.get("EMBEDDING_MODEL") or llm_client.DEFAULT_EMBEDDING_MODEL
    dim = int(os.environ.get("EMBED_DIM") or llm_client.DEFAULT_EMBED_DIM)

    parsed_notes, all_paths = scan_library()
    index = load_index()
    index["model"] = model
    index["dim"] = dim
    index["docPrefixTemplate"] = DOC_PREFIX_TEMPLATE
    index["queryPrefixTemplate"] = QUERY_PREFIX_TEMPLATE

    dropped = [k for k in list(index["notes"]) if k not in all_paths]
    for k in dropped:
        del index["notes"][k]
    if dropped:
        head = ", ".join(dropped[:5]) + ("..." if len(dropped) > 5 else "")
        print(f"drop: library/に実在しなくなった{len(dropped)}件をindexから除外: {head}")

    embedded_count = 0
    skipped_unchanged = 0
    for rel_path, (fm, body) in parsed_notes.items():
        title = str(fm.get("title", ""))
        existing = index["notes"].get(rel_path)

        # メタデータは(埋め込みの要否に関わらず)常に最新へ更新する
        meta = {
            "title": title,
            "created": fm.get("created"),
            "type": fm.get("type"),
            "status": fm.get("status"),
            "shelf_life": fm.get("shelf_life"),
            "summary": fm.get("summary"),
            "contentHash": existing.get("contentHash") if existing else None,
            "chunks": existing.get("chunks", []) if existing else [],
        }
        index["notes"][rel_path] = meta

        if args.metadata_only:
            continue

        image_paths = local_image_paths(body)
        content_hash = compute_content_hash(fm, body, image_paths, model, dim)
        if not args.full and existing and existing.get("contentHash") == content_hash:
            skipped_unchanged += 1
            continue

        if args.max_embeds is not None and embedded_count >= args.max_embeds:
            continue  # 今回の上限に達した分は次回実行へ持ち越し(indexは前回分のまま)

        print(f"* {rel_path}")
        try:
            chunks = embed_note(client, rel_path, title, body)
        except llm_client.LLMError as e:
            print(f"  -> 埋め込みに失敗(次回再試行): {e}", file=sys.stderr)
            continue
        meta["chunks"] = chunks
        meta["contentHash"] = content_hash
        embedded_count += 1
        save_index(index)  # 1件ごとにflush(中断時のレジューム用)

    if not args.metadata_only:
        save_index(index)

    deferred = len(parsed_notes) - skipped_unchanged - embedded_count
    print(
        f"完了: 埋め込み {embedded_count} / 変更なしスキップ {skipped_unchanged}"
        + (f" / 上限到達で次回へ持ち越し {deferred}" if deferred > 0 else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
