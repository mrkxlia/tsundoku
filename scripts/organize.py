"""inbox/ のWebクリップを整理して library/ へ移動するスクリプト。

処理内容(1ファイルごと):
1. 1行目からURLを抽出(bare URL / Markdownリンクの両対応)
2. URLから種別(video/slides/post/image/pdf/article)を判定し、種別に応じて
   コンテンツを取得(media_types.py 参照。YouTube字幕・SpeakerDeck PDF・X oEmbed等)
3. LLM(llm_client)で タイトル・3行要約・タグ(3〜5個)を生成
   (PDFはGeminiのPDF入力、字幕が取れないYouTubeは動画URL直接入力で要約)
4. frontmatter(url, created, type, tags, summary)を付与
   (自動取得できなかったものは needs-review、メディア添付ありは has-media タグ)
5. library/ の既存ノートと突き合わせ、同一URL・酷似内容なら統合
   (情報量の多い方を残し、他方のURLを sources に追記、重複側は archive/ へ)
6. library/YYYY-MM-DD-<タイトルスラッグ>.md へ移動

環境変数:
    MAX_ITEMS_PER_RUN : 1回の実行で処理する最大件数(既定20。超過分は次回へ)
    DRY_RUN           : "1" で外部API(LLM/oEmbed)を呼ばずモックで動作確認
    (LLM関連は llm_client.py を参照)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import yaml

import llm_client
import media_types

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
LIBRARY = ROOT / "library"
ARCHIVE = ROOT / "archive"

DEFAULT_MAX_ITEMS = 20
SIMILARITY_THRESHOLD = 0.9
MIN_BODY_FOR_SIMILARITY = 100  # 短文同士の誤マージを避ける(空白除去後の文字数)

URL_RE = re.compile(r"https?://[^\s)\]\">]+")
TIMESTAMP_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[-_T ]?(\d{2}))?(?:[:\-]?(\d{2}))?(?:[:\-]?(\d{2}))?")
TRACKING_PARAMS = {"fbclid", "gclid", "yclid", "si", "ref", "ref_src", "s", "t", "igshid"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name) or ""
    return int(raw) if raw.strip() else default


def is_dry_run() -> bool:
    return os.environ.get("DRY_RUN") == "1"


# ---------------------------------------------------------------- クリップ解析

@dataclass
class Clip:
    path: Path
    url: str
    body: str
    created: str  # ISO形式
    title_hint: str


def extract_url(first_line: str) -> str | None:
    m = URL_RE.search(first_line)
    return m.group(0).rstrip(".,、。") if m else None


def is_clip_file(path: Path) -> bool:
    """1行目(最初の非空行)にURLを含む、frontmatter未付与の.mdか。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    if text.lstrip().startswith("---"):
        return False  # 既にfrontmatter付き(処理済み or 手書きノート)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    return extract_url(first) is not None


def collect_candidates() -> list[Path]:
    """inbox/*.md を主対象に、安全網としてルート直下のクリップ形式.mdも拾う。"""
    candidates: list[Path] = []
    if INBOX.is_dir():
        candidates += sorted(p for p in INBOX.glob("*.md") if is_clip_file(p))
    # 安全網: 保存先設定がルートのままの端末からのクリップ
    candidates += sorted(
        p
        for p in ROOT.glob("*.md")
        if p.name.lower() != "readme.md" and is_clip_file(p)
    )
    return candidates


def resolve_created(path: Path) -> str:
    """作成日時を ファイル名 → gitの追加日時 → mtime の順で解決する。"""
    m = TIMESTAMP_RE.search(path.stem)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        try:
            dt = datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0))
            return dt.isoformat()
        except ValueError:
            pass
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%aI", "--", str(path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip().splitlines()
        if out:
            return out[-1][:19]  # 最初にaddされたコミットの日時(タイムゾーンは落とす)
    except (subprocess.SubprocessError, OSError):
        pass
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def parse_clip(path: Path) -> Clip | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    first_idx = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first_idx is None:
        return None
    url = extract_url(lines[first_idx])
    if not url:
        return None
    body = "\n".join(lines[first_idx + 1 :]).strip()
    # ファイル名がタイムスタンプだけでなければタイトルのヒントに使う
    hint = "" if TIMESTAMP_RE.fullmatch(path.stem.strip()) else path.stem
    return Clip(path=path, url=url, body=body, created=resolve_created(path), title_hint=hint)


