---
title: Claude Codeに同じ指摘をさせないhookの仕組み
url: https://zenn.dev/nozomi720/articles/claude_code_hooks_feedback
created: '2026-08-15T19:16:42'
type: article
tags:
- claudecode
- ai
- hook
- 開発効率化
- python
summary: 'Claude Codeでの同じ指摘の繰り返しを防ぐため、指摘内容をファイルに記録・管理する仕組みを構築。

  指摘回数に応じてhookの強制力を3段階で引き上げ、コマンド実行やファイル編集の制限を行う。

  読ませる・やらせない・終わらせないの3段階hookでAIの行動を自動的に制御している。'
read: false
shelf_life: medium
---

# Claude Code に「同じ指摘を二度させない」仕組みを hook で作った
2026-08-15
## 同じ指摘を、何度も繰り返している

Claude Code を使っていて一番消耗するのは、実装の質そのものより **「先週も言ったことを今日も言っている」** ことでした。

- 「テストを先に書いて」
- 「テストは hook が自動実行するから Bash で手動実行しないで」
- 「GitHub Actions の `uses:` は SHA でピン留めして」

`CLAUDE.md` に書いても、セッションが長くなると効き目が薄れます。そもそも「何回言ったか」がどこにも残らないので、こちらも「これ前に言ったっけ？」と分からなくなる。

そこで、 **指摘そのものをファイルとして永続化し、指摘回数（ `count` ）に応じて hook の強制力を段階的に上げる** 仕組みを作りました。現在 `~/.claude/feedback/` には 47 個のルールが溜まっていて、そのうち 14 個は hook が機械的に検知できる形になっています。

| count | ルール数 |
| --- | --- |
| 1 | 31 |
| 2 | 4 |
| 3 | 5 |
| 4 | 2 |
| 5 | 2 |
| 6 | 3 |

## 1指摘 = 1ファイル

ルールは `~/.claude/feedback/<topic>.md` に1つずつ置きます。実際に運用している `tdd.md` はこうなっています。

```
---
name: tdd
description: 実装前にテストを書くTDDアプローチを必ず取ること
type: feedback
count: 6
enforce:
  - event: pre_edit
    path: '**/*.go'
    absent_sibling: '{stem}_test.go'
    message: 'TDD: 実装ファイルを書く前にテストファイル(Red)を先に書くこと。'
    severity: ask
  - event: pre_edit
    path: '**/*.ts'
    absent_sibling: '{stem}.test.ts'
    message: 'TDD: 実装ファイルを書く前にテストファイル(Red)を先に書くこと。'
    severity: ask
---

実装を始める前に必ずテストを先に書くこと。テストなしで実装を進めてはいけない。

**Why:** ユーザーはTDDを要求しており、テストなしの実装は受け入れられない。

**How to apply:** 新しい機能・パッケージを作成するときはもちろん、リファクタリング
時も必ずテストファイルを先に書いてからプロダクションコードを書く。
```

ポイントは frontmatter です。

- `count` … 同じ指摘を受けた回数。 **強制力の強さそのもの**
- `enforce` … hook が機械的に検知するための条件（後述）
- 本文 … Claude が読む用の説明

### 「言い訳」を書かせる

本文には `**Why:**` （なぜ指摘されたか）と `**How to apply:**` （いつ適用するか）に加えて、 `**言い訳:**` というセクションを書くルールにしています。

```
**言い訳:** 「大量のファイルを一括変更したから壊れていないか自分の目で確認したい」
というのは正当な理由に思えるが、それこそがこのルールが繰り返し指摘されている理由
そのもの。変更の規模が大きいほど「今回は特別」と例外扱いしたくなるが、hook は変更
規模に関わらず同じように結果を返してくれる。
```

これが地味に効きます。ルールを破りたくなる場面では、たいてい「今回は特別だから」という理屈が先に立つ。その理屈を **あらかじめ潰した文章** が同じファイルに書いてあると、逃げ道が塞がれます。

ルール同士は `[[hook_errors_are_yours]]` のように Obsidian 風のリンクで繋いでいます。

## count に応じて強制力を上げる

すべてのルールをいきなり `deny` （ツール実行を禁止）にすると事故ります。1回目の指摘は状況依存かもしれないし、正規表現の誤検知でツールが止まると作業不能になる。

なので `count` から severity を自動決定します。

```
def resolve_severity(count, explicit=None, event=None):
    """ルールに severity の明示があればそれを使い、無ければ count から決める。"""
    if explicit:
        return explicit
    if count >= 5:
        return "deny"
    if count >= 3:
        return "block" if event == "stop_check" else "ask"
    return "warn"
```

| count | pre\_bash / pre\_edit | stop\_check |
| --- | --- | --- |
| \>= 5 | `deny` | `deny` |
| 3〜4 | `ask` | `block` |
| 1〜2 | `warn` | `warn` |

- `warn` … stderr に出すだけ。処理は続行
- `ask` … ユーザーに確認を求める（Claude は勝手に進めない）
- `deny` / `block` … ツール呼び出しを止める

