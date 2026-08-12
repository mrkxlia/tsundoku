---
url: https://x.com/mlbear2/status/2025116238620623020?s=12&t=22GY_jUSQsg0NcuE2S9fmA
created: '2026-08-11T21:35:08'
type: post
tags:
- claudecode
- codex
- ai開発
- ワークフロー
- has-media
summary: 'Claude CodeがPlanを提示する前に自動でCodexにレビューさせる手法が確立された。

  codexのresume --lastオプションを利用することで、容易に実装することが可能となった。

  開発効率の向上に役立つ実践的なワークフローとして注目される。'
title: Claude CodeでCodex自動レビューを動かす方法
read: false
---

# Post by @MLBear2 on X
2026-08-11
Claude Code が Plan 提示する前に自動でCodexにレビューさせる方法確立できた。調べてみたら codex に resume --last ってオプションあったし一瞬でできたわ、さっさとやっておけばよかった😇 https://t.co/9jOL4CNk17

![](https://pbs.twimg.com/media/HBqoOcObgAIIWgL.jpg?name=orig)

## 画像の内容

![](../assets/2026-08-11-Claude-CodeでCodex自動レビューを動かす方法-1.jpg)

### 画像1
実装計画立案時のルールと、codexコマンドを使ったレビュー手順の具体的なコード例が記載されています。

実装計画立案時のルール
- ユーザーに計画を提示する前に、codex コマンドで計画のレビューを行うこと。具体的な使い方は以下の通り。
- レビュー指示の文章は適宜調整すること。ただし codex コマンドは本質的じゃない指摘をしてくるので「瑣末な点へのクソリプするな。致命的な点のみ指摘しろ。」という指示は必ず入れた方がいい。

# initial plan review request
# 必ず -m でモデルを指定すること (gpt-5.3-codex が最適)
codex exec -m gpt-5.3-codex "このプランをレビューして。瑣末な点へのクソリプはしないで。致命的な点だけ指摘して: {plan_full_path} (ref: {CLAUDE.md full_path})"

# updated plan review request
# resume --last をつけないと最初のレビューの文脈が失われるから注意
codex exec resume --last -m gpt-5.3-codex "プランを更新したからレビューして。瑣末な点へのクソリプはしないで。致命的な点だけ指摘して: {plan_full_path} (ref: {CLAUDE.md full_path})"