# ---------------------------------------------------------------- URL・重複判定

def normalize_url(url: str) -> str:
    # YouTubeは youtu.be / watch?v= / shorts 等の表記ゆれを watch URL に統一して重複統合を効かせる
    video_id = media_types.extract_youtube_id(url)
    if video_id:
        return f"https://youtube.com/watch?v={video_id}"
    p = urllib.parse.urlsplit(url.strip())
    host = p.netloc.lower().removeprefix("www.").removeprefix("mobile.")
    if host == "x.com":
        host = "twitter.com"
    query = urllib.parse.urlencode(
        [
            (k, v)
            for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
        ]
    )
    return urllib.parse.urlunsplit(("https", host, p.path.rstrip("/"), query, ""))


def normalize_body(body: str) -> str:
    return re.sub(r"\s+", "", body).lower()


def is_similar(body_a: str, body_b: str) -> bool:
    a, b = normalize_body(body_a), normalize_body(body_b)
    if len(a) < MIN_BODY_FOR_SIMILARITY or len(b) < MIN_BODY_FOR_SIMILARITY:
        return False
    if abs(len(a) - len(b)) / max(len(a), len(b)) > 0.5:
        return False  # 長さが違いすぎるものは早期除外
    return SequenceMatcher(None, a, b).ratio() >= SIMILARITY_THRESHOLD


# ---------------------------------------------------------------- ノート入出力

@dataclass
class LibraryNote:
    path: Path
    fm: dict
    body: str
    urls: set[str] = field(default_factory=set)  # 正規化済み(url + sources)


def split_frontmatter(text: str) -> tuple[dict, str] | None:
    if not text.startswith("---"):
        return None
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return (fm if isinstance(fm, dict) else {}), text[m.end() :]


def load_library() -> list[LibraryNote]:
    notes = []
    if not LIBRARY.is_dir():
        return notes
    for path in sorted(LIBRARY.glob("*.md")):
        parsed = split_frontmatter(path.read_text(encoding="utf-8"))
        if not parsed:
            continue
        fm, body = parsed
        urls = {normalize_url(u) for u in [fm.get("url", "")] + list(fm.get("sources") or []) if u}
        notes.append(LibraryNote(path=path, fm=fm, body=body, urls=urls))
    return notes


def dump_note(fm: dict, body: str) -> str:
    front = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{front}---\n\n{body.strip()}\n"


def slugify(title: str) -> str:
    s = re.sub(r'[\\/:*?"<>|#^\[\]{}\r\n\t]', " ", title)
    s = re.sub(r"\s+", "-", s.strip())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:50].rstrip("-") or "untitled"


def unique_path(directory: Path, name: str) -> Path:
    path = directory / name
    stem, suffix = path.stem, path.suffix
    n = 2
    while path.exists():
        path = directory / f"{stem}-{n}{suffix}"
        n += 1
    return path


# ---------------------------------------------------------------- メイン処理

