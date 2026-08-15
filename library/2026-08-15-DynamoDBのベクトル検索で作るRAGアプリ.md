---
title: DynamoDBのベクトル検索で作るRAGアプリ
url: https://zenn.dev/tosuri13/articles/567f25a4f3e9b5
created: '2026-08-15T19:16:42'
type: article
tags:
- aws
- dynamodb
- rag
- ベクトル検索
- python
summary: 'DynamoDBでリアルタイムベクトル検索機能が一般提供され、単体でRAGが構築可能になりました。

  ベクトルインデックスの設定項目やAWS SDKを用いたインデックス作成、データ投入の具体的な手順を解説しています。

  既存のテーブルにも後からインデックスを追加できるため、手軽にRAG機能を統合できます。'
read: false
shelf_life: medium
---

# DynamoDBのベクトル検索で簡単にRAGができるようになったぞ！
2026-08-15
こんにちは👋

2026年8月5日、AWSから **DynamoDBのリアルタイムベクトル検索** が一般提供(GA)されました。

<iframe src="https://embed.zenn.studio/card#zenn-embedded__b35930cb48f6c" frameborder="0"></iframe>

元々、DynamoDBのデータを活用してRAGアプリケーションを作成する場合は、ベクトル検索の機能を別のサービスに外出しして、メタデータのID(PK)などで紐づける二重管理の構成が必要でしたが、今回のアップデートで **DynamoDBのみでベクトル検索ができる** ようになりました！

これは非常に素晴らしいアップデートで、よりシームレスにDynamoDBを活用したRAGアプリケーションを構築できるようになりました。また、DynamoDBをベースとしたアプリケーションを既に運用されている場合でも、後から簡単にベクトル検索機能を統合できるようになっています。

今回は、DynamoDBでのベクトル検索機能について触れながら、AIエージェント(Strands Agents)へのRAG機能の導入まで試してみたいと思います。

## 今回作るもの

