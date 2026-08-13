---
url: https://github.com/microsoft/SkillOpt
created: '2026-08-11T20:48:46'
type: article
tags:
- ai
- microsoft
- opensource
- llm
- python
summary: 'Microsoftが開発したSkillOptは、LLMのモデル重みを変更せずに行動履歴から再利用可能なスキルを最適化するテキスト空間オプティマイザーです。

  エポックや検証ゲートなどのニューラルネットワーク学習の概念を取り入れ、単一のMarkdownファイルを効率的に更新します。

  多様なベンチマークやモデルにおいて、推論時のコストを増やさずにAIエージェントの性能を大幅に向上させることが可能です。'
title: 'microsoft/SkillOpt: SkillOpt is a text-space optimizer that trains reusable natural-language skills for frozen LLM agents through trajectory-driven edits, validation-gated updates, and deployable best_skill.md artifacts.'
read: false
shelf_life: medium
---

# microsoft/SkillOpt: SkillOpt is a text-space optimizer that trains reusable natural-language skills for frozen LLM agents through trajectory-driven edits, validation-gated updates, and deployable best_skill.md artifacts.
2026-08-11
## SkillOpt: Executive Strategy for Self-Evolving Agent Skills

*Train agent skills like you train neural networks — with epochs, (mini-)batchsize, learning rates, and validation gates — but without touching model weights.*

