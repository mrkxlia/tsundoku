---
url: https://x.com/u1/status/2073289543948923153?s=12&t=22GY_jUSQsg0NcuE2S9fmA
created: '2026-08-11T20:15:40'
type: post
tags:
- claude
- ai
- 開発効率
- プログラミング
summary: 'Claude Codeのcompact機能による会話履歴の要約は非可逆であり、指示とログの混同やセッション状態の喪失といった構造的事故を引き起こす。

  これに対する対策として、圧縮前状態を保存するskill、復旧用マーカーを使う2段階hook、60%通知による自動圧縮回避の仕組みを実装した。

  1M context環境と組み合わせることで、 compactを多用しても論理破綻が起きない安定したセッション運用が可能になる。'
title: claude codeのcompactの問題点と対策
read: false
shelf_life: medium
---

# claude codeのcompactの問題点と対策
2026-08-11
後日､以下の内容+αを自動で入れられて透過的にcompactを強化出来るプラグインを作りました｡

[https://x.com/u1/status/2073742408555343968](https://x.com/u1/status/2073742408555343968)

そもそも Claude Code の compact はどう動くか

話の前提として、Claude Code の compact は次の 2 経路で走る:

- **手動 compact** (/compact): user が明示的に叩く。任意のタイミングで発火できる。
- **自動 compact**: セッションの context 使用率が上限近く（実運用では概ね 90〜95% 近辺）に達すると、Claude Code 側の判断で自動的に走る。user が意図した瞬間に走るわけではなく、ターンの区切りで「気付いたら圧縮されていた」形になる。

どちらの経路でも中身は同じで、それまでの会話履歴を LLM に投げて自然文の要約を作らせ、要約 + 直近ターン + system prompt を新しい context として再構築する。要約は「何をやったか」の物語ベースの記述になり、「なぜその選択をしたか」「どの案を却下したか」「今どのフェーズか」といった判断構造は結果的に薄まる。しかも一度圧縮が走ると圧縮前の raw ログには戻れない、非可逆な操作である点も大きい。

hook から見ると、圧縮は PostCompact イベントで拾える。ただし PostCompact hook は additionalContext を返せない仕様で、圧縮直後のエージェントに指示を直接注入する経路がない。指示を差し込むには、次の UserPromptSubmit イベントを経由するしかない。この制約が本記事の hook 設計を規定している。

標準 compact の何がダメか

Claude Code の /compact は会話履歴を LLM に要約させる仕組みで、要約結果を新セッションの初期 context に据える。要約自体は妥当だが、要約は「過去の作業記録」であって「次に何をすべきか」という指示ではない。結果として、圧縮後のエージェントは次のような誤認識を起こしやすくなる:

- 「作業指示」と「作業ログ」の境界を失う。圧縮後の要約に「案 A を検討した」と残っていると、そこで採用された案 B ではなく案 A を実装し始める
- 検証フェーズと実装フェーズを混同する。「検証してからデプロイする」と決めていた前提が要約から落ち、次ターンでいきなりデプロイ相当の破壊的操作に入る
- 圧縮前に一度潰した誤ったアプローチを再提案する。要約は「試した」ことは残しても「なぜ却下したか」の根拠までは持ち帰らない
- plan mode / worker 委譲 / タスクツリーといった「セッション状態」を失う。plan mode を抜けた状態で作業を続行したり、tmux で並走中の worker の存在を忘れて自分で作業を始めたりする

実際にどんな事故が起きていたか

自分の直近 1 週間のセッションを見返すと、compact 直後に少なくとも次の 4 パターンが観測できた。いずれも「作業指示」と「作業ログ」の分離失敗という一つの根に見える:

- **検証前デプロイ**: 圧縮前に「実機で挙動を確認してから配置する」と合意していたのに、圧縮後は要約に残った完成イメージだけを見て検証をスキップし、配置先を上書きしていた
- **却下済みショートカットの再実行**: 圧縮前に一度失敗して撤回したショートカット的アプローチを、圧縮後の要約が「試みた手順」として残しているため、そのまま再実行して同じ失敗を踏む
- **設計原則の失念**: 「配置先を直接編集せず、管理元の repository を編集して配布する」といったセッション中に確立した原則が要約から抜け落ち、圧縮後は配置先を直接触るという「短期的には動くが再現できない」変更を行う
- **タスク目的の取り違え**: 圧縮前に固定していたテストの目的（例: sandbox 外実行時の承認判断の検証）が要約から抜け、圧縮後は関連する周辺調査に脱線し、最終的にタスクとは別ラインの作業まで開始する

これらは同一セッション内で複数回発生し、compact のたびに種類の違う誤認識が起きていた。単発の偶発事故ではなく、標準 compact の仕様に対して構造的に発生する失敗と見ている。

作ったもの

## (1) compact-prep skill

「/compact を打つ前に user が明示的に叩く」slash command として実装した skill。現セッションから、圧縮の要約に載りきらないであろう「判断構造」と「セッション状態」だけを抜き出して、固定パスの state file (${TMPDIR}/claude-compact-state/<session\_id>.md) に決められたフォーマットで保存する。

保存する項目は次のとおり。要約に載りにくい情報を優先している:

- Active Plan（plan file のパスと現在フェーズ）
- TaskList Summary（in-progress タスクと補足）
- Session Decisions（採用した案 / 却下した案 / 却下した理由）
- Constraints and Blockers
- Worker Topology（tmux-bridge の pane / role / 担当）
- Editing Files（未保存・未検証の注意点）
- Recovery Notes（圧縮後の自分への手紙）

設計の勘所は「機械的に強制する」こと。session\_id が取れなければ推測名で file を作らせない Hard gate、見出し順を固定して書き終わった後に読み返して欠落を検知する Forcing function、副作用を絞る allowed-tools の 3 つで、「書いたつもり」のまま state が壊れる経路を潰している。実物は末尾に置く。

## (2) PostCompact + UserPromptSubmit の 2 段 hook

(1) で state file を書いても、圧縮後のエージェントがそれを読まなければ意味がない。ここが厄介で、Claude Code の PostCompact hook は additionalContext を返せない仕様なので、圧縮直後のエージェントに指示を直接注入する経路がない。

そこで 2 段構成にする:

PostCompact hook が session\_id で marker file を書く（指示は入れない、圧縮が起きたことだけ記録する）

次の UserPromptSubmit hook が marker を検出したら、additionalContext で「plan file を Read しろ / state file を Read しろ / TaskList を確認しろ / 圧縮サマリーの next step は仮説として扱え / plan mode が解除されていたら再突入を確認せよ」を注入し、marker を消す（one-shot）

hook 間で state を共有する共通機構が Claude Code にはないので、file system 上の marker が唯一の通信路になる。それぞれの hook は「単一の責務 + marker の読み書き」だけ持つ、非常に薄い分業。圧縮していない通常のターンでは UserPromptSubmit hook は test -f 1 回で即 exit するので実質コスト 0。全体を fail-open (常に exit 0) にしているので、hook が壊れても Claude Code 本体は止まらない。

これで圧縮直後の 1 ターン目から「自分は plan の Phase 3 の途中で、worker A に X を委譲済み」という状態に戻る。実物は末尾に置く。

## (3) 60% 通知（自動 compact を回避するため）

ここまでの (1) skill + (2) 2 段 hook は「手動 /compact の前後に何かする」設計で、user 自身が /compact-prep → /compact の順で叩くことが前提になっている。ところが Claude Code の自動 compact は宣言なしに走るので、この経路が使えない。自動 compact に先を越されると、state file が保存されないまま raw ログが要約に潰され、以降の復旧材料がなくなる。

対策は「自動 compact が走る前に、user 自身が手動で /compact-prep → /compact を叩ける状態を作る」こと。これが 60% 通知の目的。

なぜ 60% か

- **自動 compact 発火点から十分手前を取る**: 自動 compact は概ね 90〜95% 近辺で発火する。通知が発火点に近すぎると、user がその発話ターンで気付いても、次の作業ターンで自動 compact が先に走る可能性が残る。安全側に振って 30% 分のマージンを確保している。
- **区切りまで作業を進める余裕を残す**: 60% で通知が来た時点でまだ 30% 分の作業余力がある。中途半端な状態で即 /compact に飛ばず、区切りの良いところまで進めてから state file を書ける。
- **区切りが「主観」ではなく「タイマー」で来る**: 集中して作業していると context 消費に気付かない。60% で機械的に割り込む forcing function として、hook が能動的に指示を注入する。
- **副次効果**: 60% 時点で「今どのフェーズにいるか / 何を残しているか」を棚卸しさせられるので、区切りの判断そのものにも効く。

1M context 前提であること

60% で「まだ十分作業できる」状態を成立させるには絶対 token 量が要る。標準の 200K context だと 60% は 120K token で、通知が来た時点で残枠が少なすぎて即 compact しかない。自分は Opus 4.7 (4.6 ではなく 4.7) の 1M context を有効にして使っており、60% = 約 600K token 分の余裕がある。ここまで枠があると、通知を受けてから区切りまで作業を続けても余裕を持って /compact-prep → /compact に持ち込める。60% という数字は 1M context 前提でこそ意味を持つ設定で、200K context のままだと 80% 台まで閾値を上げないと窮屈になる。

実装の分業

実装は 2 パーツ。既存の statusline hook（毎ターンの statusline 更新時に context 使用率を計算している）に閾値超過で warn marker を書く分岐を足し、UserPromptSubmit hook 側で warn marker を検出したら「/compact-prep を提案せよ」を注入する。使用中の marker は 3 種類:

- claude-compact-warn: 「これから通知したい」warn marker。statusline が書き、UserPromptSubmit hook が読んで消す
- claude-compact-warned: 「もう通知済み」cooldown marker。UserPromptSubmit hook が書き、PostCompact hook が消す。これで二重通知を防ぐ
- claude-compacted: (2) で紹介した「圧縮直後」marker。PostCompact hook が書き、UserPromptSubmit hook (recovery 側) が読んで消す

statusline は「使用率」しか知らず、UserPromptSubmit hook は「通知するかどうか」しか知らず、PostCompact hook は「圧縮が起きたか」しか知らない。それぞれの責務が単一で、状態は marker の存在有無だけで表現されている。実物は末尾の [参考 C](https://file+.vscode-resource.vscode-cdn.net/Users/u1/agent/tmp/claude-sessions/3066d3e4-d8ab-433f-9660-f67b2d3cd259/x-article.md#c-60-%E9%80%9A%E7%9F%A5) に置く。

user 側の見た目としては、60% を超えたターンで Claude が自然文で「context 使用率が上がってきたので、区切りが良いところで /compact-prep → /compact を実行することをお勧めします」と提案してくるようになる。「勝手に自動 compact が走って迷走する」パターンが構造的に減る。

効果

1セッションで10回ぐらいcompactしても特に論理破綻が起きないぐらいには安定したので当初期待していた効果は達成されてるはず !

- 圧縮起因の作業ロスがほぼゼロ
- 却下案の再提案が消えた
- plan mode の維持ができるようになった
- tmux で複数 worker を動かしてる時の topology 忘却がなくなった

参考: 実装コード

以下は本文で触れた skill / hook の実体。そのままコピペで動く。配置先は Claude Code の標準 (~/.claude/) 前提。

A: compact-prep skill 本文

~/.claude/skills/compact-prep/SKILL.md に置く。

```markdown
---
name: compact-prep
description: |
  Claude Code の /compact 実行前に、現セッションの作業状態を一時 state file へ保存する。
  MANDATORY TRIGGERS: /compact-prep, compact-prep, 圧縮準備, compact 準備, コンパクト準備, 圧縮前状態保存。
  DO NOT TRIGGER: compact 後の復旧、通常の進捗報告、plan 作成、context 使用率の雑談。
strict_procedure: true
argument-hint: "[復旧メモ]"
allowed-tools: Read Write Bash(~/.claude/scripts/get-session-id.sh *) Bash(mkdir *) Bash(date *) Bash(pwd)
---

# compact-prep

Claude Code の \`/compact\` 前に、圧縮サマリーへ残りにくい作業状態を
\`${TMPDIR}/claude-compact-state/${SESSION_ID}.md\` へ保存する。

## Strict procedure profile

- Strictness: strict-procedure。圧縮前 state file の内容と保存完了報告が成果そのもの。
- Hard gates: session_id が取得できない場合は state file を推測名で作らず、取得不能として停止する。
- Forcing function: 保存先パスを固定し、保存後にファイルを読み返して必須項目の有無を確認する。
- Completion receipt: state file パス、保存した主要項目、未確認項目、次に実行する \`/compact\` 案内を報告する。

## 手順

1. session_id を取得する。
   - \`~/.claude/scripts/get-session-id.sh\` を実行する。
   - 取得できない場合は state file を作らず、session_id が取得できないため準備未完了と報告する。
2. 保存先を \`${TMPDIR:-/tmp}/claude-compact-state/${SESSION_ID}.md\` に決める。
3. TaskList、active plan file、tmux-bridge 状態、編集中ファイルを確認する。
   - active plan file は \`~/.claude/plans/\` 配下の該当ファイルを読む。
   - tmux-bridge を使っていない場合は「未使用」と記録する。
4. state file に以下の見出しをこの順で保存する。
   - \`# Compact Prep State\`
   - \`## Active Plan\`
   - \`## Current Phase\`
   - \`## TaskList Summary\`
   - \`## Session Decisions\`
   - \`## Constraints and Blockers\`
   - \`## Worker Topology\`
   - \`## Editing Files\`
   - \`## Recovery Notes\`
5. 保存後に state file を読み直し、上記見出しがすべて存在することを確認する。
6. ユーザーに「準備完了。\`/compact\` を実行してください。」と伝える。

## 保存内容

- active plan file パスと、現在のフェーズ/ステップ
- in-progress タスク一覧と補足
- session 中の判断、ユーザーの選択、不採用にした案の理由
- 制約、ブロッカー、未完了の検証
- worker 体制。tmux-bridge 使用時は pane、role、担当を記録する
- 編集中のファイルと、未保存または未検証の注意点
- 圧縮後の自分への復旧メモ

## Completion receipt

完了時は次を含める。

- state file パス
- 保存した主要項目
- 未確認項目と理由
- \`準備完了。/compact を実行してください。\`
```

B: 圧縮直後の復旧 hook (2 段)

## B-1: PostCompact hook

~/.claude/hooks/compaction-recovery.sh:

```bash
#!/bin/bash
# PostCompact hook (matcher: ""): 圧縮発生を marker file で記録する。
# PostCompact は additionalContext 出力をサポートしないため、
# context 注入は UserPromptSubmit 側 (userpromptsubmit-compaction-recovery.sh) で行う。
#
# fail-open (常に exit 0)

set -uo pipefail

INPUT=$(cat)
SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[[ -z "$SESSION_ID" ]] && exit 0

# marker file を書く（UserPromptSubmit が検出して context 注入→削除する）
MARKER_DIR="${TMPDIR:-/tmp}/claude-compacted"
mkdir -p "$MARKER_DIR" 2>/dev/null || true
printf '%s\n' "$(date +%s)" > "$MARKER_DIR/$SESSION_ID" 2>/dev/null || true

# compact が実行されたら 60% 警告の cooldown をリセットする
WARN_DIR="${TMPDIR:-/tmp}/claude-compact-warned"
rm -f "$WARN_DIR/$SESSION_ID" 2>/dev/null || true

exit 0
```

## B-2: UserPromptSubmit hook (復旧指示注入)

~/.claude/hooks/userpromptsubmit-compaction-recovery.sh:

```bash
#!/bin/bash
# UserPromptSubmit hook: PostCompact が残した marker file を検出し、
# additionalContext で圧縮復旧指示を context に注入する（one-shot）。
#
# overhead: test -f 1 回/ターン（marker なければ即 exit）
# fail-open (常に exit 0)

set -uo pipefail

INPUT=$(cat)
SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[[ -z "$SESSION_ID" ]] && exit 0

# marker file がなければ何もしない
MARKER_DIR="${TMPDIR:-/tmp}/claude-compacted"
MARKER="$MARKER_DIR/$SESSION_ID"
[[ -f "$MARKER" ]] || exit 0

# marker を消す（one-shot: 次ターンでは発火しない）
rm -f "$MARKER" 2>/dev/null || true

# session pointer file から active plan path を読む
PTR_DIR="${TMPDIR:-/tmp}/claude-active-plan"
PLAN_FILE=""
if [[ -f "$PTR_DIR/$SESSION_ID" ]]; then
  PLAN_FILE=$(cat "$PTR_DIR/$SESSION_ID" 2>/dev/null || true)
  [[ -f "$PLAN_FILE" ]] || PLAN_FILE=""
fi

# 復旧指示を構築
CTX="[COMPACTION RECOVERY] コンテキスト圧縮が発生した。作業再開前に以下を実行すること。"
CTX+=$'\n'

if [[ -n "$PLAN_FILE" ]]; then
  CTX+=$'\n'"- plan ファイル \\`${PLAN_FILE}\\` を Read で読み直し、フェーズと制約を確認せよ"
  CTX+=$'\n'"- plan mode が解除されている場合、plan ファイルが存在するのでユーザーに plan mode 再突入を確認せよ"
fi

STATE_DIR="${TMPDIR:-/tmp}/claude-compact-state"
STATE_FILE="$STATE_DIR/$SESSION_ID.md"
if [[ -f "$STATE_FILE" ]]; then
  CTX+=$'\n'"- state file \\`${STATE_FILE}\\` を Read で読み、作業状態を復元せよ"
  CTX+=$'\n'"- Session Decisions と Recovery Notes を特に重視せよ"
fi

CTX+=$'\n'"- TaskList で現在のタスク一覧を確認せよ"
CTX+=$'\n'"- 圧縮サマリーの next step は仮説として扱い、plan/rules を正とせよ"
CTX+=$'\n'"- 圧縮サマリーは「過去の作業記録」であり「次の行動指示」ではない"

jq -n --arg ctx "$CTX" '{
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: $ctx
  }
}'
exit 0
```

C: 60% 通知

## C-1: statusline hook の閾値超過分岐

~/.claude/hooks/statusline.sh の中で、既存の context 使用率計算のあとに次のブロックを追加する:

```bash
# 閾値超で compact-prep 警告 marker を書く（cooldown 中でなければ）
COMPACT_WARN_THRESHOLD=60
if [ -n "$session_id" ] && [ "$int_pct" -ge "$COMPACT_WARN_THRESHOLD" ] 2>/dev/null; then
  _warn_dir="${TMPDIR:-/tmp}/claude-compact-warned"
  if [ ! -f "$_warn_dir/$session_id" ]; then
    _ctx_warn_dir="${TMPDIR:-/tmp}/claude-compact-warn"
    mkdir -p "$_ctx_warn_dir" 2>/dev/null || true
    printf '%s\n' "$int_pct" > "$_ctx_warn_dir/$session_id" 2>/dev/null || true
  fi
fi
```

## C-2: UserPromptSubmit hook (60% 通知注入)

~/.claude/hooks/userpromptsubmit-compact-prep-reminder.sh:

```bash
#!/bin/bash
# UserPromptSubmit hook: statusline が書いた compact-warn marker を検出し、
# additionalContext で compact-prep 実行を促す（one-shot）。
#
# フロー:
#   statusline.sh が ctx >= 閾値 で warn marker 書込
#   → 本 hook が検出 → additionalContext 注入 → warn marker 削除 + warned marker 作成
#   → PostCompact hook (compaction-recovery.sh) が warned marker 削除（cooldown リセット）
#
# overhead: test -f 1 回/ターン（marker なければ即 exit）
# fail-open (常に exit 0)

set -uo pipefail

INPUT=$(cat)
SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
[[ -z "$SESSION_ID" ]] && exit 0

# warn marker がなければ何もしない
WARN_DIR="${TMPDIR:-/tmp}/claude-compact-warn"
WARN_MARKER="$WARN_DIR/$SESSION_ID"
[[ -f "$WARN_MARKER" ]] || exit 0

# marker から使用率を読み取る
CTX_PCT=$(cat "$WARN_MARKER" 2>/dev/null)
CTX_PCT=${CTX_PCT:-"?"}

# warn marker を消す（one-shot）
rm -f "$WARN_MARKER" 2>/dev/null || true

# cooldown marker を作成（statusline が再度 warn marker を書くのを防止）
WARNED_DIR="${TMPDIR:-/tmp}/claude-compact-warned"
mkdir -p "$WARNED_DIR" 2>/dev/null || true
printf '%s\n' "$(date +%s)" > "$WARNED_DIR/$SESSION_ID" 2>/dev/null || true

CTX="[COMPACT PREP REMINDER] context 使用率が ${CTX_PCT}% に達した。"
CTX+=$'\n'"- 作業区切りでユーザーに \\`/compact-prep\\` の実行を提案せよ。"
CTX+=$'\n'"- \\`/compact-prep\\` 実行後、ユーザーに \\`/compact\\` 実行を案内せよ。"
CTX+=$'\n'"- scope 縮小や別セッション化ではなく、圧縮前 state 保存で対処せよ。"

jq -n --arg ctx "$CTX" '{
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: $ctx
  }
}'
exit 0
```

D: settings.json の hook 登録

~/.claude/settings.json に以下を追加する（既存の hook 設定に足す形）:

```json
{
  "hooks": {
    "PostCompact": [
      { "matcher": "", "hooks": [{ "type": "command", "command": "~/.claude/hooks/compaction-recovery.sh" }] }
    ],
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command", "command": "~/.claude/hooks/userpromptsubmit-compaction-recovery.sh" }] },
      { "hooks": [{ "type": "command", "command": "~/.claude/hooks/userpromptsubmit-compact-prep-reminder.sh" }] }
    ]
  }
}
```