過去に作った「 [**メイドインアビス**](https://ja.wikipedia.org/wiki/%E3%83%A1%E3%82%A4%E3%83%89%E3%82%A4%E3%83%B3%E3%82%A2%E3%83%93%E3%82%B9) 」の内容について検索できるRAGシステムをそのままDynamoDBに移植してみようと思います。S3 Vectors版の方も面白いので読んでみてね(宣伝)。

<iframe src="https://embed.zenn.studio/card#zenn-embedded__c9b9651501e6f" frameborder="0"></iframe>

Wikipediaの内容をチャンキングしてDynamoDBに突っ込み、今回発表されたベクトル検索機能を用いて取得したコンテキストを元に回答を生成させる感じです。今回は **Strands Agents** でAIエージェント化して、ローカルから対話できるところまでやってみようと思います。

今回使用する技術スタックをまとめるとこんな感じです。

| 役割 | 使うもの |
| --- | --- |
| ベクトルストア | Amazon DynamoDB (Vector Index) |
| 埋め込みモデル | Amazon Bedrock (Amazon Titan Text Embeddings V2) |
| テキスト生成モデル | DeepSeek 3.2 |
| エージェントフレームワーク | Strands Agents |
| IaC | AWS CDK (Python) |

## DynamoDBテーブルを用意する

まず気になるのは「 **ベクトル検索を使うテーブルには何か特別な設定が必要なのか?**」という部分ですよね。

DynamoDBのベクトル検索は、テーブルに「 **ベクトルインデックス** 」と呼ばれるインデックスを追加するだけで利用することができます。テーブル作成時に「ベクトル用の何か」を有効化する必要はありませんし、既に本番で動いているテーブルにも後から足すことができます。

というわけで、CDKで書くテーブル定義は本当にただのテーブルです(そのうち、GSIのようにCDK上で定義できるようになると思いますが、現状CFnにも定義されてなさそうなので一旦スキップ)。

```
dynamodb.Table(
    self,
    "MIADDocumentsTable",
    table_name="miad-documents-table",
    partition_key=dynamodb.Attribute(
        name="document_id",
        type=dynamodb.AttributeType.NUMBER,
    ),
    billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
)
```

テーブルのPKはチャンクの通し番号(`document_id`)にしました。

ただし、ベクトルインデックスは `PAY_PER_REQUEST` (オンデマンドキャパシティ)のテーブルでしか作成することができません。プロビジョンドキャパシティのテーブルでは作成できないため、その点だけ注意する必要があります。

## ベクトルインデックスを作成する

マネジメントコンソールで作成したテーブルを開くと、「インデックス」タブの中にGSIと並んで **ベクトルインデックス** の項目が増えています。

![](https://static.zenn.studio/user-upload/b63918257ec0-20260806.png)

「ベクトルインデックスを作成」から、既存のテーブルにベクトルインデックスを追加することができます。初見だと分かりづらい設定項目もあるので、一つずつ項目を確認していきましょう。

![](https://static.zenn.studio/user-upload/64f84824b4dc-20260806.png)

### VectorAttribute

検索対象となる **ベクトルが入っている属性の名前** です。DynamoDBのアイテムの中で、数値のリストを持っている属性を指定します。

属性に含まれる値のイメージ

```
[ { "N" : "0.038366105407476425" }, { "N" : "0.09332295507192612" }, { "N" : "0.025404581800103188" }, ...]
```

つまり、埋め込みモデルなどで作成したベクトルを、 **あらかじめ全てのアイテムに属性として追加する必要がある** ということです。ベクトルインデックスを作成すると、自動的に埋め込みが作成されるとかではないので注意が必要です。

### Dimensions

ベクトルの **次元数** です。 **最大4,096次元** まで対応しています。

埋め込みモデルでベクトルを生成する際に指定した次元数を、そのまま入力すれば大丈夫です。今回はAmazon Titan Text Embeddings V2のデフォルト次元数である1024を使用します。

### DistanceFunction

距離関数です。 `COSINE` / `EUCLIDEAN` / `DOT_PRODUCT` の3種類が選べます。

| 距離関数 | 説明 | 値域 | 評価 |
| --- | --- | --- | --- |
| `COSINE` | `1 − コサイン類似度` 。2つのベクトルのなす角を距離に変換する | 0 〜 2 | 小さいほど似ている（昇順で上位k件） |
| `EUCLIDEAN` | 各次元の差の二乗和の平方根。空間上の2点間の直線距離 | 0 〜 ∞ | 小さいほど似ている（昇順で上位k件） |
| `DOT_PRODUCT` | 各次元の積の総和。向きが揃うほど、また長いベクトルほど大きくなる | −∞ 〜 ∞ | 大きいほど似ている（降順で上位k件） |

今回は、値域が有限で扱いやすい `COSINE` を利用したいと思います。

### Projection

GSIと同じ概念で、 **テーブルからインデックスにどの属性をコピーしておくか** の設定です。

| ProjectionType | コピーされる属性 | 用途 |
| --- | --- | --- |
| `KEYS_ONLY` | キー属性 + ベクトル属性 + インラインフィルタ属性 | 検索でキーだけ取得し、本体は別途 `GetItem` する場合 |
| `INCLUDE` | `KEYS_ONLY` の属性 + 指定した非キー属性 | 必要な属性だけに絞ってコストを抑えたい場合 |
| `ALL` | ベーステーブルの全属性 | 検索結果だけで完結させたい場合 |

RAGの場合は、検索結果からテキスト本文や関連するメタデータを取得したいケースがほとんどだと思うので、属性が少なければ `ALL` 、書き込みコストなどに懸念がある場合は `INCLUDE` を指定するのが良いと思います。

### SearchSchema

今回は指定していませんが、ベクトルインデックスの設計をする上で重要な機能です。 `SearchSchema` には2種類の要素を定義することができます。

#### HASH (ルーティングキー)

- ベクトルインデックスを分割するための属性
- 検索時にこの値の指定が **必須** になる
- 属性を **1つだけ** 指定できる (複合キーとかはできない)
- 検索が特定のスコープに閉じるため、スループットを最適化することができる

#### INLINE\_FILTER (インラインフィルター属性)

- 取得対象となるアイテムをフィルターするための属性
- 検索時での指定は **任意**
- **最大18個まで** 属性を指定することが可能
- ただし、使える演算子は **等価のみ** で、範囲検索や部分検索などは使用できない

```
"SearchSchema": [
      {
          "AttributeName": "tenant_id", 
          "SearchSchemaElementType": "HASH"
      },
      {
          "AttributeName": "category",
          "SearchSchemaElementType": "INLINE_FILTER"
      }
]
```

### ベクトルインデックスをAWS SDK経由で作成する

この記事の執筆時点では、CFnに `VectorIndexes` のような定義がなさそうだったので、AWS SDK(boto3)経由で作りました。

テーブルに何もアイテムがない状態でベクトルインデックスを作成したのですが、ステータスが `ACTIVE` になるまで結構時間がかかったので注意です。

```
import boto3

dynamodb = boto3.client("dynamodb")
dynamodb.update_table(
    TableName="miad-documents-table",
    VectorIndexUpdates=[
        {
            "Create": {
                "IndexName": "miad-documents-vector-index",
                "VectorAttribute": {"AttributeName": "vector"},
                "Dimensions": 1024,
                "DistanceFunction": "COSINE",
                "Projection": {"ProjectionType": "ALL"},
            }
        }
    ],
)
```

## ベクトルインデックスにデータを投入する

まずは、RAGの検索対象となるコーパスから、チャンキング処理 + ベクトル化を適用したドキュメントを準備します。

[メイドインアビスのWiki](https://ja.wikipedia.org/wiki/%E3%83%A1%E3%82%A4%E3%83%89%E3%82%A4%E3%83%B3%E3%82%A2%E3%83%93%E3%82%B9) から抜いてきたHTMLをMarkdownに変換し、それをLangChainの `MarkdownTextSplitter` で適切な単位のチャンクに分割します。分割したチャンクをAmazon Bedrockの **Amazon Titan Text Embeddings V2** に渡して、1024次元のベクトルを生成しています。

また、今回はメタデータを引っ張ってこれることも検証したかったので、ついでに引用を表示するRAGで必要な `source_url` を入れています。

```
import json
from pathlib import Path

import boto3
from langchain_text_splitters import MarkdownTextSplitter

corpus = Path("assets/corpus.txt").read_text()
splitter = MarkdownTextSplitter(
    chunk_size=1024,
    chunk_overlap=256,
)

# NOTE: Wikiの後半部分は関連性が低いので省略する
chunks = splitter.split_text(corpus)[:35]

bedrock = boto3.client("bedrock-runtime")
with Path("assets/documents.jsonl").open("w") as file:
    for index, chunk in enumerate(chunks):
        response = bedrock.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps(
                {
                    "inputText": chunk,
                    "dimensions": 1024,
                }
            ),
        )
        vector = json.loads(response["body"].read())["embedding"]

        document = {
            "document_id": index + 1,
            "text": chunk,
            "source_url": "https://ja.wikipedia.org/wiki/%E3%83%A1%E3%82%A4%E3%83%89%E3%82%A4%E3%83%B3%E3%82%A2%E3%83%93%E3%82%B9",
            "vector": vector,
        }
        file.write(json.dumps(document, ensure_ascii=False) + "\n")

        print(f"● {index + 1}/{len(chunks)} embedded")
```

出力された `documents.jsonl` はこんな形になりました。

```
{"document_id": 1, "text": "メイドインアビス...", "source_url": "https://ja.wikipedia.org/wiki/...", "vector": [0.0234, -0.0512, ...]}
```

DynamoDBの `PutItem` を使用して、ドキュメントをアイテムとしてテーブルに追加しています。先ほど作成したベクトルインデックスには、非同期でレプリケーションされていきます。この辺り意識しなくていいのは便利ですね。

```
import json
from pathlib import Path

import boto3

dynamodb = boto3.client("dynamodb")

documents = Path("assets/documents.jsonl").read_text()
for line in documents.splitlines():
    document = json.loads(line, parse_float=str)
    dynamodb.put_item(
        TableName="miad-documents-table",
        Item={
            "document_id": {"N": str(document["document_id"])},
            "text": {"S": document["text"]},
            "source_url": {"S": document["source_url"]},
            "vector": {"L": [{"N": value} for value in document["vector"]]},
        },
    )

    print(f"● {document['document_id']} added")
```

## ベクトルを検索する

ベクトルインデックスの検索には、 `SearchVectors` というAPIを使います。入力されたクエリも同じようにAmazon Titan Text Embeddings V2でベクトル化し、 `SearchVector` に渡します。

`TopK` で類似度の高いものから上位何件を取得するかを選ぶことができます。コンテキストがあまり膨らむとコスト的に困るので、今回は上位3件だけを取得することにします。

```
import json
import sys

import boto3

bedrock = boto3.client("bedrock-runtime")
dynamodb = boto3.client("dynamodb")

response = bedrock.invoke_model(
    modelId="amazon.titan-embed-text-v2:0",
    body=json.dumps({"inputText": sys.argv[1], "dimensions": 1024}),
)
embedding = json.loads(response["body"].read())["embedding"]

response = dynamodb.search_vectors(
    TableName="miad-documents-table",
    IndexName="miad-documents-vector-index",
    SearchVector=[{"N": str(value)} for value in embedding],
    TopK=3,
    ProjectionExpression="document_id, #t, source_url",
    ExpressionAttributeNames={"#t": "text"},
)

for result in response["SearchResults"]:
    print(
        {
            "score": result["Score"],
            "document_id": result["Item"]["document_id"]["N"],
            "text": result["Item"]["text"]["S"],
            "source_url": result["Item"]["source_url"]["S"],
        }
    )
```

前回と同じく、モデルが詳しく知らなさそうな「白笛の探窟家」について聞いてみます。

```
❯ uv run src/query.py "白笛の探窟家について教えて！"
{'score': 0.5545843839645386, 'document_id': '6', 'text': '(省略) 白笛\n\n    探窟家における最高位。限界深度は無制限。この位に到達した探窟家は数えるほどしかおらず、白笛の探窟家はみな“伝説的英雄”と称される。(省略)', 'source_url': 'https://ja.wikipedia.org/wiki/...'}
{'score': 0.6138157844543457, 'document_id': '7', 'text': '(省略) 最高位の探窟家である白笛は「奈落の星」(ネザースター)とも呼ばれ、また各人ごとに「○○卿」という異名が付く (省略)', 'source_url': 'https://ja.wikipedia.org/wiki/...'}
{'score': 0.6424354910850525, 'document_id': '9', 'text': '(省略) 本作の主人公である少女。12歳。赤笛（探窟家見習い）。金髪のおさげでメガネを掛けている。一人称は「私」。伝説級の探窟家、白笛のライザを母に持つ。(省略)', 'source_url': 'https://ja.wikipedia.org/wiki/...'}
```

ちゃんと関連するチャンクが取れていますね。体感のレイテンシもかなり速く、個人的にはS3 Vectorsと比べても遜色ないのかなと思います(実測は他の方々にお任せします)。

いくつかベクトル検索を検証していて、気付いた点を挙げておきます。

### 結果は最初からソートされている

`SearchVectors` の説明にこう書かれています。

> returns the most similar items **sorted by similarity score** based on the distance function configured for the index

つまり、 **自分でソート処理を挟む必要はありません** 。上の結果も `0.5545 → 0.6138 → 0.6424` と昇順で関連すると判断されたものから順に並んでいます。

ただし、距離関数を `DOT_PRODUCT` にすると **降順** (大きいほど似ている)になるので、距離関数を切り替える可能性があるなら明示的にソートしておいたほうが事故らないかも。

### ベクトル属性はデフォルトで返ってこない

`SearchVectors` は、 **デフォルトでベクトル属性を返しません** 。

> By default, the results from `SearchVectors` don't include the vector attribute (the embedding). Vector data is large, and you typically don't need it in the response.

<iframe src="https://embed.zenn.studio/card#zenn-embedded__ebb82b22b0877" frameborder="0"></iframe>

`Projection` を `ALL` にしていても `VectorAttribute` で指定した属性は特別扱いで除外されます。RAGだと基本的に元ベクトルは不要なので嬉しいような気もしつつ、 `ALL` なのに返ってこないみたいな例外はあんまり増やさないでほしいですね。

## Strands AgentsでAIエージェントにする

ベクトル検索でDynamoDBから関連ドキュメントを取得できることが確認できたので、 **Strands Agents** を使ってAIエージェント化していきます。

Strands Agentsでは、 `@tool` デコレータを付けた関数がそのままエージェントが利用できる **ツール** になります。先ほどの検索ロジックをツールの中に詰め込んで、結果を整形された文字列で返すようにしてあげます。

AIエージェントを動かす基盤モデルには、Bedrockで利用可能な基盤モデルの中で、そこそこまともに返答できて推論コストの安い **DeepSeek 3.2** を使っています。

```
import json

import boto3
import questionary
from rich.console import Console
from rich.table import Table
from strands import Agent, tool
from strands.models import BedrockModel

bedrock = boto3.client("bedrock-runtime")
dynamodb = boto3.client("dynamodb")
console = Console()

@tool
def search_documents(query: str) -> str:
    """自然言語で入力されたクエリを利用して、メイドインアビスに関するドキュメントをセマンティックに検索します"""

    response = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps(
            {
                "inputText": query,
                "dimensions": 1024,
            }
        ),
    )
    embedding = json.loads(response["body"].read())["embedding"]

    response = dynamodb.search_vectors(
        TableName="miad-documents-table",
        IndexName="miad-documents-vector-index",
        SearchVector=[{"N": str(value)} for value in embedding],
        TopK=3,
    )
    results = response["SearchResults"]

    table = Table(title=f"🔍 {query}", title_justify="left", title_style="bold cyan")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Score", style="magenta", justify="right")
    table.add_column("Text")

    for result in results:
        text = result["Item"]["text"]["S"].replace("\n", " ")
        table.add_row(
            result["Item"]["document_id"]["N"],
            f"{result['Score']:.4f}",
            text[:120] + ("…" if len(text) > 120 else ""),
        )

    console.print(table)

    return "\n\n".join(
        f"## ドキュメント{result['Item']['document_id']['N']}\n"
        f"出典: {result['Item']['source_url']['S']}\n\n"
        f"{result['Item']['text']['S']}"
        for result in results
    )

agent = Agent(
    model=BedrockModel(
        region_name="ap-northeast-1",
        model_id="deepseek.v3.2",
    ),
    system_prompt=(
        "あなたはメイドインアビスと呼ばれる作品に関する質問に回答するチャットボットです。\n"
        "検索ツールを利用して正しい情報を引用しつつ、ユーザのリクエストに対する回答を生成してください。"
    ),
    tools=[search_documents],
)

while question := questionary.text("質問:").ask():
    agent(question)
    console.print("\n")
```

実行するとこんな感じになりました。

```
❯ uv run src/agent.py
? 質問: 白笛の探窟家について教えて！
```

```
わかりました！白笛の探窟家について検索しますね。
Tool #1: search_documents
🔍 白笛の探窟家
┏━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID ┃  Score ┃ Text                                                               ┃
┡━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│  6 │ 0.5970 │ 軽い目まいと吐き気[6][11] 深界二層  重い吐き気と頭痛、末端の痺れ… │
│  7 │ 0.6243 │ 国外の者も、手続きを踏んで鈴付きから始めれば笛とライセンスを取得… │
│ 18 │ 0.6652 │ オースに住むそっくりな双子の姉弟。博物館で奈落文字（ネザーグリフ… │
└────┴────────┴────────────────────────────────────────────────────────────────────┘
```

```
白笛の探窟家について詳しくご説明します！

## 白笛の探窟家とは

白笛は**探窟家の中の最高位**です。探窟家のランクは下記のようになっています：

1. **鈴付き** - 探窟家のタマゴ（潜行不可）
2. **赤笛** - 探窟家見習い（限界深度：深界一層450mまで）
3. **蒼笛** - 一人前の探窟家（限界深度：深界二層まで）
4. **月笛** - 師範代（限界深度：深界四層まで）
5. **黒笛** - 達人（限界深度：深界五層まで）
6. **白笛** - **最高位、限界深度無制限**

## 白笛の特徴

### 特別な称号と地位
- 白笛は「**奈落の星(ネザースター)**」とも呼ばれています
- 各人に「○○卿」という公的な称号が付きます
- 数えるほどしか存在しない「**伝説的英雄**」と称される存在です

### 物語開始時点での白笛探窟家
現在判明している白笛は以下の5人です：

1. **「不動卿」動かざるオーゼン**
   - 50年以上前から白笛として存在
   - 深界二層の「監視基地」で暮らす
   - リコの母・ライザの師匠

2. **「黎明卿」新しきボンドルド**
   - ユアワースの生成研究過程でカートリッジを開発

3. **「神秘卿」神秘のスラージョ**

4. **「先導卿」選ばれしワクナ**

5. **「殲滅卿」殲滅のライザ**（リコの母親）
   - 物語開始時点ではラストダイブ中
   - 5話以降は笛が帰ってきたため公的には死亡扱い

## 白笛の笛「ユアワース」

白笛の持つ笛は通常の笛と大きく異なります：

- **二級遺物「ユアワース」(命を響く石)**を加工して作られる
- **深界六層以降への立ち入りキー**として機能
- 特定の遺物を起動状態にする**特殊なキー**の役割
- **所有者個人に合わせて**特殊な原料・製法で生成
- **所有者以外が所持しても機能しない**（パーソナライズされている）

このため、アビスから回収されたライザの白笛は娘のリコに遺品としてそのまま渡されましたが、リコは本人用のユアワースを別途手に入れることになりました。

## 探窟家としての特別な地位

白笛の探窟家には以下の特徴があります：

1. **限界深度無制限** - 理論上はアビス最下層まで潜行可能
2. **ラストダイブの許可** - 公式にはラストダイブ（深界六層への絶界行）にも許可が必要
3. **伝説的英雄** - 彼らの功績は探窟家たちの憧れの的
4. **唯一無二の能力** - 各白笛には独自の特殊能力や技術がある

白笛探窟家はメイドインアビスの世界において、アビスの秘密を解き明かす鍵となる極めて重要な存在です。彼らなくしては深界六層以降への到達は不可能であり、アビスの真実に迫るには白笛の存在と能力が不可欠となっています。
```

ちゃんとベクトル検索を利用して回答してくれるようになりました！

ただDynamoDBにデータを投入するだけで、簡単にRAGアプリケーションを作ることができるようになって満足です。

追加でメタデータとして引っ張ってきた `source_url` を返せば、Citation(引用)のような要件も満たすことができます。これまでのサービスだと付加情報となるメタデータの管理が大変だったので、この辺りも嬉しいポイントです。

## クォータと料金

DynamoDBのベクトル検索におけるクォータと料金をまとめてみました。

### ベクトルインデックス周りのクォータ

| 項目 | デフォルト | 引き上げ |
| --- | --- | --- |
| 1テーブルあたりのベクトルインデックス数 | 5 | 可(要サポート問い合わせ) |
| 最大次元数 | 4,096 | 不可 |
| `SearchVectors` の最大TopK | 100 | 不可 |
| ベクトルインデックスあたりのルーティングキー | 1 | 不可 |
| ベクトルインデックスあたりのインラインフィルター属性 | 18 | 不可 |
| ルーティングキーあたりの検索レート | 1 GBps | 可 |
| ルーティングキーあたりの書き込みレート | 10 MBps | 可 |
| 許可申請なしでインデックスを作成できるベーステーブルサイズ | 600 GB | 可 |

<iframe src="https://embed.zenn.studio/card#zenn-embedded__c80929d410edb" frameborder="0"></iframe>

### ベクトル検索の料金

DynamoDBのベクトル検索における課金軸は、以下の3つです。

| 軸 | 内容 |
| --- | --- |
| Vector write | ベクトルインデックスに **書き込まれたデータ量** (GB) |
| Vector search | 類似検索のレスポンス生成で **処理されたデータ量 + 返却データ量** (GB) |
| Storage | ベクトルインデックスに **保存されているデータ量** (GB/月) |

<iframe src="https://embed.zenn.studio/card#zenn-embedded__0631c44b01aea" frameborder="0"></iframe>

全てバイト単位の **データ量に対する従量課金となっており** 、従来のキャパシティユニットに対する従量課金のような料金体系とは異なっています。

実際に `ReturnConsumedCapacity` をリクエストに指定すると、いつものキャパシティユニットではなく `VectorSearchRequestBytes` という形で処理されたデータ量がバイト単位で返ってきます。

```
{'VectorSearchRequestBytes': 39887.0}
```

## その他の小ネタ

ベクトル検索の検証中に見つけた細かい話をまとめておきます。

### ステータスがACTIVEでも検索できない

`UpdateTable` で既存テーブルにベクトルインデックスを後付けした場合、 `ACTIVE` になった後も `Backfilling` が `true` の間は `SearchVectors` がエラーになります。

なので、ステータスが `ACTIVE` になるまで待つだけではダメで、 `Backfilling` が `false` か `null` になるまで検索することができないので注意です。

```
❯ aws dynamodb describe-table --table-name miad-documents-table \
    --query 'Table.VectorIndexes[0].[IndexName,IndexStatus,Backfilling]'
[
    "miad-documents-vector-index",
    "ACTIVE",
    true
]
```

### ベクトルインデックスでは、FGACが効かない

`SearchVectors` では、 **FGAC(Fine-Grained Access Control)が効きません** 。

> You can't use Amazon DynamoDB fine-grained access control (FGAC) with the `SearchVectors` API.

<iframe src="https://embed.zenn.studio/card#zenn-embedded__578ff3336ef36" frameborder="0"></iframe>

`dynamodb:LeadingKeys` や `dynamodb:Attributes` といった条件キーが無視されるため、IAMポリシー側で「このキー値しか検索させない」と縛ることができません。

なので、ルーティングキー(`HASH`)はあくまで、ベクトル検索におけるスループットの最適化が目的であり、 **セキュリティ境界としての役割はない** ことに注意が必要です。

### 専用エンドポイントにリクエストが飛んでいる

`SearchVectors` だけ、 **標準のDynamoDBエンドポイントではなく専用の検索エンドポイント** に解決されます。

`CreateTable` や `PutItem` などは `dynamodb.<region>.amazonaws.com` に飛んでいきますが、 `SearchVectors` だけ `search-dynamodb.<region>.amazonaws.com` に飛んでいきます(謎)。

### インデックスの設定は後から変更できない

`VectorAttribute` 、 `Dimensions` 、 `DistanceFunction` 、 `Projection` 、 `SearchSchema` などのベクトルインデックスにおける設定値は、 **全て後から変更することができません** 。

変更したい場合は、別名で新しいインデックスを作って移行することになるので、ベクトルインデックスの作成時には注意する必要があります。

### ItemCountの更新が6時間おき

`DescribeTable` が返すベクトルインデックスの `ItemCount` と `IndexSizeBytes` は、 **約6時間おきにしか更新されません** 。データを入れた直後は `0` のままなので、あくまで概算として使いましょう。

> The `ItemCount` and `IndexSizeBytes` values that `DescribeTable` reports for a vector index are updated approximately every six hours.

<iframe src="https://embed.zenn.studio/card#zenn-embedded__98e82392ac784" frameborder="0"></iframe>

### ルーティングキーを消すと無言でインデックスから消える

`SearchSchema` に `HASH` を定義している場合に、その属性を持たないアイテムを書き込んだり、 `UpdateItem` の `REMOVE` で `HASH` になっている属性を消したりすると、 **エラーにならずにインデックスから外れる挙動になります** 。

> Removing the vector index partition key attribute from an item (via REMOVE in UpdateItem) or omitting it in a PutItem does not produce an error. However, the item is silently de-indexed and no longer appears in search results.

<iframe src="https://embed.zenn.studio/card#zenn-embedded__20f33bdf2919d" frameborder="0"></iframe>

テーブルには存在するのにベクトル検索の結果だけに出てこないといった、ややこしいバグを生む可能性があるため、取り扱いには注意が必要です。

## まとめ

DynamoDBのベクトル検索機能の登場により、メインのストレージとベクトルDBで二重管理をする必要がなくなり、よりシームレスにRAGアプリケーションを構築できるようになりました。

既存のDynamoDBテーブルにベクトルインデックスを後付けすることも可能なので、新たに導入するハードルも大きく下がったのかなと思います。コストも安いのでぜひ試してみてください！