def process_clip(clip: Clip, client: llm_client.LLMClient, library: list[LibraryNote]) -> str:
    """1クリップを処理し、結果ラベル(organized/merged/absorbed)を返す。"""
    info = media_types.enrich(clip.url, clip.body, dry_run=is_dry_run())
    body = info.note_body
    hint = clip.title_hint or info.title_hint

    meta = None
    if info.pdf is not None:
        try:
            meta = client.generate_note_meta_from_pdf(clip.url, hint, info.pdf)
        except llm_client.LLMError as e:
            print(f"    [llm] PDF要約に失敗(テキスト経路へ縮退): {e}", file=sys.stderr)
            info.extra_tags.append("needs-review")
    elif info.video_uri:
        try:
            meta = client.generate_note_meta_from_video(clip.url, hint, info.video_uri)
        except llm_client.LLMError as e:
            print(f"    [llm] 動画要約に失敗(タイトルのみで続行): {e}", file=sys.stderr)
            info.extra_tags.append("needs-review")
    if meta is None:
        meta = client.generate_note_meta(clip.url, hint, info.llm_body)

    fm: dict = {
        "url": clip.url,
        "created": clip.created,
        "type": info.type,
        "tags": list(dict.fromkeys(meta["tags"] + info.extra_tags)),
        "summary": meta["summary"],
    }
    date = clip.created[:10]
    filename = f"{date}-{slugify(meta['title'])}.md"

    url_norm = normalize_url(clip.url)
    dup = next(
        (n for n in library if url_norm in n.urls or is_similar(body, n.body)),
        None,
    )

    if dup is None:
        new_path = unique_path(LIBRARY, filename)
        new_path.write_text(dump_note(fm, body), encoding="utf-8")
        clip.path.unlink()
        library.append(
            LibraryNote(path=new_path, fm=fm, body=body, urls={url_norm})
        )
        print(f"  -> library/{new_path.name}")
        return "organized"

    # 重複: 情報量(本文の長さ)が多い方を library に残す
    if len(normalize_body(body)) > len(normalize_body(dup.body)):
        # 新しい方が充実 → 既存ノートを archive へ、URLは新ノートの sources に集約
        sources = [u for u in [dup.fm.get("url", "")] + list(dup.fm.get("sources") or []) if u]
        sources = [u for u in dict.fromkeys(sources) if normalize_url(u) != url_norm]
        if sources:
            fm["sources"] = sources
        archived = unique_path(ARCHIVE, dup.path.name)
        dup.path.rename(archived)
        new_path = unique_path(LIBRARY, filename)
        new_path.write_text(dump_note(fm, body), encoding="utf-8")
        clip.path.unlink()
        dup.path, dup.fm, dup.body = new_path, fm, body
        dup.urls |= {url_norm}
        print(f"  -> library/{new_path.name} (既存 {archived.name} を統合し archive へ)")
        return "merged"

    # 既存の方が充実 → 既存に sources 追記し、新クリップは archive へ
    if url_norm not in dup.urls:
        if not isinstance(dup.fm.get("sources"), list):
            dup.fm["sources"] = []
        dup.fm["sources"].append(clip.url)
        dup.urls.add(url_norm)
        dup.path.write_text(dump_note(dup.fm, dup.body), encoding="utf-8")
    archived = unique_path(ARCHIVE, filename)
    archived.write_text(dump_note(fm, body), encoding="utf-8")
    clip.path.unlink()
    print(f"  -> archive/{archived.name} (既存 {dup.path.name} に統合)")
    return "absorbed"


def main() -> int:
    for d in (INBOX, LIBRARY, ARCHIVE):
        d.mkdir(exist_ok=True)

    max_items = env_int("MAX_ITEMS_PER_RUN", DEFAULT_MAX_ITEMS)
    candidates = collect_candidates()
    if not candidates:
        print("処理対象のクリップはありません")
        return 0

    deferred = max(0, len(candidates) - max_items)
    candidates = candidates[:max_items]
    print(f"{len(candidates)}件を処理します" + (f"(残り{deferred}件は次回へ)" if deferred else ""))

    client = llm_client.create_client()
    library = load_library()
    stats = {"organized": 0, "merged": 0, "absorbed": 0, "failed": 0}

    for path in candidates:
        rel = path.relative_to(ROOT)
        print(f"* {rel}")
        try:
            clip = parse_clip(path)
            if clip is None:
                print("  -> スキップ(クリップ形式でない)")
                continue
            stats[process_clip(clip, client, library)] += 1
        except llm_client.LLMError as e:
            stats["failed"] += 1
            print(f"  -> 保留(LLM失敗、次回再試行): {e}", file=sys.stderr)
        except Exception as e:  # 1件の失敗で全体を止めない
            stats["failed"] += 1
            print(f"  -> 保留(エラー、次回再試行): {e}", file=sys.stderr)

    print(
        f"完了: 整理 {stats['organized']} / 統合 {stats['merged'] + stats['absorbed']} / 保留 {stats['failed']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