1〜2回目は「記録するが縛らない」暫定ルール。3回目で確定ルールになり、5回目で問答無用の禁止になります。 **指摘の重みは、指摘した回数という一番正直な指標で決まる** わけです。

なお、違反は `.violations.jsonl` に追記しますが、 **`count` は自動インクリメントしません** 。

```
def log_violation(rule, count, severity, event, detail):
    """~/.claude/feedback/.violations.jsonl に1行 JSON を追記する。
    count 自体は絶対に書き換えない（ログに残すのみ）。"""
```

hook が検知した違反は「Claude がルールを破ろうとした」だけであって、「人間がもう一度指摘した」わけではないからです。ルールの重みを上げる権限は人間側に残しておきます。

## 3つの hook で三段構えにする

`settings.json` でこう配線しています。

```
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [
        { "type": "command",
          "command": "python3 \"$HOME/.claude/hooks/feedback-inject.py\"" }
      ]}
    ],
    "PreToolUse": [
      { "matcher": "Bash|Edit|Write|MultiEdit",
        "hooks": [
          { "type": "command",
            "command": "python3 \"$HOME/.claude/hooks/feedback-guard.py\"" }
        ]}
    ],
    "Stop": [
      { "hooks": [
        { "type": "command",
          "command": "python3 \"$HOME/.claude/hooks/feedback-stop-check.py\"" }
      ]}
    ]
  }
}
```

| hook | イベント | 役割 |
| --- | --- | --- |
| `feedback-inject.py` | UserPromptSubmit | 確定ルールをコンテキストに注入する（ **読ませる** ） |
| `feedback-guard.py` | PreToolUse | 実行前に止める（ **やらせない** ） |
| `feedback-stop-check.py` | Stop | 直させる（ **終わらせない** ） |

<iframe src="https://embed.zenn.studio/mermaid#zenn-embedded__d126017954732" frameborder="0"></iframe>

### inject — 確定ルールを毎ターン読ませる

`count >= 3` のルールだけを count 降順に並べ、stdout に出します。UserPromptSubmit hook の stdout はそのままコンテキストに入ります。

```
rules = [r for r in fr.list_rules() if r["count"] >= 3]
```

出力例：

```
# 確定フィードバックルール（count >= 3）
これらは繰り返し指摘された確定ルール。違反すると hook がブロックする。

■ dont_run_tests_manually (これまで 6 回指摘されています)
テスト/lintはhookに任せ、言語問わずBashから手動実行しない
...
```

「これまで N 回指摘されています」と回数を明示するのが地味に大事で、AI に対して「これは重い」という重み付けを伝えられます。

問題はコンテキストの圧迫です。ルールが増えれば増えるほど毎ターン食い潰す。そこで **3000 文字の予算** を設け、超えたら count の低いものから本文を落として description だけにします。

```
def build_output(rules):
    ordered = sorted(rules, key=lambda r: (-r["count"], r["name"]))
    blocks = {r["name"]: format_full(r) for r in ordered}

    def assemble():
        return HEADER + "\n\n".join(blocks[r["name"]] for r in ordered)

    out = assemble()
    if len(out) <= LIMIT:
        return out

    # count の低いものから description のみに落とす
    for r in sorted(ordered, key=lambda r: (r["count"], r["name"])):
        blocks[r["name"]] = format_brief(r)
        out = assemble()
        if len(out) <= LIMIT:
            return out

    return out[:LIMIT]
```

重いルールほど詳しく残る、という優先度付き切り捨てです。

### guard — 実行前に止める

PreToolUse hook は JSON を返すことでツール実行を制御できます。

```
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,        # "deny" or "ask"
        "permissionDecisionReason": reason,
    }
}, ensure_ascii=False))
```

**Bash を止める例（ `pre_bash` ）**

「テストを手動実行しない」ルール（count 6 = `deny` ）はこうです。

```
enforce:
  - event: pre_bash
    when: '(^|&&|\|\||;)\s*(go +(test|vet|build)\b|rspec\b|rubocop\b|pytest\b|pnpm( +run)? +(test|lint)\b|bundle +exec +(rspec|rubocop)\b|git +stash\b)'
    message: 'テスト/lintはhookに任せ、Bashで手動実行しない。'
    severity: deny
```

`git stash` まで塞いでいるのがミソです。「自分の変更が原因かどうか調べたいので一旦 stash して既存テストを流す」という **もっともらしい検証手順** が、実際に3回繰り返されたので明示的に禁止しました。 `when` は正規表現、 `unless` で例外を、 `check` （シェルコマンド）で「非0終了なら違反確定」という条件も足せます。

**ファイル編集を止める例（ `pre_edit` ）**

TDD は「実装ファイルの隣にテストファイルが無ければ ask」で表現できます。

```
- event: pre_edit
  path: '**/*.go'
  absent_sibling: '{stem}_test.go'
  severity: ask
```

`{stem}` は拡張子を除いたファイル名に展開されます。 `foo.go` を書こうとしたとき `foo_test.go` が無ければ確認が入る。つまり **Red を書かせてから Green を書かせる** という順序をハーネス側で強制できます。

ただしこのままだと `foo_test.go` 自身を書くときに「 `foo_test_test.go` が無い」と言われて詰みます。なので除外します。

