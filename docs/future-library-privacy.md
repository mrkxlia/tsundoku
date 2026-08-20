# 将来検討: library/ 本文のpublic公開範囲の見直し(著作権観点)

このドキュメントは**提案(起案)のみ**であり、実装は含まない。2026-08-16の統合作業(短小・
高類似ノートのマージ)中にユーザーから「統合したデータはprivateリポジトリにあったほうが
良いか」という質問を受けたことがきっかけで、より広い論点として整理した。

## 課題

`library/` の各ノート本文は、`type` によらず**クリップ元のWebページ本文がほぼ生のまま**
frontmatterの下に保存される(`organize.py` の `parse_clip()` → `media_types.enrich()` は
`article` typeの場合、取得した本文に一切加工を加えず素通しする。Geminiによる要約は
`summary` frontmatterフィールドとして別に生成されるだけで、本文そのものを短縮・言い換え
してはいない)。

2026-08-16時点の実測(161ノート):

| type | 件数 | 平均本文長 |
|---|---|---|
| article | 64 | 約15,500字 |
| slides | 19 | 約29,700字(OCR書き起こし・スライドテキスト含む) |
| post | 72 | 約2,500字 |
| pdf | 1 | 約389,600字 |

つまり `article` type だけで平均15,000字超、要約ではなく元記事相当の分量のテキストが、
**public repository である `mrkxlia/tsundoku` に平文でコミットされ続けている**。

