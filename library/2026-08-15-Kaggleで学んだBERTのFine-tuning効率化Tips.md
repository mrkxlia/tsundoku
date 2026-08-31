---
title: Kaggleで学んだBERTのFine-tuning効率化Tips
url: https://www.ai-shift.co.jp/techblog/2138
created: '2026-08-15T19:16:42'
type: article
tags:
- bert
- kaggle
- 深層学習
- pytorch
- 自然言語処理
- needs-recheck
summary: 'Kaggle等で役立つBERT事前学習モデルのFine-tuning効率化手法を解説。

  混合精度の利用や文章切り詰め、Dynamic Paddingなどのテクニックを紹介。

  さらに勾配累積を用いることでメモリを節約しつつ安定した高速学習を実現する。'
read: false
shelf_life: long
recheck_reason: 記事中で「先日終了したKaggleのコンペティション」と記載されているCommonLit-Readability Prizeは、2021年8月2日に終了しており、現在（2026年8月）から見ると「先日終了した」という表現は古くなっているためです。
last_verified: '2026-08-20T15:17:57+00:00'
published_at: ''
---

# 株式会社AI Shift | サイバーエージェントグループ
2026-08-15
2021.8.13

- Research

## Kaggleで学んだBERTをfine-tuningする際のTips①〜学習効率化編〜

