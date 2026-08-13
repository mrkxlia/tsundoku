---
url: https://x.com/jij_inc_jp/status/2085274679615562068
created: '2026-08-11T19:04:37'
type: post
tags:
- jijmodeling
- 数理最適化
- 生成ai
- claude
- has-media
summary: '数理最適化モデリングツール「JijModeling 2」の新版がリリースされました。

  Flat ASTの採用によりコンパイル時間とメモリ使用量を大幅削減しました。

  Claude Fable 5の活用で初期実装が実働2日に短縮され約1ヶ月でリリースされました。'
title: JijModeling 2新版リリース Claude活用で開発短縮
read: false
shelf_life: medium
---

数理最適化モデリングツール「JijModeling 2」の新バージョンをリリースしました 🚀

コンパイラ内部表現として Flat AST を採用し、コンパイル時間とメモリ使用量を大幅に削減しました。当初計画では実装からローンチまで2ヶ月程度を見込んでいましたが、Claude Fable 5により初期実装は実働2日程度で完了✨  
その後、開発メンバーによる徹底的なレビュー、リファクタリングを経て1ヶ月弱でリリースまでこぎつけることができました！ Thank you @claudeai 🙌

詳しくは近日公開予定のPodcast や公式ドキュメントをご覧ください👉[https://t.co/PytrOvMhpp](https://t.co/PytrOvMhpp)

#JijModeling #MathematicalOptimization

![](https://pbs.twimg.com/media/HPBN4AJaAAAmPQT.jpg?name=orig)

## 画像の内容

![](../assets/2026-08-11-JijModeling-2新版リリース-Claude活用で開発短縮-1.jpg)

### 画像1
JijModelingからOMMXへコンパイルされ、多様なソルバーに入力される仕組みを示したワークフロー図。
JijModeling
Compile
OMMX
Input
Solvers
JijZept Solver
Qamomile
OpenJij
SCIP
Gurobi
...
