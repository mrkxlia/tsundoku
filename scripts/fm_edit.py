"""frontmatter の単一スカラーフィールドだけを行レベルで挿入/置換するユーティリティ。

organize.py の dump_note() は fm 辞書全体を毎回YAML再シリアライズするため、
既存ノートの frontmatter に対して行う編集(read/title/shelf_life/status/superseded_by の
バックフィルや更新)にそのまま使うと、iPhoneのObsidian Git・Cloudflare Functions(/api/read)
など他の書き手による並行コミットとの間で不要な差分(YAML再整形によるノイズ)や、
挿入位置が重なることによる衝突リスクを増やしてしまう。

このモジュールは「対象キーの行だけを差し替える/末尾に1行追記する」ことで、
git の行単位マージが素直に効くようにするための最小限のヘルパー。

対応するのは常に1行に収まる単純なスカラー値のフィールドのみ
(read: bool, title/shelf_life/status/superseded_by/published_at: 文字列)。
tags・sources・summary のような複数行/リスト値のフィールドは対象外 — それらは
引き続き organize.py の dump_note() 経由(ノート新規作成時のみ)で扱う。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

# 最初の "---\n...\n---\n" ブロックのみにマッチさせる(本文中に "---" や行頭 "status:" が
# 現れるノートが実在するため、split_frontmatter() と同じ非貪欲DOTALLパターンを使う)
_FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?\n)(---\s*\n?)", re.DOTALL)


class FrontmatterNotFoundError(ValueError):
    pass


def _dump_line(key: str, value: object) -> str:
    """"key: value" の1行分のYAMLフラグメントを生成する(必要なクォートはPyYAMLに任せる)。"""
    dumped = yaml.safe_dump(
        {key: value}, allow_unicode=True, default_flow_style=False, width=1000
    ).rstrip("\n")
    if "\n" in dumped:
        raise ValueError(
            f"fm_edit は単一行スカラーのみ対応: key={key!r} value={value!r} が複数行になった"
        )
    return dumped


def set_frontmatter_field(text: str, key: str, value: object) -> tuple[str, bool]:
    """ノート全文 `text` の frontmatter 内で `key` を `value` に設定する。

    既存の "key: ..." 行(行頭・トップレベルのみ)があればその行だけを置換し、
    無ければ frontmatter ブロック末尾(閉じ"---"の直前)に新規行として追記する。
    本文側やfrontmatterより後ろの内容には一切触れない。

    戻り値: (新しい全文, 実際に変更したか)
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise FrontmatterNotFoundError("frontmatterブロックが見つかりません")

    header, body, footer = m.group(1), m.group(2), m.group(3)
    new_line = _dump_line(key, value)

    line_re = re.compile(rf"^{re.escape(key)}:.*$", re.MULTILINE)
    existing = line_re.search(body)

    if existing:
        if existing.group(0) == new_line:
            return text, False
        new_body = body[: existing.start()] + new_line + body[existing.end() :]
    else:
        sep = "" if body.endswith("\n") else "\n"
        new_body = f"{body}{sep}{new_line}\n"

    return f"{header}{new_body}{footer}{text[m.end():]}", True


def set_frontmatter_fields(text: str, **fields: object) -> tuple[str, bool]:
    """複数フィールドをまとめて設定する。1つでも変更があれば changed=True。"""
    changed_any = False
    for key, value in fields.items():
        text, changed = set_frontmatter_field(text, key, value)
        changed_any = changed_any or changed
    return text, changed_any


def edit_note_file(path: Path, **fields: object) -> bool:
    """ノートファイルを読み込み、指定フィールドを行レベル編集して変更があれば書き戻す。"""
    text = path.read_text(encoding="utf-8")
    new_text, changed = set_frontmatter_fields(text, **fields)
    if changed:
        path.write_text(new_text, encoding="utf-8")
    return changed


# ---------------------------------------------------------------- tags(リスト)の行レベル編集
#
# tags は複数行のブロックシーケンス("tags:\n- a\n- b\n")のため、上記の単一行スカラー用
# ヘルパーとは別に、要素の追加/削除だけを行レベルで行うヘルパーを用意する。organize.py の
# dump_note() が生成する形式(default_flow_style=False、リスト項目は親キーと同じ列)を前提とする。

