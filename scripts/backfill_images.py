"""既存の library/ ノート(type: post)に対し、添付画像を後付けで取り込むone-offスクリプト。

新規クリップの日次処理(organize.py)とは独立して、手動(workflow_dispatch)で
一度だけ実行する想定。organize.py/media_types.py/llm_client.py の既存関数を
そのまま再利用し、新規ノート作成やdedup状態には一切触れない
(既存ノートの本文とtagsだけをその場で書き換える)。

再実行しても、既に「## 画像の内容」セクションを持つノートはスキップされるため冪等。

環境変数: organize.py / llm_client.py と共通(GEMINI_API_KEY, DRY_RUN等)

注記(スライドアセットのprivate側移行、2026-08、同期ステップ実装済み): このスクリプトが
書き出す画像は organize.write_assets() 経由で assets/ に保存されるが、assets/ は
.gitignore対象(実体は tsundoku-site の vault-assets/ で管理)。呼び出し元の
backfill_images.yml が organize.yml と同じパターンで、実行前に vault-assets/ を
assets/ へ同期し、実行後に新規ファイルを vault-assets/ へ書き戻す。
"""

from __future__ import annotations

import sys

import llm_client
import media_types
import organize


def backfill_note(note: organize.LibraryNote, client: llm_client.LLMClient) -> bool:
    if note.fm.get("type") != "post":
        return False
    if organize.IMAGE_SECTION_HEADER in note.body:
        return False  # 既に処理済み
    url = note.fm.get("url", "")
    if not url:
        return False

    if organize.is_dry_run():
        print("  [dry-run] 画像取得をスキップ")
        return False

    info = media_types.MediaInfo(type="post", note_body=note.body, llm_body=note.body)
    try:
        media_types._gather_post_images(url, info)
    except Exception as e:  # 取得系の想定外エラーでもワークフローは落とさない
        print(f"  [skip] 画像取得でエラー: {e}", file=sys.stderr)
        return False
    if not info.images:
        return False

    image_text = ""
    try:
        image_text = client.describe_images(
            url, [(a.data, a.mime) for a in info.images]
        ).strip()
    except llm_client.LLMError as e:
        print(f"  [warn] 画像説明に失敗(埋め込みのみで続行): {e}", file=sys.stderr)

    asset_paths = organize.write_assets(note.path.stem, info.images)
    note.body = organize.append_image_section(note.body, asset_paths, image_text)
    tags = note.fm.get("tags") or []
    if "has-media" not in tags:
        note.fm["tags"] = list(tags) + ["has-media"]
    note.path.write_text(organize.dump_note(note.fm, note.body), encoding="utf-8")
    return True


def main() -> int:
    organize.ASSETS.mkdir(exist_ok=True)
    client = llm_client.create_client()
    notes = [n for n in organize.load_library() if n.fm.get("type") == "post"]
    print(f"{len(notes)}件のpost型ノートを確認します")

    updated = 0
    for note in notes:
        print(f"* {note.path.name}")
        if backfill_note(note, client):
            updated += 1
            print("  -> 画像を追加")
    print(f"完了: {updated}/{len(notes)} 件に画像を追加")
    return 0


if __name__ == "__main__":
    sys.exit(main())