一方、画像・PDF等のバイナリ実体については、2026-08-16に「著作物再配布回避」を理由として
private側(`mrkxlia/tsundoku-site` の `vault-assets/`)へ既に移管済み(tsundoku-site PR #5、
本リポジトリのPR #14・#15・#16)。**テキスト本文にはまだ同じ判断が適用されていない**、
という非対称な状態にある。

## 現状の事実確認(2026-08-16時点)

- `tsundoku`(このVault)は**public**。理由はコスト: GitHub ActionsはpublicリポジトリではLinux
  runnerの分数が無料無制限、privateリポジトリでは無料枠(個人アカウントの場合月2,000分、
  プラン次第)を超えると課金される
- 直近の `organize.yml` 実行時間の実測: 平均約352秒/回(日次実行)、backlogが多い日は
  1,500秒超に達することもある。過去には `backfill_shelf_life.py` の一括実行で2時間超かかった
  実績もある
- ざっくり試算: 日次実行だけなら 352秒 × 30日 ≈ 176分/月。仮に月数回バックフィルを実行しても、
  個人アカウントの無料枠(月2,000分)には収まりそうな水準ではあるが、正確な現在のプラン・
  実際の月間消費分数は未確認
- `tsundoku-site`(閲覧サイトのリポジトリ)は既に**private**。かつ実際にデプロイされたサイト
  自体もCloudflare Access(認証必須)でゲートされているため、「本文を人間が読める経路」は
  現状でもエンドツーエンドで非公開。**publicに露出しているのは、あくまで `tsundoku` の
  GitHubリポジトリを直接ブラウズ/cloneした場合の生ファイルのみ**
- `library/` 本文は `build_embeddings.py` がチャンク化してGemini埋め込みを生成し、tsundoku-site
  の `/api/ask`(RAG検索)がベクトル検索に使う。本文を大幅に削る場合、検索精度への影響を
  考慮する必要がある

## 選択肢

### A. 現状維持

- 変更なし。運用コストゼロ。RAG検索の精度に影響なし
- リスク: `tsundoku` リポジトリを直接ブラウズ/cloneすれば誰でも記事本文(≒元記事相当の分量)
  を読める状態が続く

### B. `tsundoku` リポジトリ自体をprivateにする

- 最もシンプル。Vault全体(バイナリは既にvault-assets/へ移管済みなので、実質テキストのみ)
  が非公開になり、露出面が消える
- コスト: GitHub Actionsの無料分数上限に達した場合は課金対象になる(上記試算では収まりそうだが
  未確認)。iPhoneのObsidian Git同期は、書き込み権限のあるPATであれば引き続き動作するはずだが
  実機での動作確認が必要
- tsundoku-site側の `deploy.yml` は現在 `tsundoku` をpublicとして無認証でcheckoutしている
  想定(要確認)。private化する場合は `vault-assets` checkout同様のトークン設定が必要になる
  可能性がある

### C. 本文の実体をvault-assetsと同じ方式でprivate側へ分離(推奨)

画像・PDFで既に確立した「実体はprivate側、参照だけpublic側」というパターンをテキスト本文にも
適用する。

- `library/` のpublicノートは frontmatter(title/url/tags/summary/shelf_life等、いずれも
  短く・LLMによる要約や分類であり著作物性の観点でリスクが低い)のみを保持し、本文は
  「## 本文」的なプレースホルダ+`tsundoku-site` 側の私有ストレージへのポインタ程度に留める
- 元本文の実体は `tsundoku-site`(既にprivate)へ、`vault-assets/` と並ぶ新設ディレクトリ
  (例: `vault-bodies/`)として書き出す。書き込み経路は既存の `SITE_CONTENT_TOKEN` 送信ロジック
  (`organize.py` のアセット同期処理)を流用できる
- `build_embeddings.py` は埋め込み生成時のみ `vault-bodies/` をsparse-checkoutして本文を読む
  (embeddingsタスクが既に `vault-assets/` をsparse-checkoutしている処理と同型)。RAG検索精度は
  変わらない
- `tsundoku-site` のQuartzビルド(`sync-content.sh`)も同様に `vault-bodies/` から本文をオーバーレイ
  する必要がある(サイト自体は既にCloudflare Accessでゲートされているため、閲覧体験は現状維持)
- コスト: GitHub Actions分数は変わらない(`tsundoku` はpublicのまま)。実装コストが3案中最大
  (vault-assets移管と同規模の変更が両リポジトリに必要、初回移行時は既存161ノートの本文の
  一括移送も要る)

## 推奨

**選択肢C**を推奨する。理由:

1. vault-assetsで既に確立した設計パターンをそのまま踏襲でき、一貫性がある
2. GitHub Actionsの無料枠(publicリポジトリの恩恵)を失わない
3. RAG検索・サイト閲覧体験のどちらにも実質的な影響を与えずに、著作権上のリスクだけを
   下げられる

ただし選択肢Bの方が実装コストは大幅に低いため、**まず選択肢Bを試して実際のActions消費分数を
計測し、無料枠に収まりそうなら選択肢Bで十分**、収まらない/他の理由でpublicを維持したいなら
選択肢Cへ、という段階的な進め方も現実的。

## 実装時の変更点チェックリスト(選択肢C採用時、現時点では未着手)

- [ ] `tsundoku-site` に `vault-bodies/`(`vault-assets/` 同様 `.gitignore` 対象の作業ディレクトリ
      ではなく、コミット対象のprivateストレージ)を新設
- [ ] `organize.py`: 新規ノート作成時、本文実体を `vault-bodies/<note-stem>.md` へ書き出し、
      `library/` 側のnote bodyはプレースホルダ(または既存の3行summaryのみ)にする
- [ ] 既存161ノート(2026-08-16時点)の本文を一括で `vault-bodies/` へ移行するバックフィル
      スクリプトを用意(vault-assetsのバイナリ移管時に使った手順・注意点を参考にする)
- [ ] `build_embeddings.py`: `vault-bodies/` のsparse-checkoutと本文読み込みに対応
- [ ] `tsundoku-site` の `sync-content.sh`: `vault-bodies/` から本文をオーバーレイしてQuartz
      ビルドに渡す処理を追加
- [ ] `detect_superseded.py` / `merge_notes.py` など、本文(chunk化された全文)を前提にしている
      既存スクリプトが `vault-bodies/` を参照できるよう更新
- [ ] 移行後、`tsundoku` のgit履歴に残った旧本文をどう扱うか検討(vault-assetsの時と同様に
      `git-filter-repo` での履歴書き換えが必要になる可能性が高い。書き換え前バックアップ・
      モバイル端末の再clone対応も必要)

## 未確認事項(着手前に確認すべきこと)

- 現在のGitHubアカウントのプラン(Free/Pro等)と、privateリポジトリのActions無料分数の正確な上限
- `tsundoku-site` の `deploy.yml` が `tsundoku` をpublicとして無認証checckoutしているか
  (private化した場合の対応要否)
- iPhoneのObsidian Gitが、privateリポジトリに対しても現状のPAT設定のまま問題なく動作するか
  (実機での動作確認が必要)

**Why**: 画像・PDF実体は既にprivate化済みだが、本文テキストは同じ論点が未検討のまま残って
いた。統合作業でこの非対称性に気づいたのを機に、今後の判断材料として整理した。
**How to apply**: このドキュメントは提案のみで実装を促すものではない。着手する場合は
まず「未確認事項」を解消し、選択肢B(privateリポジトリ化)を試して実際のActions消費を
計測してから、選択肢Cへ進むかどうかを判断する。
