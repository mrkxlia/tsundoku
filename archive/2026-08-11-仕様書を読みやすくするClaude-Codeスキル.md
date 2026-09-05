---
url: https://zenn.dev/spacemarket/articles/6c4992227d0b0d
created: '2026-08-11T20:15:40'
type: article
tags:
- claudecode
- ai
- ドキュメント
- プログラミング
summary: '仕様書やスペック文書を人間が読みやすいHTMLレポートに変換するClaude Codeスキル「spec-to-readable-html」の紹介記事。

  Markdownの代わりにHTMLを使用することで、サマリー、目次、Mermaid図などを視覚的にリッチに表現できるのが特徴。

  プロンプト設計やテンプレート活用の工夫、トレーサビリティ確保のポイントなどが解説されている。'
title: スペック文書を「読みたくなるHTML」に変換するClaude Codeスキルを作った話（スキル本文付き）
read: false
shelf_life: medium
published_at: '2026-05-28'
---

# スペック文書を「読みたくなるHTML」に変換するClaude Codeスキルを作った話（スキル本文付き）
2026-08-11
こんにちは！スペースマーケットの jin です🐶

今回は、仕様書やスペック文書を人間が読みやすいHTMLレポートに変換するClaude Codeスキル「 **spec-to-readable-html** 」を作った話を書きます。

作った動機、設計で考えたこと、実際に使ってみた結果などをまとめたので、Claude Codeスキルの開発に興味がある方の参考になれば嬉しいです。