```
def _looks_like_test_file(basename):
    if re.search(r"_test\.go$", basename):
        return True
    if re.search(r"\.test\.tsx?$", basename):
        return True
    if re.search(r"_spec\.rb$", basename):
        return True
    if re.match(r"^test_.*\.py$", basename):
        return True
    return False
```

### stop-check — 直すまで終わらせない

Stop hook で **exit 2** を返すと、Claude は応答を終えられず作業を続行します。ここでは「そのセッションで変更したファイル」に対してシェルコマンドを走らせます。

GitHub Actions の SHA ピン留めルール（count 3）の例：

```
- event: stop_check
  changed: '.github/workflows/**'
  check: '! grep -qE "uses:[[:space:]]*[^[:space:]]+@(v[0-9]|main|master|latest)" "$FILE"'
  message: 'uses: にタグ/ブランチ参照が残っています。コミット SHA でピン留めすること。'
  severity: block
```

`$FILE` に変更ファイルの絶対パスが入るので、任意の grep / linter を書けます。「タグ参照が残っていたら終わらせない」という強制になります。

変更ファイルの一覧は、gate 側の hook が書く `changed_files.<session>.txt` を優先し、無ければ git にフォールバックします。

```
for args in (
    ["git", "diff", "--name-only", "HEAD"],
    ["git", "ls-files", "--others", "--exclude-standard"],
):
```

当然ながら、直せない場合に無限ループするのが怖いので打ち切りを入れています。

Stop hook の入力 JSON には `stop_hook_active` （前回の Stop hook がブロックして継続させた結果の Stop なら true）が入っており、公式にはこれを見てループを防ぐことが推奨されています。ただしフラグを見て即座に諦めると **1回もリトライできない** ので、ここでは自前のカウンタで回数を数えています（このフラグの使い道については、別記事のゲート側でもう少し踏み込みました）。

```
MAX_ATTEMPTS = 3

attempts = bump_attempts(ap)
if attempts >= MAX_ATTEMPTS:
    sys.stderr.write("3 回連続でブロックしました。ループを打ち切ります。手動確認を。\n")
    clear_attempts(ap)
    return 0
```

## hook 自身が事故らないための作法

一番大事な設計方針はこれです。

```
if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception as e:  # hook のバグで作業を止めない
        sys.stderr.write(f"[feedback-guard] internal error (ignored): {e}\n")
        sys.exit(0)
```

3つの hook すべてで例外を握り潰して exit 0 にしています。 **hook のバグでユーザーの作業が人質に取られるのが最悪のシナリオ** なので、検知できないことより止まらないことを優先します。

```
def load_yaml_text(text):
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        pass
    if which("yq"):
        r = subprocess.run(["yq", "-o=json", "."], input=text,
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return json.loads(r.stdout)
    return mini_yaml_load(text)
```

`mini_yaml_load()` は frontmatter のサブセット（マッピング、リスト、引用符付きスカラー）だけを扱う 70 行ほどの自前パーサです。glob マッチも `*` は `/` を跨がない・ `**` は跨ぐ・ `{a,b}` 展開という標準的な挙動を自前で実装しています。

hook 群には `hooks/tests/` に pytest を置いています。テスト時は環境変数でルール置き場を差し替えられるようにしました。

```
def feedback_dir():
    """~/.claude/feedback を返す。CLAUDE_FEEDBACK_DIR でテスト時に差し替え可能。"""
    override = os.environ.get("CLAUDE_FEEDBACK_DIR")
    if override:
        return override
    ...
```

## 運用してみて

**効いたもの**

- `dont_run_tests_manually` （count 6 / deny）… 物理的に手が出せないので確実。「hook の結果を待つ」以外の選択肢が消える
- `tdd` （ask）… 止めるのではなく一拍置かせるのが良く、正当な理由があれば通せる

**効きにくいもの**

`enforce` を書けないルールは inject 頼みになります。たとえば「実装を先に書いてから呼び出し元を書く」という **順序** のルールは、ファイル単体を見ても違反判定ができません。47 個中 14 個しか `enforce` を持てていないのはそのためです。

**誤検知の逃がし方**

正規表現ベースなので当然誤爆します。逃がし方を3つ用意しています。

1. `unless:` に例外パターンを書く
2. `severity:` を明示して count による自動昇格を止める
3. `_looks_like_test_file()` のようなコード側の除外

**次にやりたいこと**

- `.violations.jsonl` の集計。どのルールが実際に何回発火したかを見れば、形骸化しているルールを捨てられる
- 発火頻度から count の更新を提案させる（更新の実行はあくまで人間が判断する）

## まとめ

- AI に「お願い」しても守られない。 **ハーネス側で強制する**
- 指摘は口頭ではなくファイルにする。ファイルになれば `count` で重み付けでき、コードから評価できる
- いきなり禁止せず `warn → ask → deny` と段階を踏む。誤検知で作業不能になるほうが害が大きい
- hook 自身は絶対に事故らせない（例外は握り潰して exit 0）

同じ hook 基盤を使って「テストが通るまでターンを終わらせない」ゲートも作っています。そちらは別記事に書きます。
