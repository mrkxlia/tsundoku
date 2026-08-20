# 定期再検証(reverification)の設計と実装状況

**Stage⑤ 実装済み**(`scripts/reverify.py` + `.github/workflows/reverify.yml`)。
以下は元の設計メモをベースに、実装内容を反映して更新したもの。`scripts/organize.py` の
`reverify_hook(note)` は設計どおりno-opのまま維持している(下記「`reverify_hook(note)`」参照)。
未着手なのは「実装時の変更点」チェックリストのうち tsundoku-site側の表示のみ。

## 課題

クリップ時点では正しかった情報が、時間経過で古くなる・誤りが判明する場合がある
(価格・仕様・組織名の変更、後継サービスへの移行、記事自体の削除など)。
`shelf_life`(Stage④)は「情報がどのくらいの期間で陳腐化しやすいか」という**事前の目安**を
記録するのに対し、reverification は「実際に内容がまだ正しいか」を**事後に確認**する仕組みで、
両者は補完関係にある。

## 仕組み(実装済み)

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

## frontmatter予約フィールド(実装済み)

| フィールド | 内容 |
|---|---|
| `last_verified` | 最後に再検証した日時(ISO8601、UTC offset付き)。未設定 = 一度も再検証されていない |
| `needs-recheck` | `tags`内の1タグとして付与。再検証で疑義が見つかったノート。`status`は変えない |
| `recheck_reason` | `needs-recheck`付与時の判定理由(日本語1文、200字まで、改行なしの単一行) |

`last_verified`/`recheck_reason`は既存の`fm_edit.py`(単一フィールドの行レベル編集)、
`needs-recheck`は新設の`fm_edit.append_tag`/`remove_tag`で書き込む。

## 注意点

- **Google Search グラウンディングの無料枠**は他のGemini機能とは別枠で、変動しやすい
  (実装時に [AI Studio](https://aistudio.google.com/rate-limit) で最新のレート制限を確認すること)。
- **グラウンディングの無料枠はモデル世代ごとに別枠**であり、通常の生成呼び出し(`LLM_MODEL_CHAIN`)
  が使えているモデルでもグラウンディングは枠0のことがある。実際、このアカウントでは2026-08-18時点で
  Gemini 3系のグラウンディング枠が0/0(利用不可)、Gemini 2.5系は0/1.5K(日1,500件が未使用)だった。
  これは通常の生成クォータとは無関係のため、モデルが生成呼び出しで動いていることは
  グラウンディングが動く根拠にならない。**必ずAI Studioのレート制限ページで対象モデルの
  「検索によるグラウンディング」欄を個別に確認すること**。この理由から`verify_currency`は
  `LLM_MODEL_CHAIN`とは別に`GROUNDING_MODEL_CHAIN`(既定Gemini 2.5系)を持つ設計にしている
  (`llm_client.GeminiClient.grounding_model_chain`)。
- 無料枠を消費するため、`organize.yml`の日次実行に直接組み込むのではなく、
  `backfill.yml`同様の手動/低頻度スケジュール実行(例: 週1)を想定する。
- 再検証の判定はハルシネーションのリスクを伴うため、`status`を自動変更する設計にはしない
  (上記の通り`needs-recheck`タグ止まり)。

## 実装時の変更点(チェックリスト)

- [x] `scripts/reverify.py` 新規作成(対象選定・Google Search グラウンディング呼び出し・
      `last_verified`/`needs-recheck`の`fm_edit`書き込み)
- [x] `llm_client.py` に Google Search グラウンディング対応メソッド(`verify_currency`)を追加
- [x] `.github/workflows/reverify.yml` 新規作成(手動実行、`organize-inbox`
      concurrencyグループに参加)
- [x] `scripts/organize.py` の `reverify_hook(note)` はno-opのまま据え置き(対象選定を
      `last_verified`/`created`の経過日数で行うため、クリップ時点での初期値書き込みは不要と判断)
- [ ] tsundoku-site側: `needs-recheck`タグの表示(任意。RAGの`isSupersededOrExpired`判定には
      含めない方針 — 人間のレビュー前に検索結果から機械的に除外しないため)。未着手

## 実装内容の要点

- 対象選定: `shelf_life` short(30日)/medium(180日)経過、`--all`でlong(経過日数を問わず)も対象
- TPM超過対策: `LLM_SLEEP_SECONDS`を30秒に引き上げ、429は同一モデルで60秒×2回リトライしてから
  次モデルへ(`llm_client.VERIFY_MAX_RETRIES`/`VERIFY_RETRY_SLEEP_SECONDS`)
- グラウンディング専用モデルチェーン: `verify_currency`は`GROUNDING_MODEL_CHAIN`
  (既定`gemini-2.5-flash`)を使う。通常の`LLM_MODEL_CHAIN`(Gemini 3系)とは無関係
  (上記「注意点」参照)。`gemini-2.5-flash-lite`は新規アカウントでは廃止済み(404)のため
  含めていない
- 信頼性対策(2026-08-18、15件バッチの実地検証で33%失敗した経験から追加):
  - グラウンディングは検索を伴い通常の生成より時間がかかるため、タイムアウトを90秒から
    150秒(`VERIFY_TIMEOUT_SECONDS`)に延長
  - ネットワーク層のタイムアウト・接続エラー(`URLError`/`TimeoutError`)も429と同様に
    同一モデルで再試行するよう`_call_model_raw`を拡張(全呼び出し元に効く一般的な改善)
  - 応答がJSON形式の指示に従わない場合、同一モデルで最大1回まで再試行
    (`VERIFY_PARSE_RETRIES`)。グラウンディングは出力形式が不安定になることがあるため
- 初回運用ノート: 無料枠は変動するため、初回実行は`max_items`を10〜15程度に絞って実測してから
  40〜50件のバッチへ広げる(README「運用」参照)

## 検証観点(実装時に確認済み)

- `reverify_hook`が呼ばれても`organize.py`の既存の挙動(整理結果・frontmatter)が変化しないこと
- 再検証で誤って`status`が書き換わらないこと(`needs-recheck`タグのみ付与されること)
- 同じ入力で2回連続実行した場合、2回目は完全にスキップされること(レジューム)
