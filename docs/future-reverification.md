# 将来拡張: 定期再検証(reverification)の設計

このドキュメントは**設計メモのみ**であり、実装は含まない(Stage⑤)。ここに書かれた仕様は
`scripts/organize.py` の `reverify_hook(note)` (no-opスタブ)と、frontmatterの予約フィールド
`last_verified` / タグ `needs-recheck` の運用方針を、実装に着手する際の起点として残す。

## 課題

クリップ時点では正しかった情報が、時間経過で古くなる・誤りが判明する場合がある
(価格・仕様・組織名の変更、後継サービスへの移行、記事自体の削除など)。
`shelf_life`(Stage④)は「情報がどのくらいの期間で陳腐化しやすいか」という**事前の目安**を
記録するのに対し、reverification は「実際に内容がまだ正しいか」を**事後に確認**する仕組みで、
両者は補完関係にある。

## 想定する仕組み(未実装)

1. **対象選定**: `shelf_life` が `short`/`medium` かつ `last_verified`(または無ければ`created`)
   から一定期間(例: shortは30日、mediumは180日)経過したノートを対象に、既存ノートの母数が
   増えても1回の実行で舐め切らずに済むよう上位N件ずつ処理する(`build_embeddings.py`の
   `--max-embeds`と同様、レジューム前提の設計を踏襲する)。
2. **再検証**: 対象ノートのタイトル・URL・要約をもとに、Gemini API の **Google Search
   グラウンディング**機能(Web検索結果を根拠にした生成)を使い、「記載内容は現在も正しいか」
   「後継・更新版の情報が存在するか」を判定する。
3. **判定結果の反映**:
   - 内容に問題なし → `last_verified` を現在日時で更新するのみ(`status`は変更しない)
   - 古い/誤りの疑いあり → **`status`を直接変更せず**、`needs-recheck` タグを付与するに留める。
     supersession判定(Stage④の`detect_superseded.py`)のような自動`status: superseded`化は
     行わない。理由: Web検索ベースの再検証はハルシネーションや誤判定のリスクが
     `detect_superseded.py`(既存ノート同士の直接比較)より高いと考えられるため、
     最終判断は人間のレビューを介在させる(`needs-recheck`タグが付いたノートを
     定期的に見直す運用を想定)。
4. **`reverify_hook(note)`**: `organize.py`が新規/更新ノートを1件処理し終えるたびに呼ばれる
   予約フック(現状no-op)。将来実装する場合、ここで`last_verified`の初期値(`created`と同じ)を
   書き込む、あるいは何もしない(初期値は再検証ワークフロー側で「未設定=要検証」として
   扱う)のいずれかを選択できる。この関数自体を拡張する形にすることで、呼び出し漏れを防ぐ。

## frontmatter予約フィールド

| フィールド | 状態 | 内容 |
|---|---|---|
| `last_verified` | 未実装・予約のみ | 最後に再検証した日時(ISO形式)。未設定 = 一度も再検証されていない |
| `needs-recheck` | 未実装・予約のみ(`tags`内の1タグとして運用想定) | 再検証で疑義が見つかったノート。`status`は変えない |

既存の`fm_edit.py`(単一フィールドの行レベル編集)がそのまま流用できる設計(`last_verified`は
単純な文字列スカラー値のため)。

## 注意点

- **Google Search グラウンディングの無料枠**は他のGemini機能とは別枠で、変動しやすい
  (実装時に [AI Studio](https://aistudio.google.com/) で最新のレート制限を確認すること)。
- 無料枠を消費するため、`organize.yml`の日次実行に直接組み込むのではなく、
  `backfill.yml`同様の手動/低頻度スケジュール実行(例: 週1)を想定する。
- 再検証の判定はハルシネーションのリスクを伴うため、`status`を自動変更する設計にはしない
  (上記の通り`needs-recheck`タグ止まり)。

## 実装時の変更点(着手時のチェックリスト、現時点では未着手)

- [ ] `scripts/reverify.py` 新規作成(対象選定・Google Search グラウンディング呼び出し・
      `last_verified`/`needs-recheck`の`fm_edit`書き込み)
- [ ] `llm_client.py` に Google Search グラウンディング対応メソッドを追加
- [ ] `.github/workflows/reverify.yml` 新規作成(手動実行 or 低頻度cron、`organize-inbox`
      concurrencyグループに参加)
- [ ] `scripts/organize.py` の `reverify_hook(note)` を実装(no-opから置き換え)
- [ ] tsundoku-site側: `needs-recheck`タグの表示(任意。RAGの`isSupersededOrExpired`判定には
      含めない方針 — 人間のレビュー前に検索結果から機械的に除外しないため)

## 検証観点(実装時)

- `reverify_hook`が呼ばれても`organize.py`の既存の挙動(整理結果・frontmatter)が変化しないこと
- 再検証で誤って`status`が書き換わらないこと(`needs-recheck`タグのみ付与されること)