![](https://storage.googleapis.com/studio-design-asset-files/projects/M3aARmnzWe/s-672x350_v-fs_webp_65004cb3-8d5e-43a5-bf1f-39764279c48b.webp)

こんにちは  
AIチームの戸田です

近年、自然言語処理タスクにおいて、BERTを始めとするTransformerをベースとした事前学習モデルを感情分類や質問応答などの下流のタスクでfine-tuningする手法が一般的になっています

[huggingfaceのTransformers](https://huggingface.co/transformers/) など、事前学習モデルを簡単に使うことのできるライブラリもありますが、Kaggleなどのコンペティションで上位に入るには素のモデルのままでは難しく、ヘッダや損失関数などの工夫などが必要です

本記事では私がKaggleのコンペティションに参加して得た、事前学習モデルのfine-tuningのTipsを共有させていただきます

書きたい内容が多くなってしまったので、今回は学習の効率化について、次回精度改善について、と２回に分けて書かせていただきます

## 事前準備

学習データとして、先日終了したKaggleのコンペティション、 [CommonLit-Readability](https://www.kaggle.com/c/commonlitreadabilityprize/overview) のtrainデータを使います

Kaggle Grand Masterの [Abhishek Thakur氏](https://www.kaggle.com/abhishek) の [notebook](https://www.kaggle.com/abhishek/step-1-create-folds) の方針で5 Foldで分割し、Fold-0の分割データを利用します

```python
import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedKFold

SEED = 0
N_FOLDS = 5
INPUT_DIR = '<Kaggleからダウンロードしたものを配置したパス>'

def create_folds(data):
    data["kfold"] = -1
    data = data.sample(frac=1, random_state=SEED).reset_index(drop=True)

    num_bins = int(np.floor(1 + np.log2(len(data))))
    
    data.loc[:, "bins"] = pd.cut(
        data["target"], bins=num_bins, labels=False
    )
    kf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)
    for f, (t_, v_) in enumerate(kf.split(X=data, y=data.bins.values)):
        data.loc[v_, 'kfold'] = f
    data = data.drop("bins", axis=1)
    
    return data

train_df = pd.read_csv(f"{INPUT_DIR}/train.csv")
train_df = create_folds(train_df)

train_index = train_df.query('kfold!=0').index.tolist()
valid_index = train_df.query('kfold==0').index.tolist()
```

その他、基本の学習用のコードは [こちら](https://gist.github.com/trtd56/05e8f41832407a00934ef8ffa6a0eaea) にアップロードしていますので、ご参照いただければと思います

## 学習効率化

TransformerをベースとしたモデルはBERTに限らず、パラメーター数が非常に多いため学習に時間がかかってしまいます

ここでは試行錯誤のサイクルを早く回すための学習の効率化について紹介させたいただきます

BERTに限らず、画像認識のモデルなどにも使えるものもありますので、ご参考にしていただければと思います

### 混合精度(Mixed Precision)の利用

通常、pytorchなどのライブラリは32 ビットの単精度浮動小数点数(FP32)を利用してニューラルネットを学習しますが、百度とNVIDIAが発表した [Mixed Precision Training](https://arxiv.org/abs/1710.03740) という論文で、いくつか工夫を加えることで、半分の 16 ビットの半精度浮動小数点数 (FP16) でも、モデルの正確度をほぼ落とすことなく、トレーニングを高速化できることが示されました

FP16 で学習することができれば、必要なメモリは半分になるため、大きなバッチサイズを使うことができます

加えて最新のGPUにはTensorコアというものが導入されており、単純な演算速度の向上も見込めるようです

pytorchは [version 1.6からデフォルトで混合精度の学習をサポート](https://pytorch.org/docs/stable/notes/amp_examples.html) しています

以下は全く同じパラメータでseedを固定し、混合精度を使うか否かだけ変えた2つの学習のWeights & Biasesのスクリーンショットになります

![](https://storage.googleapis.com/studio-design-asset-files/projects/M3aARmnzWe/s-2318x1370_v-frms_webp_88da9dad-89c6-4800-b7e9-1651af30d536.png)

赤が通常時で、青が混合精度を使った場合ですが、青のほうがGPUメモリの消費が少ないことがわかります

BESTなValidationの精度と学習時間は以下のようになります

|  | 精度(MSE) | 学習時間 |
| --- | --- | --- |
| baseline | 0.5032 | 34分44秒 |
| mixed\_precision | 0.5068 | 31分42秒 |

学習にはGoogle Colaboratory ProのTesla V100を使ったのですが、私の実装の問題なのか、学習時間は思ったより短縮されませんでした

一方、精度はほぼ劣化なしと言っても良いと思います

### 文章の切り詰め

[Reformer](https://arxiv.org/abs/2001.04451) のような例外もありますが、多くのTransformerモデルはその主要な部品であるScaled Dot-Product Attentionが文章の長さ𝑛に対して𝑂(𝑛2)でメモリを使用するため、長い文章に対してメモリ消費量が急激に増加してしまうという問題があります

BERTやRoBERTaのデフォルトの最長文字列の長さは512トークンですが、これを制限することで、メモリを削減することができます

しかしトークン数が少なくなるので必然的に情報が欠損してしまい、タスクの精度が下がってしまいます

[How to Fine-Tune BERT for Text Classification?](https://arxiv.org/pdf/1905.05583.pdf) という論文には、重要な情報は文章の最初と最後に現れることが多いので、文章を切り詰める際に先頭と末尾を利用することを提案しており、実際の文書分類のタスクで単純に先頭や末尾のみを切り取った場合とくらべて良い精度が出せていることを示しています

うまく文章を切り詰めれば、タスクにもよると思いますが、トークン数を制限してメモリを削減しつつ精度を担保することが期待できます

実装例は以下のようになります

```python
MAX_LEN　# トークンの最大数(デフォルト512)
TOKENIZER # モデルに合わせたTokenizer

def cut_head_and_tail(text):
    # まずは限界を設定せずにトークナイズする
    input_ids = TOKENIZER.encode(text)
    n_token = len(input_ids)

    # トークン数が最大数と同じ場合
    if n_token == MAX_LEN:
        input_ids = input_ids
        attention_mask = [1 for _ in range(MAX_LEN)]
        token_type_ids = [1 for _ in range(MAX_LEN)]
    # トークン数が最大数より少ない場合
    elif n_token < MAX_LEN:
        pad = [1 for _ in range(config.MAX_LEN-n_token)]
        input_ids = input_ids + pad
        attention_mask = [1 if n_token > i else 0 for i in range(MAX_LEN)]
        token_type_ids = [1 if n_token > i else 0 for i in range(MAX_LEN)]
    # トークン数が最大数より多い場合
    else:
        harf_len = (MAX_LEN-2)//2
        _input_ids = input_ids[1:-1]
        input_ids = [0]+ _input_ids[:harf_len] + _input_ids[-harf_len:] + [2]
        attention_mask = [1 for _ in range(MAX_LEN)]
        token_type_ids = [1 for _ in range(MAX_LEN)]

    d = {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
        "token_type_ids": torch.tensor(token_type_ids, dtype=torch.long),
    }
    
    return d
```

token\_type\_idsはモデルによって値が異なるので気をつけてください

### Uniform Length Batching

Transformerに限らず、ニューラルネットワークの学習はミニバッチ学習で行われます。各ミニバッチ内ではシーケンス長を揃える必要があるため、Transformerでは\[PAD\]と呼ばれる特殊なトークンを追加して長さを揃えます。(Padding)

通常、学習データ内の最長のシーケンスに揃えてPaddingを行います

![Fixed Padding](https://drive.google.com/uc?export=view&id=1UaVW3gxTSAD0E9CrCX48kn6QF_L_slP9)

上記画像だと14トークンになるようにPaddingをしていますが、バッチによっては半数近くが\[PAD\]になっており、無駄な計算をしているように見えます

これに対応するため、近い長さのシーケンスで構成されたバッチを生成するようにし、バッチごとの最大長で動的にシーケンス長を揃えることで不要な\[PAD\]の計算を削減することができます

![Uniform Length Batching](https://drive.google.com/uc?export=view&id=1UjQaOAkN-zPh10fSoXmZ-68jMdFLq2y_)

この手法の懸念点として、バッチごとのバリエーションが少なくなってしまうので、学習が不安定になってしまうことがあるので注意してください

Paddingの画像はNotebook Masterの [torch氏](https://www.kaggle.com/rhtsingh) の [notebook](https://www.kaggle.com/rhtsingh/speeding-up-transformer-w-optimization-strategies) からお借りしました  
実装もリンク先にわかりやすいものがございますのでそちらをご参照いただければと思います

torch氏はこの他にも様々な有用なコードを共有してくれています  
私も見習っていきたいです

### 勾配累積(Gradient Accumulation)

こちらは精度改善にも関わることなので、次回にしようかとも考えたのですが、学習を安定させて試行錯誤のサイクルを早く回す、という点では学習効率化になると考え、本記事で扱わせていただきます

Transformerのモデルはパラメーター数が多いのでメモリ消費量が大きく、その影響でバッチサイズを小さくする必要があります  
バッチサイズが小さいと学習に時間がかかるのはもちろんのこと、学習が不安定になり、精度が下がってしまう可能性があります

これに対処するため、小さなバッチサイズでも大きなバッチサイズと同様の安定性能を出すための手法がGradient Accumulationです

実装は単純で、小さいバッチで計算した重みを保存しておき、複数回分ためてから平均を取り、それを用いてモデルのパラメータを更新する、というものです

例えばバッチサイズ16で2回勾配累積をするとバッチサイズ32で学習させたことと同等の精度を得られることが期待できます。

簡易的なコードになりますが、以下のような実装をすれば勾配累積を使うことができます

```python
ITERS_TO_ACCUMULATE # 累積数

for epoch in epochs:
    for i, (input, target) in enumerate(data):

        output = model(input)
        loss = loss_fn(output, target)
        loss = loss / iters_to_accumulate
        loss.backward()

        if (i + 1) % ITERS_TO_ACCUMULATE == 0:
            optimizer.step()
            optimizer.zero_grad()
```

混合精度の検証の際と同様に全く同じパラメータでseedを固定し、バッチサイズ32のbaseline、バッチサイズを半分の16にしたbs16 、そしてバッチサイズを半分の16にし、勾配累積を2回行うbs16\_accumlate2の3パターンの検証を行いました

![](https://storage.googleapis.com/studio-design-asset-files/projects/M3aARmnzWe/s-2304x1370_v-frms_webp_8c7ac548-38b0-492a-9ece-bc6caf127706.png)

すべて同じepoch学習を回していますが、bs16は１回のステップに回せるデータ数が半分なので、ステップ数が倍になっており、bs16\_accumlate2は2回に1回の学習を行うのでbaselineと同じステップ数になっています

BESTなValidationの精度と学習時間は以下のようになります

|  | 精度(MSE) | 学習時間 |
| --- | --- | --- |
| baseline | 0.5032 | 34分44秒 |
| bs16 | 0.5131 | 1時間5分56秒 |
| bs16\_accumulate2 | 0.5007 | 34分13秒 |

bs16は学習時間が2倍になっている上、baselineと比較して精度も劣化してしまっています

一方bs16\_accumulate2は精度の劣化はなく（むしろ改善）、学習時間もほぼかわっていないことがわかります

## おわりに

本記事では私がKaggleのコンペティションに参加して得た、事前学習モデルのfine-tuningの学習の効率化に関するTipsを共有させていただきました

次回は精度改善のTipsについて書かせていただきたいと思います

最後までお読みいただきありがとうございました！
