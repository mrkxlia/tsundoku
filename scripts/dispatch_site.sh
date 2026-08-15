#!/usr/bin/env bash
# tsundoku-site への content-updated dispatch を「前回dispatch時から変更がある場合のみ」送る。
# organize.yml / backfill.yml の最後のステップから共通で呼び出される。
#
# 状態は embeddings-index Release の site-dispatch-state.json アセットに永続化する
# (embeddings.json と同様、Releaseアセットをクロスラン状態として利用):
#   vault_head:        前回dispatch直前に観測した origin/main 先頭SHA
#   embeddings_sha256: 前回dispatch時の index/embeddings.json の SHA-256
#
# 設計上の不変条件:
#  - 状態更新は dispatch 成功後のみ行う → dispatch失敗時は次回必ず再送される
#    (「前回実行から◯時間」のような時刻ヒューリスティックは使わない)
#  - 状態の取得/parse失敗はフェイルオープン(=dispatchする)。誤る方向は「余分なデプロイ」のみ
#  - SHAは dispatch 前に観測する → 起動されたdeploy側のcheckoutは必ず観測SHA以降を見るため、
#    取りこぼし(サイトに反映されない変更)は起こらない
#
# 必要な環境変数:
#   GITHUB_TOKEN      - Release操作(状態のダウンロード・アップロード)用。既定の github.token で足りる
#   SITE_DISPATCH_TOKEN - tsundoku-site への dispatch 用(PAT-B2 "site-dispatcher")
set -euo pipefail

REPO="mrkxlia/tsundoku"
SITE_REPO="mrkxlia/tsundoku-site"
STATE_ASSET="site-dispatch-state.json"
STATE_DIR=".dispatch-state"

CURRENT_HEAD="$(git ls-remote origin refs/heads/main | cut -f1)"
CURRENT_EMB="absent"
if [ -f index/embeddings.json ]; then
  # embeddings.json は再同期のたびに generatedAt(実行時刻)が書き換わるため、
  # ファイル全体をそのままハッシュすると内容が同じでも毎回値が変わってしまう。
  # 実質的な内容(notes等)のみを対象にハッシュする(jq -S でキー順も正規化)。
  CURRENT_EMB="$(jq -S 'del(.generatedAt)' index/embeddings.json | sha256sum | cut -d' ' -f1)"
fi

mkdir -p "$STATE_DIR"
PREV_HEAD=""
PREV_EMB=""
if GH_TOKEN="$GITHUB_TOKEN" gh release download embeddings-index \
     --repo "$REPO" --pattern "$STATE_ASSET" --dir "$STATE_DIR" --clobber 2>/dev/null; then
  PREV_HEAD="$(jq -r '.vault_head // empty' "$STATE_DIR/$STATE_ASSET" 2>/dev/null || true)"
  PREV_EMB="$(jq -r '.embeddings_sha256 // empty' "$STATE_DIR/$STATE_ASSET" 2>/dev/null || true)"
fi

if [ -n "$PREV_HEAD" ] && [ "$CURRENT_HEAD" = "$PREV_HEAD" ] && [ "$CURRENT_EMB" = "$PREV_EMB" ]; then
  echo "前回dispatch時から変更なし(HEAD=${CURRENT_HEAD:0:7}, embeddings=${CURRENT_EMB:0:12})。dispatchをスキップします"
  exit 0
fi

echo "変更を検知: HEAD ${PREV_HEAD:0:7} -> ${CURRENT_HEAD:0:7} / embeddings ${PREV_EMB:0:12} -> ${CURRENT_EMB:0:12}"
GH_TOKEN="$SITE_DISPATCH_TOKEN" gh api "repos/$SITE_REPO/dispatches" -f event_type=content-updated

jq -n --arg h "$CURRENT_HEAD" --arg e "$CURRENT_EMB" --arg t "$(date -u +%FT%TZ)" \
  '{vault_head: $h, embeddings_sha256: $e, dispatched_at: $t}' \
  > "$STATE_DIR/$STATE_ASSET"

if ! GH_TOKEN="$GITHUB_TOKEN" gh release view embeddings-index --repo "$REPO" >/dev/null 2>&1; then
  GH_TOKEN="$GITHUB_TOKEN" gh release create embeddings-index --repo "$REPO" \
    --title "embeddings-index" --notes "tsundoku-site 用の埋め込みindex・dispatch状態アセット(自動更新)"
fi
GH_TOKEN="$GITHUB_TOKEN" gh release upload embeddings-index "$STATE_DIR/$STATE_ASSET" \
  --repo "$REPO" --clobber

echo "dispatch送信・状態更新済み"
