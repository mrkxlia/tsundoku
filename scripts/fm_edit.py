"""frontmatter の単一スカラーフィールドだけを行レベルで挿入/置換するユーティリティ。

organize.py の dump_note() は fm 辞書全体を毎回YAML再シリアライズするため、
既存ノートの frontmatter に対して行う編集(read/title/shelf_life/status/superseded_by の
バックフィルや更新)にそのまま使うと、iPhoneのObsidian Git・Cloudflare Functions(/api/read)
など他の書き手による並行コミットとの間で不要な差分(YAML再整形によるノイズ)や、
挿入位置が重なることによる衝突リスクを増やしてしまう。

このモジュールは「対象キーの行だけを差し替える/末尾に1行追記する」ことで、
git の行単位マージが素直に効くようにするための最小限のヘルパー。

対応するのは常に1行に収まる単純なスカラー値のフィールドのみ
(read: bool, title/shelf_life/status/superseded_by: 文字列)。
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