[![Project Page](https://camo.githubusercontent.com/7ea611ef378f81242c31c1c65360d31288d2cbc5d99f85954cf2677cd16ae7a1/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f50726f6a656374253230506167652d536b696c6c4f70742d386462623363)](https://microsoft.github.io/SkillOpt/) [![Paper](https://camo.githubusercontent.com/e043833705b9c184599a5228fb10c3460f6c9b850784f2eed2b5a1acb19cfa24/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f50617065722d61725869762d623331623162)](https://arxiv.org/abs/2605.23904) [![Project Video](https://camo.githubusercontent.com/5de9d157b4e3de1b13f379dc519c39eb942055480573bbfdae002f0c42743293/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f50726f6a656374253230566964656f2d576174636825323044656d6f2d666630303030)](https://youtu.be/JUBMDTCiM0M) [![PyPI](https://camo.githubusercontent.com/d43351fe980c27b0e1b54d73f18c5f0168c19eb8e0d32755e40247703203665f/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f507950492d736b696c6c6f70742d677265656e2e737667)](https://pypi.org/project/skillopt/) [![Python 3.10+](https://camo.githubusercontent.com/1e84b5e6b27224195cfafe6258acef2a29506fb27c574ab58d217cb74de10851/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f507974686f6e2d332e31302532422d626c75652e737667)](https://www.python.org/) [![License: MIT](https://camo.githubusercontent.com/fdf2982b9f5d7489dcf44570e714e3a15fce6253e0cc6b5aa61a075aac2ff71b/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4c6963656e73652d4d49542d79656c6c6f772e737667)](https://github.com/microsoft/SkillOpt/blob/main/LICENSE)

[![microsoft%2FSkillOpt | Trendshift](https://camo.githubusercontent.com/8f7e3457ddf58dbf34da260d45930d9612206f518d456b1078f714628b3ffde4/68747470733a2f2f7472656e6473686966742e696f2f6170692f62616467652f7472656e6473686966742f7265706f7369746f726965732f33383439382f6461696c793f6c616e67756167653d507974686f6e)](https://trendshift.io/repositories/38498?utm_source=trendshift-badge&utm_medium=badge&utm_campaign=badge-trendshift-38498)> 📖 **For installation, data preparation, training/eval commands, configuration, and framework internals, start with the versioned [SkillOpt documentation](https://github.com/microsoft/SkillOpt/blob/main/docs/index.md). A concise rendered overview is available in the [Documentation & Reproduction Guide](https://microsoft.github.io/SkillOpt/docs/guideline.html), and longer-form engineering analysis appears on the [Technical Blog](https://microsoft.github.io/SkillOpt/blog/). We also maintain a [Changelog](https://github.com/microsoft/SkillOpt/blob/main/CHANGELOG.md) for released and unreleased changes.**

---

## News 🔥🔥🔥

- **\[2026-07-24\]** 📰 **SkillOpt in the news.** Read the official [Microsoft Research feature](https://www.microsoft.com/en-us/research/blog/skillopt-agent-skills-as-trainable-parameters/), along with recent coverage from [VentureBeat](https://venturebeat.com/orchestration/microsofts-open-source-skillopt-automatically-upgrades-ai-agent-skills-without-touching-model-weights), [Synced (机器之心)](https://mp.weixin.qq.com/s/pMlyj3a3KOh8L7cIHClRXA), [Flowtivity](https://flowtivity.ai/blog/microsoft-skillopt-train-ai-agent-skills/), and [The Decoder](https://the-decoder.com/microsofts-skillopt-boosts-gpt-5-5-by-using-nothing-but-a-trained-markdown-file/).
- **\[2026-07-02\]** 🚀 **SkillOpt [v0.2.0](https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0) is out on [PyPI](https://pypi.org/project/skillopt/)!** Headline feature: **SkillOpt-Sleep**, a nightly offline self-evolution engine (harvest → mine → replay → consolidate behind a held-out validation gate), now shipped as the `skillopt-sleep` CLI. It also includes experimental multi-objective, replay, and dream-rollout controls; the main CLI keeps conservative defaults and does not expose every experiment-harness control as a flag. The release source adds integration shells for **Claude Code, Codex, Copilot, and Devin**, plus an **OpenClaw reference adaptation**; these plugin/MCP files live in the repository rather than the PyPI wheel. It also adds SearchQA split materialization, Windows robustness, and hardened JSON parsing. See the [release notes](https://github.com/microsoft/SkillOpt/releases/tag/v0.2.0) for full release details and contributor acknowledgements.
- **\[2026-06-15\]** 😴 **SkillOpt-Sleep (preview)** — a nightly offline self-evolution companion for local coding agents (Claude Code / Codex / Copilot): review past sessions, replay recurring tasks, and consolidate validated skills behind a held-out gate. See **[`docs/sleep/README.md`](https://github.com/microsoft/SkillOpt/blob/main/docs/sleep/README.md)** for what it is, how to use it, and results.
- **\[2026-06-03\]** 🎉 **[gbrain](https://github.com/garrytan/gbrain), [gbrain-evals](https://github.com/garrytan/gbrain-evals/blob/main/docs/benchmarks/2026-06-03-skillopt.md), and [darwin-skill](https://github.com/alchaincyf/darwin-skill) have all integrated SkillOpt.**
- **\[2026-06-02\]** 🎉 **SkillOpt [v0.1.0](https://github.com/microsoft/SkillOpt/releases/tag/v0.1.0) is now available on [PyPI](https://pypi.org/project/skillopt/)!** Install with `pip install skillopt`. This initial release includes the full training loop (rollout → reflect → aggregate → select → update → evaluate), multi-backend support (OpenAI / Azure / Claude / Qwen / MiniMax), six built-in benchmarks, and WebUI dashboard.

---

## Overview

Modern agent skills are usually hand-crafted, generated one-shot by a strong LLM, or evolved through loosely controlled self-revision — none of which behaves like a deep-learning optimizer for the skill itself, and none of which reliably improves over its starting point under feedback.

**SkillOpt treats the skill document as the trainable state of a frozen agent**, and trains it with the discipline that makes weight-space optimization reproducible. A separate optimizer model turns scored rollouts into bounded add / delete / replace edits on a single skill document; in the default paper-style path, a candidate edit is accepted only when it strictly improves a held-out validation score. A textual learning-rate budget, a rejected-edit buffer, and an epoch-wise slow / meta update make skill training stable while adding **zero inference-time model calls** at deployment.

The deployed artifact is a compact `best_skill.md` (typically 300–2,000 tokens) that runs against the unchanged target model. Across **six benchmarks, seven target models, and three execution harnesses** (direct chat, Codex CLI, Claude Code CLI), SkillOpt is best or tied-best on **all 52 evaluated (model, benchmark, harness) cells** and on GPT-5.5 lifts the average no-skill accuracy by **+23.5 points in direct chat, +24.8 inside the Codex agentic loop, and +19.1 inside Claude Code**. Optimized skill artifacts transfer across model scales, between Codex and Claude Code harnesses, and to nearby benchmarks without further optimization.

For the full method, ablations, and per-cell results see the [paper](https://arxiv.org/abs/2605.23904); for a visual walkthrough of the loop see the [project page](https://microsoft.github.io/SkillOpt/); for deeper API / backend / benchmark docs see [`docs/`](https://github.com/microsoft/SkillOpt/blob/main/docs).

## 🎬 Demo Video

64c8f76086bed7bd7a5ce664a7a14f40\_raw.mp4<video src="https://private-user-images.githubusercontent.com/29210256/597425176-eb12d3bc-371c-467f-904d-91b61f339ed7.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkwNzYsIm5iZiI6MTc4NjQ0ODc3NiwicGF0aCI6Ii8yOTIxMDI1Ni81OTc0MjUxNzYtZWIxMmQzYmMtMzcxYy00NjdmLTkwNGQtOTFiNjFmMzM5ZWQ3Lm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNjA4MTElMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjYwODExVDExNDYxNlomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPWZiYmU0MDQzYjRiMGZkYzQ1MWM3YjlhYzQxY2Y3Y2UwZjAyNjU3NzhkMzcwOTEzZDFhOTQ4NWNhNzI1ZjkxNTEmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0JnJlc3BvbnNlLWNvbnRlbnQtdHlwZT12aWRlbyUyRm1wNCJ9.PQo2f9DKxr6J_JhSuesgPwon_YE7Im46xbZ0-oom0L4" controls="controls"></video>

[**▶ Watch the full demo on YouTube**](https://youtu.be/JUBMDTCiM0M)

---

## Extensibility & WebUI

### Adding a new backend

A backend = a chat / exec target (e.g. `openai_chat`, `claude_chat`, `qwen_chat`, `minimax_chat`, `copilot_chat`, `openai_compatible`, `codex_exec`, `claude_code_exec`, `cursor_exec`, `copilot_exec`). If a provider implements the OpenAI Chat Completions protocol, try the built-in `openai_compatible` backend before adding code. See [`docs/guide/new-backend.md`](https://github.com/microsoft/SkillOpt/blob/main/docs/guide/new-backend.md) for the full contract. Chat backends add a `skillopt/model/<name>_backend.py` module; target-only exec backends use the shared harness in `codex_harness.py`. Both register through `common.py`, `backend_config.py`, and `skillopt/model/__init__.py`.

### Adding a new benchmark

A benchmark = a `skillopt/envs/<name>/` package with an adapter, a data loader, a scored rollout helper, a YAML config, and optionally an initial seed skill. See [`docs/guide/new-benchmark.md`](https://github.com/microsoft/SkillOpt/blob/main/docs/guide/new-benchmark.md) for the full contract; the simplest reference is `skillopt/envs/searchqa/`.

### WebUI

Launch the monitoring dashboard (optional):

```
pip install -e ".[webui]"
python -m skillopt_webui.app
```

| Flag | Default | Description |
| --- | --- | --- |
| `--port` | 7860 | Server port |
| `--host` | `0.0.0.0` | Bind address |
| `--share` | off | Create a public Gradio share link |

The default host listens on every network interface. Use `--host 127.0.0.1` for local-only access.

---

## Citation

```
@article{yang2026skillopt,
  title={Skillopt: Executive strategy for self-evolving agent skills},
  ={Yang, Yifan and Gong, Ziyang and Huang, Weiquan and Yang, Qihao and Zhou, Ziwei and Huang, Zisu and Li, Yan and Gao, Xuemei and Dai, Qi and Liu, Bei and others},
  journal={arXiv preprint arXiv:2605.23904},
  year={2026}
}
```