_TAGS_KEY_RE = re.compile(r"^tags:[ \t]*(\S.*)?$", re.MULTILINE)


def _dump_tag_item(tag: str) -> str:
    """"- tag" 1行分のYAMLフラグメントを生成する(クォート要否はPyYAMLに任せる)。"""
    dumped = yaml.safe_dump([tag], allow_unicode=True, default_flow_style=False, width=1000)
    line = dumped.rstrip("\n")
    if "\n" in line:
        raise ValueError(f"fm_edit のタグは単一行スカラーのみ対応: tag={tag!r} が複数行になった")
    return line


def _parse_tag_item(line: str) -> str | None:
    """"- xxx" 1行を要素1件のリストとして解釈し、値を返す(解釈できなければNone)。"""
    try:
        parsed = yaml.safe_load(line)
    except yaml.YAMLError:
        return None
    if isinstance(parsed, list) and len(parsed) == 1:
        return str(parsed[0])
    return None


def _find_tags_block(body: str) -> tuple[int, int, list[str]]:
    """frontmatter本文(body)内の `tags:` キーと、直後に連続する `- item` 行群の
    (開始位置, 終了位置, 各行の文字列リスト) を返す。

    `tags:` が見つからない場合は FrontmatterNotFoundError、`tags: [a, b]` のような
    フロースタイル(同じ行に値がある)の場合は ValueError を送出する(fm_editは
    ブロックスタイルのみ対応)。
    """
    m = _TAGS_KEY_RE.search(body)
    if not m:
        raise FrontmatterNotFoundError("frontmatterに tags: ブロックが見つかりません")
    if m.group(1):
        raise ValueError(f"fm_edit のタグ編集はブロックスタイルのみ対応: {m.group(0)!r}")

    lines_start = m.end() + 1  # "tags:\n" の次の行から
    item_lines: list[str] = []
    pos = 0
    for line in body[lines_start:].splitlines(keepends=True):
        if not line.startswith("- "):
            break
        item_lines.append(line.rstrip("\n"))
        pos += len(line)
    return lines_start, lines_start + pos, item_lines


def append_tag(text: str, tag: str) -> tuple[str, bool]:
    """frontmatter内の `tags:` ブロック末尾に `tag` を追加する。既に存在すれば無変更。

    戻り値: (新しい全文, 実際に変更したか)
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise FrontmatterNotFoundError("frontmatterブロックが見つかりません")
    header, body, footer = m.group(1), m.group(2), m.group(3)

    start, end, item_lines = _find_tags_block(body)
    if tag in {v for line in item_lines if (v := _parse_tag_item(line)) is not None}:
        return text, False

    new_body = body[:end] + _dump_tag_item(tag) + "\n" + body[end:]
    return f"{header}{new_body}{footer}{text[m.end():]}", True


def remove_tag(text: str, tag: str) -> tuple[str, bool]:
    """frontmatter内の `tags:` ブロックから `tag` と一致する行を削除する。

    戻り値: (新しい全文, 実際に変更したか)
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise FrontmatterNotFoundError("frontmatterブロックが見つかりません")
    header, body, footer = m.group(1), m.group(2), m.group(3)

    start, end, item_lines = _find_tags_block(body)
    kept_lines = [line for line in item_lines if _parse_tag_item(line) != tag]
    if len(kept_lines) == len(item_lines):
        return text, False
    if not kept_lines:
        raise ValueError(f"tag={tag!r} を削除すると tags: が空になります(fm_editは非対応)")

    new_block = "".join(f"{line}\n" for line in kept_lines)
    new_body = body[:start] + new_block + body[end:]
    return f"{header}{new_body}{footer}{text[m.end():]}", True


def edit_note_tags(path: Path, add: tuple[str, ...] = (), remove: tuple[str, ...] = ()) -> bool:
    """ノートファイルのtagsへ追加/削除を行レベル編集で適用し、変更があれば書き戻す。"""
    text = path.read_text(encoding="utf-8")
    changed_any = False
    for tag in add:
        text, changed = append_tag(text, tag)
        changed_any = changed_any or changed
    for tag in remove:
        text, changed = remove_tag(text, tag)
        changed_any = changed_any or changed
    if changed_any:
        path.write_text(text, encoding="utf-8")
    return changed_any
