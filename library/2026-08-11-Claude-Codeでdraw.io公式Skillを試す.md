---
url: https://dev.classmethod.jp/articles/claude-code-trying-out-drawio-skill-for-aws-architecture/
created: '2026-08-11T21:35:08'
type: article
tags:
- claudecode
- aws
- drawio
- 生成ai
summary: 'draw.io公式のClaude Code向けSkillを導入し、AWSアーキテクチャ図の自動生成を検証した記事。

  初期状態ではモノクロアイコンや色ズレなどの課題があったが、スタイルルールをSKILL.mdに追記することで解決した。

  AWS 2026のアイコンスタイルやグループコンテナの定義など、実践的なガイドラインがまとめられている。'
title: Claude Code × draw.io公式Skillで、AWSアーキテクチャ図の生成を自動化してみた
read: false
shelf_life: medium
published_at: ''
---

# Claude Code × draw.io公式Skillで、AWSアーキテクチャ図の生成を自動化してみた
2026-08-11
## はじめに

フローチャートやアーキテクチャ図をWEB上で描くとき、多くの方は手動で作成しているのではないでしょうか。2026年4月現在、AI Agentに作業を任せる流れが加速していますが、作図系のWEBアプリはAI連携（MCPなど）にまだ制限が多いのが現状です。

そんな中、 **draw.io（jgraph）公式がClaude Code向けのSkillを公開している** ことを知り、試してみました。  
（draw.ioにはMCPサーバー版もあるが、Skill 版は外部プロセス不要でセットアップがシンプル。今回はSkill 版を使った。）

