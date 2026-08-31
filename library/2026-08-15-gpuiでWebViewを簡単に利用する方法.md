---
title: gpuiでWebViewを簡単に利用する方法
url: https://voluntas.ghost.io/gpui-webview/
created: '2026-08-15T19:16:42'
type: article
tags:
- rust
- gpui
- webview
- ui
summary: 'gpuiはZedが公開しているRust製のUIフレームワークである。

  Tauriのwryを使うgpui-wryを利用することでWebViewを容易に導入できる。

  Rust開発者にとって導入を検討する価値のあるフレームワークである。'
read: false
shelf_life: medium
published_at: '2026-08-14'
---

# gpui で WebView を使う
2026-08-15
[gpui](https://gpui.rs/?ref=voluntas.ghost.io) については、別途記事を書く予定です。gpui は [Zed](https://zed.dev/?ref=voluntas.ghost.io) が公開している Rust 製の UI フレームワークです。時雨堂では自社ドキュメントツールチェイン専用のエディタ開発などに利用しています。

自社ドキュメントツールチェインでは [reST](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html?ref=voluntas.ghost.io) から出力した HTML をエディタで表示するために WebView を採用しています。

gpui での WebView は想像以上に簡単で [Tauri](https://tauri.app/?ref=voluntas.ghost.io) が公開している [wry](https://github.com/tauri-apps/wry?ref=voluntas.ghost.io) を使う [gpui-wry](https://github.com/longbridge/gpui-component/tree/main/crates/webview?ref=voluntas.ghost.io) を使うだけでサクッと動かせます。

<video src="https://storage.ghost.io/c/72/43/72437cfd-b364-4edd-89da-f7d288fb4a9c/content/media/2026/08/01bd217ff8632be92f14715c39eb8d28--1-.mp4" width="1514" height="1080" controls=""></video>0:00

/0:04

ほんとサクサク

---

gpui は作っていて楽しい UI フレームワークなので、もし Rust を利用されているのであれば、検討する価値はあると思います。