![個人プロジェクトをHTML化したもの1](https://static.zenn.studio/user-upload/c35247dcfb34-20260526.png)

![個人プロジェクトをHTML化したもの2](https://static.zenn.studio/user-upload/53364c6a6cc5-20260526.png)

▲ 今回作成したスキルを使って個人プロジェクトをHTML化したサンプルの一部です

## きっかけ：「The Unreasonable Effectiveness of HTML」

ことの始まりは、Anthropic の Claude Code エンジニアリングリードである Thariq Shihipar さんの記事でした。

<iframe src="https://embed.zenn.studio/card#zenn-embedded__10e86bb62f148" frameborder="0"></iframe>

この記事の主張はシンプルです。 **AIの出力フォーマットとして、MarkdownよりHTMLの方が圧倒的にリッチな表現ができる** というもの。

- SVG図やインタラクティブウィジェットを埋め込める
- ページ内ナビゲーションで長文でも迷わない
- カラーコードや注釈など、情報設計の自由度が段違い

この記事を読んだとき、「スペック文書に使えるじゃん」と思いました。

## 課題：仕様書は書かれた瞬間から読まれなくなる

PRDやAPI仕様書、技術設計書といったドキュメントには、こんな課題がつきものです：

- **長い** 。背景説明、要件、API仕様、非機能要件...全部読むのはつらい
- **構造が見えにくい** 。フラットなMarkdownだと、全体像を掴むのに時間がかかる
- **図がない（あっても見づらい）** 。テキストだけでシステム間の関係やワークフローを理解するのは認知負荷が高い
- **重要度がすぐにわからない** 。Must/Should/Couldが埋もれてしまう

## 解決策：Claude Codeスキルとして作る

HTMLレポートへの変換をClaude Codeのスキルとして実装しました。単純なMarkdown→HTML変換ではなく、 **内容を分析・再構成・要約し、視覚的な補助も自動で追加** するのがポイントです。

### 主な機能

| 機能 | 説明 |
| --- | --- |
| サマリー＋カード | 文書を数段落で要約し、数値的なハイライトをカードグリッドで表示 |
| 目次サイドバー | 見出しから自動生成。デスクトップではスティッキー表示、スクロール追従付き |
| Mermaidダイアグラム | 内容に応じてフローチャート、シーケンス図、ER図、ステート図などを自動生成。クリックで Pan & Zoom 拡大表示 |
| 用語集グリッド | ドメイン固有の概念やキーワードをカード形式で一覧化 |
| 構造化テーブル | 技術スタック、状態管理、テスト戦略など、文書の性質に合わせた表を自動構成 |
| バッジ | Must/Should/Could の優先度、Confirmed/Inferred のステータス、リスクレベルを色分け表示 |
| コールアウト | 制約事項や設計原則など、読者が見落としてはいけない情報を目立たせる |
| ツリービュー | ディレクトリ構成をファイル種別ごとに色分けして可視化 |
| ソーストレーサビリティ | 出力の各セクションが元文書のどこに対応するかを付録で明示 |

### 使い方

Claude Codeの中で、以下のコマンドで起動します：

```
/spec-to-readable-html @仕様書のパス
```

これだけで、仕様書を読み込み→分析→HTML生成までやってくれます。

以下は、個人プロジェクトのプロジェクト仕様書を変換した例です。

![個人プロジェクトをHTML化したもの3](https://static.zenn.studio/user-upload/2bee6ddb863b-20260526.png)

## スキルの設計：SKILL.mdというプロンプト設計

今回の `SKILL.md` は約180行。以下のような構成で設計しました：

### 1\. いつ使うか・使わないかを明確に

```
## When to Use This Skill
- Convert a specification, requirements document, design doc...
- Make a Markdown spec easier for humans to read
- Add summaries, diagrams, charts...

Do **not** treat the task as a literal Markdown-to-HTML conversion
unless the user explicitly asks for a faithful conversion.
```

このスキルが行うタスクの大前提を最初に伝えています。「変換」という言葉だけだと、性能の低いモデルほどMarkdownタグをHTMLタグに置き換えるだけの処理と解釈しがちですし、高性能なモデルでも文脈次第では単純変換に寄ることがあります。スキルの冒頭で「分析・再構成・要約を伴う変換である」という前提を明示することで、こうした誤解を防いでいます。

### 2\. 判断基準を与える

スキル内に「Visual Decision Guide」というテーブルを用意しました：

| ソースの内容 | 最適なビジュアル |
| --- | --- |
| ステップバイステップのプロセス | フローチャート |
| システム間のAPI呼び出し | シーケンス図 |
| エンティティと関係 | ER図 |
| ステータスのライフサイクル | ステート図 |

Claudeに「いつ何のダイアグラムを生成すべきか」の判断基準を与えることで、的確なビジュアルが自動で追加されるようになりました。

### 3\. テンプレートHTMLで品質を固定する

プロンプトだけだと、生成されるHTMLのスタイルが毎回ブレます。そこで、 `references/template.html` というテンプレートファイルを用意しました。

```
references/
├── template.html          # ベースHTMLテンプレート（CSS含む）
└── html-output-template.md  # コンポーネントガイド
```

テンプレートには社内デザインシステムに準拠したCSS変数を定義しています：

```
:root {
  --color-primary: #00a273;        /* Spacemarket green */
  --color-primary-dark: #008a62;
  --color-surface: #f5f8f7;
  --font-sans: 'Hiragino Kaku Gothic ProN', ...;
  --radius: 12px;
}
```

コンポーネントガイド（ `html-output-template.md` ）では、サマリーカード・バッジ・テーブル・コールアウト・ダイアグラムコンテナなど、各UIパーツの使い方をドキュメント化しています。

**テンプレート＋コンポーネントガイドの組み合わせ** がミソで、これによりCSSを丸ごとコピーしつつ、コンテンツだけをスペック文書から生成する、という安定した出力が得られます。

## 工夫したポイント

### トレーサビリティの確保

AIが文書を「要約」すると、元の意味が変わってしまうリスクがあります。そこで以下のルールを SKILL.md に組み込みました：

- 推測した内容には `Inferred` や `Assumption` のラベルを付ける
- 仕様上のキーワード（MUST, SHOULD, SHALL）はそのまま保持する
- APIパス、フィールド名、エラーコード、列挙値は原文のまま
- 曖昧な箇所は勝手に解釈せず「Open Questions」セクションに分離

これにより、「要約されてるけど、元のスペックのどこに書いてあるか追えない」という問題を防いでいます。

### Mermaidダイアグラムの拡大表示

![Mermaidダイアグラムの拡大表示](https://static.zenn.studio/user-upload/2247e26a2240-20260526.gif)

生成されるダイアグラムはクリックで拡大表示（Pan & Zoom対応）できるようにしました。複雑なフローチャートやER図は小さいと見づらいので、これは地味に重要です。

## おわりに

「The Unreasonable Effectiveness of HTML」に触発されて作ったこのスキルですが、本質的に解決しているのは **情報の表現形式を変えることで、同じ内容でも理解しやすくする** ということです。

仕様書の内容自体は変わらないのに、構造化・要約・可視化するだけで「読む気になる」というのは、情報設計の力を実感する体験でした。

Claude Codeのスキルシステムは、プロンプトとテンプレートだけでこうしたツールを作れるのが強みかなと思っております。社内の他の課題にも同じアプローチで展開できそうなので、引き続き試していきます。

この記事が Claude Code スキル開発の参考になれば幸いです。  
ご質問やフィードバックがあれば、ぜひコメントください！

---

2026.05.29 追記

## スキル本文はこちらです！

スキルを GitHub で公開しました！  
ご自身のニーズに合わせて自由にカスタマイズしてお使いください。

```
npx skills add KeMezz/spec-to-readable-html
```

<iframe src="https://embed.zenn.studio/card#zenn-embedded__76498fb4e3b43" frameborder="0"></iframe>