- draw.io skill-cli: [https://github.com/jgraph/drawio-mcp/tree/main/skill-cli](https://github.com/jgraph/drawio-mcp/tree/main/skill-cli)

自分のVSCode/CursorにはDraw.IOのプラグインを入れているので、今までも「drawioで図を書いて」と指示すればClaude Codeは書き方を調べて`.drawio` ファイルを生成してくれていました。ただ、複雑な図を求めると品質が下がりがちでした。公式Skillを導入すれば、draw.ioのXMLフォーマットやスタイルの知識がClaude Codeに組み込まれるので、より高品質な図が生成できるはずです。

本記事では、公式Skillのセットアップからaws構成図の生成、そしてぶつかった問題と解決策をハンズオン形式でまとめます。

## 検証環境

- macOS
- Cursor
- Claude Code（Opus 4.6）
- Draw.io Desktop

## draw.io Skill とは

Claude Codeの **Skill** は、特定のタスクに対する専門知識をMarkdownファイルとして定義し、Claude Codeに読み込ませる仕組みです。MCPサーバーのような外部プロセスではなく、プロンプトの拡張として動作します。

draw.io公式Skillには以下のような知識が含まれています。

- `.drawio` ファイル（mxGraphModel XML）の正しい構造
- exportコマンド（PNG/SVG/PDF、XMLを埋め込んで再編集可能）
- styleプロパティの詳細（接続点、フォント、レイアウト等）
- 2層rendering（edgeをアイコンの背面に描画するテクニック）

つまり、Skillなしだと Claude Code が都度調べながら書いていたdraw.ioのXML知識が、Skill導入で最初から正確に使えるようになります。

また、Draw.io Desktopがインストールされていれば、図の生成後に **自動でDraw.io Desktopアプリが開き** 、生成された図をすぐにプレビュー・編集できます。生成→確認→修正指示のサイクルがスムーズに回せるのは地味に便利です。

## Skillのインストール

### 前提

- Claude Codeがインストール済みであること
- Draw.io Desktop がインストール済みであること（export機能を使う場合）

### 手順

1. プロジェクトフォルダー配下に `.claude/skills/` フォルダーを作成する
2. [draw.io公式リポジトリ](https://github.com/jgraph/drawio-mcp/tree/main/skill-cli) から `drawio` フォルダーをダウンロードし、`.claude/skills/` 配下に配置する

![2](https://devio2024-media.developers.io/image/upload/f_auto/q_auto/v1775799718/2026/04/10/s3qbxwmnks8bmc0hglkb.png)

```
your-project/
└── .claude/
    └── skills/
        └── drawio/
            └── SKILL.md
```

> グローバルにSkillを適用したい場合は、 `~/.claude/skills/` に配置してください。

配置できたら、Claude Codeで `/drawio` コマンドが認識されるようになります。

![1](https://devio2024-media.developers.io/image/upload/f_auto/q_auto/v1776054171/2026/04/13/mhgkbotoinadekm6puhf.png)

## 検証：AWS構成図を生成してみる

### シンプルな構成図を指示してみる

まずはシンプルなプロンプトで試してみます。

```
/drawio 簡単なAWS上サーバレスのWEBアプリ構成図サンプルを作ってもらえますか？
```

結果、構成図は生成されましたが、 **モノクロのアイコン** で出力されました。AWSらしいカラフルなアイコンではありません。

![3](https://devio2024-media.developers.io/image/upload/f_auto/q_auto/v1775799722/2026/04/10/txik8wusieuwji7c2jvi.png)

### カラーアイコンへの変更を指示

```
/drawio モノクロのアイコンしか入ってないですが、AWS 2026の色がついているアイコンで置き換えてもらえますか？
```

![4](https://devio2024-media.developers.io/image/upload/f_auto/q_auto/v1775799726/2026/04/10/bxniiqlwry9gwfzw6j2t.png)

色付きのアイコンに更新されましたが、よく見るとアイコンの線が黒色になっていたり、色味がずれていたりと、まだ問題がありました。さらに大きな構成図を試すと、ラベルがアイコンに被る、接続線がアイコンの上に描画される、VPCやサブネットの境界がないなど、複数の問題が出てきました。

### ぶつかった問題まとめ

| 問題 | 原因 | 解決策 |
| --- | --- | --- |
| アイコンの線が黒い | `strokeColor` が未指定でデフォルトの黒になる | `strokeColor=#ffffff` を明示 |
| カテゴリカラーがずれる | 古いカラーコードを使っている | draw.ioソースコード（ [Sidebar-AWS4.js](https://github.com/jgraph/drawio/blob/dev/src/main/webapp/js/diagramly/sidebar/Sidebar-AWS4.js) ）から正しい値を取得 |
| ラベルがアイコンに被る | デフォルトではラベルがアイコン内部に配置される | `verticalLabelPosition=bottom` で下に配置 |
| 接続線がアイコンの上に描画 | mxGraphの仕様で、同一レイヤーではedgeが常にvertexの上に描画される | `edge_layer` と `shape_layer` の2層構成にする |
| VPC等の境界がない | グループ分けをしていない | `mxgraph.aws4.group` shapeでAWS group containerを定義 |

これらを一つずつ解決し、最終的にSKILL.mdにAWSアーキテクチャ図向けのガイドラインとして追記しました。

#### カテゴリカラーの解決例

![5](https://devio2024-media.developers.io/image/upload/f_auto/q_auto/v1775799734/2026/04/10/bjdpha4jf3pho7fjl5nq.png)

## SKILL.mdに追加したAWSガイドライン

公式Skillはdraw.ioの汎用的な知識をカバーしていますが、AWSアイコン特有のstyleルールまでは含まれていません。そこで、以下のガイドラインをSKILL.mdに追記しました。

そのまま自分のSKILL.mdにコピーして、必要に応じてカスタマイズしてください。

SKILL.mdに追記したAWS icon styling全文

```markdown
## AWS icon styling (AWS 2026)

When generating AWS architecture diagrams, always use the **AWS 2026** icon style from draw.io's \`mxgraph.aws4\` namespace.

### Base style template

Every AWS icon must use this base style:

\`\`\`
sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=<CATEGORY_COLOR>;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.<service_name>;
\`\`\`

Critical properties:
- **\`strokeColor=#ffffff\`** — draws the icon graphic lines in white. Never use \`none\` or other values.
- **\`fillColor\`** — set per service category (see table below)
- **\`verticalLabelPosition=bottom;verticalAlign=top\`** — places the label below the icon to avoid overlap
- **\`sketch=0\`** — disables hand-drawn style
- **\`points=[[...]]\`** — connection points for edges

### AWS group containers

For enterprise-scale diagrams, use AWS group shapes to visually separate environments (e.g., inside AWS vs external, VPC boundaries, regions). Icons inside a group must use \`parent="<group_id>"\` and positions are relative to the group's origin.

| Group | grIcon | strokeColor | Usage |
|-------|--------|-------------|-------|
| AWS Cloud | \`mxgraph.aws4.group_aws_cloud_alt\` | \`#232F3E\` | Top-level AWS boundary |
| Region | \`mxgraph.aws4.group_region\` | \`#00A4A6\` | AWS region |
| VPC | \`mxgraph.aws4.group_vpc2\` | \`#8C4FFF\` | Virtual private cloud |
| Public Subnet | \`mxgraph.aws4.group_security_group\` | \`#7AA116\` | Public subnet |
| Private Subnet | \`mxgraph.aws4.group_security_group\` | \`#147EBA\` | Private subnet |
| Availability Zone | \`mxgraph.aws4.group_availability_zone\` | \`#232F3E\` | AZ boundary |

**Base group style template:**

\`\`\`
points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;shape=mxgraph.aws4.group;grIcon=<GROUP_ICON>;strokeColor=<STROKE_COLOR>;fillColor=none;verticalAlign=top;align=left;spacingLeft=30;fontColor=#232F3E;dashed=0;
\`\`\`

**Example — AWS Cloud group with children:**

\`\`\`xml
<mxCell id="aws_cloud" value="AWS Cloud" style="points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=0;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_aws_cloud_alt;strokeColor=#232F3E;fillColor=none;verticalAlign=top;align=left;spacingLeft=30;fontColor=#232F3E;dashed=0;" vertex="1" parent="1">
  <mxGeometry x="150" y="50" width="900" height="600" as="geometry" />
</mxCell>
<mxCell id="lambda" style="...resIcon=mxgraph.aws4.lambda;..." value="Lambda" vertex="1" parent="aws_cloud">
  <mxGeometry x="100" y="200" width="60" height="60" as="geometry" />
</mxCell>
\`\`\`

Key rules:
- Child cells use \`parent="<group_id>"\` — their x/y coordinates are relative to the group's top-left corner
- Place external elements (users, third-party services) **outside** the AWS Cloud group with \`parent="1"\`
- Size the group container large enough to fit all children with padding (at least 40px on each side)

### Category color table

| Category | fillColor | Example services |
|----------|-----------|-----------------|
| Compute | \`#ED7100\` | Lambda, EC2, ECS, Fargate, Batch |
| Containers | \`#ED7100\` | ECS, EKS, ECR |
| Network & Content Delivery | \`#8C4FFF\` | CloudFront, VPC, Route 53, ELB, API Gateway (NW) |
| Analytics | \`#8C4FFF\` | Athena, Kinesis, Redshift, EMR, QuickSight |
| Storage | \`#7AA116\` | S3, EBS, EFS, Glacier, Storage Gateway |
| IoT | \`#7AA116\` | IoT Core, Greengrass |
| Database | \`#C925D1\` | DynamoDB, RDS, Aurora, ElastiCache, Neptune |
| Developer Tools | \`#C925D1\` | CodeBuild, CodePipeline, CodeDeploy |
| Security, Identity & Compliance | \`#DD344C\` | Cognito, IAM, WAF, Shield, KMS |
| Front-End Web & Mobile | \`#DD344C\` | Amplify |
| Application Integration | \`#E7157B\` | API Gateway, SQS, SNS, Step Functions, EventBridge |
| Management & Governance | \`#E7157B\` | CloudWatch, CloudFormation, CloudTrail, Systems Manager |
| AI/ML | \`#01A88D\` | SageMaker, Bedrock, Rekognition, Comprehend |
| Migration & Modernization | \`#01A88D\` | DMS, Migration Hub |
| General Resources | \`#1E262E\` | Users, AWS Cloud, Internet, Generic resource |

### Example

\`\`\`xml
<mxCell id="10" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#7AA116;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;" value="Amazon S3" vertex="1" parent="1">
  <mxGeometry x="100" y="100" width="60" height="60" as="geometry" />
</mxCell>
\`\`\`
```

## 既知の制限

Claude Codeは生成した図のレンダリング結果を見ることができないため、edgeラベルの座標はsource/targetの位置から計算で求めています。シンプルな図では問題ありませんが、複雑な図ではラベル位置の手動調整が必要な場合があります。

とはいえ、ゼロから手動で描くのと比べれば、AIに大枠を生成してもらい微調整するだけで済むのは大幅な時間短縮です。

## おわりに

draw.io公式Skillを使うことで、Claude Codeによる図の生成品質が格段に上がりました。

![6](https://devio2024-media.developers.io/image/upload/f_auto/q_auto/v1775800158/2026/04/10/hp5lftc7mhjqimw57izq.png)

ただし、AWSアイコンのstyleルールは公式Skillだけではカバーしきれないので、SKILL.mdにガイドラインを追記する必要があります。

SKILL.mdはMarkdownファイルなのでカスタマイズは簡単です。本記事のガイドラインをベースにして、自分のプロジェクトに合った形に調整してみてください。
