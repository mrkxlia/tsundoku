https://github.com/microsoft/VibeVoice
# microsoft/VibeVoice: Open-Source Frontier Voice AI
2026-08-11
## 🎙️ VibeVoice: Open-Source Frontier Voice AI

[![Project Page](https://camo.githubusercontent.com/6fde97b223a8098e26a6f80c68194a9c88a136ef64a39dfbf531a8056a2c79ae/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f50726f6a6563742d506167652d626c75653f6c6f676f3d6769746875627061676573)](https://microsoft.github.io/VibeVoice) [![Hugging Face](https://camo.githubusercontent.com/0ec1edc31da1db1027074ab138e375d6dd9b709ac3abedf38ae78c7a7f38e71c/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f48756767696e67466163652d436f6c6c656374696f6e2d6f72616e67653f6c6f676f3d68756767696e6766616365)](https://huggingface.co/collections/microsoft/vibevoice-68a2ef24a875c44be47b034f) [![TTS Report](https://camo.githubusercontent.com/321ae2ff5cc846cde77267a619412a46195a6688df609ccc0164f59aa0493b67/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f5454532d5265706f72742d7265643f6c6f676f3d6172786976)](https://openreview.net/pdf?id=FihSkzyxdv) [![ASR Report](https://camo.githubusercontent.com/0c9126e875fd52b38ddce9c3923666612b356f1b7268ee37d638f951b1cf56f6/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4153522d5265706f72742d79656c6c6f773f6c6f676f3d6172786976)](https://arxiv.org/pdf/2601.18184) [![Colab](https://camo.githubusercontent.com/e597065dba5c2c8949acb0442eb27f5743952dc7f74bfcfa47eb18cef89b8e9b/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f53747265616d696e675454532d436f6c61622d677265656e3f6c6f676f3d676f6f676c65636f6c6162)](https://colab.research.google.com/github/microsoft/VibeVoice/blob/main/demo/VibeVoice_colab.ipynb) [![ASR Playground](https://camo.githubusercontent.com/65e613a8d7a03ac7de6ff0c844704f30ccec69c114eac2428df1dc8560854d82/68747470733a2f2f696d672e736869656c64732e696f2f62616467652f4153522d506c617967726f756e642d3646343243313f6c6f676f3d67726164696f)](https://aka.ms/vibevoice-asr)

[![microsoft%2FVibeVoice | Trendshift](https://camo.githubusercontent.com/dd1b112ad15616db87e80eaff4d375235f0f966d08a8e61cbb2c72e9b49e1127/68747470733a2f2f7472656e6473686966742e696f2f6170692f62616467652f7265706f7369746f726965732f3135343635)](https://trendshift.io/repositories/15465)

![VibeVoice Logo](https://github.com/microsoft/VibeVoice/raw/main/Figures/VibeVoice_logo_white.png)

### 📰 News

**2026-07-23: ⚡ We released [VibeVoice-ASR-BitNet](https://github.com/microsoft/VibeASR.cpp), an edge CPU inference engine for VibeVoice-ASR. Through heterogeneous quantization (I8\_S + I2\_S), the model is compressed from 4.62 GB to 1.58 GB with real-time inference (RTF < 1) on 3+ CPU threads — no GPU required. \[[Code](https://github.com/microsoft/VibeASR.cpp)\] \[[Models](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet)\] \[[Report](https://arxiv.org/abs/2607.21075)\]**

**2026-03-12: 🚀 VibeVoice-ASR is now integrated into [Azure AI Foundry Labs](https://labs.ai.azure.com/innovations/vibevoice-asr/)! You can now explore and test our unified speech-to-text capabilities directly through Microsoft Foundry.**

**2026-03-06: 🚀 VibeVoice ASR is now part of a [Transformers release](https://huggingface.co/microsoft/VibeVoice-ASR-HF)! You can now use our speech recognition model directly through the Hugging Face Transformers library for seamless integration into your projects.**

**2026-01-21:** 📣 We open-sourced [**VibeVoice-ASR**](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-asr.md), a unified speech-to-text model designed to handle 60-minute long-form audio in a single pass, generating structured transcriptions containing Who (Speaker), When (Timestamps), and What (Content), with support for User-Customized Context. Try it in [Playground](https://aka.ms/vibevoice-asr).

- ⭐️ VibeVoice-ASR is natively multilingual, supporting over 50 languages — check the [supported languages](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-asr.md#language-distribution) for details.
- 🔥 The VibeVoice-ASR [finetuning code](https://github.com/microsoft/VibeVoice/blob/main/finetuning-asr/README.md) is now available!
- ⚡️ **vLLM inference** is now supported for faster inference; see [vllm-asr](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-vllm-asr.md) for more details.
- 📑 [VibeVoice-ASR Technique Report](https://arxiv.org/pdf/2601.18184) is available.

2025-12-16: 📣 We added experimental speakers to [**VibeVoice‑Realtime‑0.5B**](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-realtime-0.5b.md) for exploration, including multilingual voices in nine languages (DE, FR, IT, JP, KR, NL, PL, PT, ES) and 11 distinct English style voices. [Try it](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-realtime-0.5b.md#optional-more-experimental-voices). More speaker types will be added over time.

2025-12-03: 📣 We open-sourced [**VibeVoice‑Realtime‑0.5B**](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-realtime-0.5b.md), a real‑time text‑to‑speech model that supports streaming text input and robust long-form speech generation. Try it on [Colab](https://colab.research.google.com/github/microsoft/VibeVoice/blob/main/demo/vibevoice_realtime_colab.ipynb).

2025-09-05: VibeVoice is an open-source research framework intended to advance collaboration in the speech synthesis community. After release, we discovered instances where the tool was used in ways inconsistent with the stated intent. Since responsible use of AI is one of Microsoft’s guiding principles, we have removed the VibeVoice-TTS code from this repository.

2025-08-25: 📣 We open-sourced [**VibeVoice-TTS**](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-tts.md), a long-form multi-speaker text-to-speech model that can synthesize speech up to 90 minutes long with up to 4 distinct speakers. — accepted as an [Oral](https://openreview.net/forum?id=FihSkzyxdv) at ICLR 2026! 🔥

## Overview

VibeVoice is a **family of open-source frontier voice AI models** that includes both Text-to-Speech (TTS) and Automatic Speech Recognition (ASR) models.

A core innovation of VibeVoice is its use of continuous speech tokenizers (Acoustic and Semantic) operating at an ultra-low frame rate of **7.5 Hz**. These tokenizers efficiently preserve audio fidelity while significantly boosting computational efficiency for processing long sequences. VibeVoice employs a [next-token diffusion](https://arxiv.org/abs/2412.08635) framework, leveraging a Large Language Model (LLM) to understand textual context and dialogue flow, and a diffusion head to generate high-fidelity acoustic details.

For more information, demos, and examples, please visit our [Project Page](https://microsoft.github.io/VibeVoice).

| Model | Weight | Quick Try |
| --- | --- | --- |
| VibeVoice-ASR-7B | [HF Link](https://huggingface.co/microsoft/VibeVoice-ASR) | [Playground](https://aka.ms/vibevoice-asr) |
| VibeVoice-ASR-BitNet (CPU) | [HF Link](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet) | [VibeASR.cpp](https://github.com/microsoft/VibeASR.cpp) |
| VibeVoice-TTS-1.5B | [HF Link](https://huggingface.co/microsoft/VibeVoice-1.5B) | Disabled |
| VibeVoice-Realtime-0.5B | [HF Link](https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B) | [Colab](https://colab.research.google.com/github/microsoft/VibeVoice/blob/main/demo/vibevoice_realtime_colab.ipynb) |

## Models

### 1\. 📖 VibeVoice-ASR - Long-form Speech Recognition

**VibeVoice-ASR** is a unified speech-to-text model designed to handle **60-minute long-form audio** in a single pass, generating structured transcriptions containing **Who (Speaker), When (Timestamps), and What (Content)**, with support for **Customized Hotwords**.

- **🕒 60-minute Single-Pass Processing**: Unlike conventional ASR models that slice audio into short chunks (often losing global context), VibeVoice ASR accepts up to **60 minutes** of continuous audio input within 64K token length. This ensures consistent speaker tracking and semantic coherence across the entire hour.
- **👤 Customized Hotwords**: Users can provide customized hotwords (e.g., specific names, technical terms, or background info) to guide the recognition process, significantly improving accuracy on domain-specific content.
- **📝 Rich Transcription (Who, When, What)**: The model jointly performs ASR, diarization, and timestamping, producing a structured output that indicates *who* said *what* and *when*.

[📖 Documentation](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-asr.md) | [🤗 Hugging Face](https://huggingface.co/microsoft/VibeVoice-ASR) | [🎮 Playground](https://aka.ms/vibevoice-asr) | [🛠️ Finetuning](https://github.com/microsoft/VibeVoice/blob/main/finetuning-asr/README.md) | [📊 Paper](https://github.com/microsoft/VibeVoice/blob/main/docs/VibeVoice-ASR-Report.pdf)

[![DER](https://github.com/microsoft/VibeVoice/raw/main/Figures/DER.jpg)](https://github.com/microsoft/VibeVoice/blob/main/Figures/DER.jpg)  
[![cpWER](https://github.com/microsoft/VibeVoice/raw/main/Figures/cpWER.jpg)](https://github.com/microsoft/VibeVoice/blob/main/Figures/cpWER.jpg)  
[![tcpWER](https://github.com/microsoft/VibeVoice/raw/main/Figures/tcpWER.jpg)](https://github.com/microsoft/VibeVoice/blob/main/Figures/tcpWER.jpg)

small.mp4<video src="https://private-user-images.githubusercontent.com/173002764/538748424-acde5602-dc17-4314-9e3b-c630bc84aefa.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkxMjksIm5iZiI6MTc4NjQ0ODgyOSwicGF0aCI6Ii8xNzMwMDI3NjQvNTM4NzQ4NDI0LWFjZGU1NjAyLWRjMTctNDMxNC05ZTNiLWM2MzBiYzg0YWVmYS5tcDQ_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTQ3MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT0yY2JjMjk3MDBlY2UwMTFjNzhlOTc3YzAyYmM1NWZlYmM3OTFiYWIyOGRjNzAyYzBjZWZkMzBiOWY2NGFiMmYzJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9dmlkZW8lMkZtcDQifQ.UdKRaahbP5jSXDtFdZRAT5P_p1MP8UhOnPLdlsIjg3M" controls="controls"></video>

### 2\. 🎙️ VibeVoice-TTS - Long-form Multi-speaker TTS

**Best for**: Long-form conversational audio, podcasts, multi-speaker dialogues

- **⏱️ 90-minute Long-form Generation**: Synthesizes conversational/single-speaker speech up to **90 minutes** in a single pass, maintaining speaker consistency and semantic coherence throughout.
- **👥 Multi-speaker Support**: Supports up to **4 distinct speakers** in a single conversation, with natural turn-taking and speaker consistency across long dialogues.
- **🎭 Expressive Speech**: Generates expressive, natural-sounding speech that captures conversational dynamics and emotional nuances.
- **🌐 Multi-lingual Support**: Supports English, Chinese and other languages.

[📖 Documentation](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-tts.md) | [🤗 Hugging Face](https://huggingface.co/microsoft/VibeVoice-1.5B) | [📊 Paper](https://arxiv.org/pdf/2508.19205)

[![VibeVoice Results](https://github.com/microsoft/VibeVoice/raw/main/Figures/VibeVoice-TTS-results.jpg)](https://github.com/microsoft/VibeVoice/blob/main/Figures/VibeVoice-TTS-results.jpg)

**English**

ES\_.\_3.mp4<video src="https://private-user-images.githubusercontent.com/173002764/482832632-0967027c-141e-4909-bec8-091558b1b784.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkxMjksIm5iZiI6MTc4NjQ0ODgyOSwicGF0aCI6Ii8xNzMwMDI3NjQvNDgyODMyNjMyLTA5NjcwMjdjLTE0MWUtNDkwOS1iZWM4LTA5MTU1OGIxYjc4NC5tcDQ_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTQ3MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT04NTAxZmZhMzEwZDllMzQ5NDc1MjUzODBjZjk1NmI5N2M1Zjk4OTRiYjQxM2RkOWI5ZTI5YTc5NjMxMmRlMTlhJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9dmlkZW8lMkZtcDQifQ.8V9keGZGqzr2QqzlOwHwZala3n6MVjBG-fSNpKZpcII" controls="controls"></video>

**Chinese**

default.mp4<video src="https://private-user-images.githubusercontent.com/173002764/482832714-322280b7-3093-4c67-86e3-10be4746c88f.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkxMjksIm5iZiI6MTc4NjQ0ODgyOSwicGF0aCI6Ii8xNzMwMDI3NjQvNDgyODMyNzE0LTMyMjI4MGI3LTMwOTMtNGM2Ny04NmUzLTEwYmU0NzQ2Yzg4Zi5tcDQ_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTQ3MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT0yMmJhODJiYmI0NTE3MTExOGY4YWJiODFjOGEzZDdiZmYwMzk2ODY2MmJjZTUxMTcwMjc1ZjlkZmQ1MDUwMmNiJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9dmlkZW8lMkZtcDQifQ.s2gWI_UIpw4oW_6sIgDA91wto3iLWpa7mn81xeco1MA" controls="controls"></video>

**Cross-Lingual**

1p\_EN2CH.mp4<video src="https://private-user-images.githubusercontent.com/173002764/481713446-838d8ad9-a201-4dde-bb45-8cd3f59ce722.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkxMjksIm5iZiI6MTc4NjQ0ODgyOSwicGF0aCI6Ii8xNzMwMDI3NjQvNDgxNzEzNDQ2LTgzOGQ4YWQ5LWEyMDEtNGRkZS1iYjQ1LThjZDNmNTljZTcyMi5tcDQ_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTQ3MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1iMzFhNjUwZTE5OTAzYTY0ZTZhZDAwYmVmNmI5MDJjMDk4ZmQ4Mjc5ZDk0NmE2OWM3YjZlOTdkYmMzMjdiMDJmJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9dmlkZW8lMkZtcDQifQ.oK96mqMJcJwM56rfVsjhRDRpEZlPB9YZijcE_7nvoEk" controls="controls"></video>

**Spontaneous Singing**

2p\_see\_u\_again.mp4<video src="https://private-user-images.githubusercontent.com/173002764/481713587-6f27a8a5-0c60-4f57-87f3-7dea2e11c730.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkxMjksIm5iZiI6MTc4NjQ0ODgyOSwicGF0aCI6Ii8xNzMwMDI3NjQvNDgxNzEzNTg3LTZmMjdhOGE1LTBjNjAtNGY1Ny04N2YzLTdkZWEyZTExYzczMC5tcDQ_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTQ3MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1jYWRmZjliMDE1ODMyMjFiZTA3NGYwY2MwNTY2OGUyYjU5ZmQ5NzVhNWU3YzQ2MjUzYzQxNjQxODk1NTRkMDFlJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9dmlkZW8lMkZtcDQifQ.Im6Sr-HB310I98xzNGCa27vCMvFVBCudMj8mmS7Mwo4" controls="controls"></video>

**Long Conversation with 4 people**

4p\_climate\_45min.mp4<video src="https://private-user-images.githubusercontent.com/173002764/481727521-a357c4b6-9768-495c-a576-1618f6275727.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkxMjksIm5iZiI6MTc4NjQ0ODgyOSwicGF0aCI6Ii8xNzMwMDI3NjQvNDgxNzI3NTIxLWEzNTdjNGI2LTk3NjgtNDk1Yy1hNTc2LTE2MThmNjI3NTcyNy5tcDQ_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjYwODExJTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI2MDgxMVQxMTQ3MDlaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1kMTRlNDAwODJiOWM2OWM2NTNmOTNkZmZjOTE3MDljNTNkY2JlMmMwMTlhMDU5OTQzYWM3OWZlNWJkNmQwZTA1JlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCZyZXNwb25zZS1jb250ZW50LXR5cGU9dmlkZW8lMkZtcDQifQ.V-5HUoidXhavsH4r8yIGliGoQE9wkQinLuw30jwz1yo" controls="controls"></video>

### 3\. ⚡ VibeVoice-Streaming - Real-time Streaming TTS

VibeVoice-Realtime is a **lightweight real‑time** text-to-speech model supporting **streaming text input** and **robust long-form speech generation**.

- Parameter size: 0.5B (deployment-friendly)
- Real-time TTS (~300 milliseconds first audible latency)
- Streaming text input
- Robust long-form speech generation (~10 minutes)

[📖 Documentation](https://github.com/microsoft/VibeVoice/blob/main/docs/vibevoice-realtime-0.5b.md) | [🤗 Hugging Face](https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B) | [🚀 Colab](https://colab.research.google.com/github/microsoft/VibeVoice/blob/main/demo/vibevoice_realtime_colab.ipynb)

VibeVoice\_Realtime.mp4<video src="https://private-user-images.githubusercontent.com/20237658/522449535-0901d274-f6ae-46ef-a0fd-3c4fba4f76dc.mp4?jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3ODY0NDkxMjksIm5iZiI6MTc4NjQ0ODgyOSwicGF0aCI6Ii8yMDIzNzY1OC81MjI0NDk1MzUtMDkwMWQyNzQtZjZhZS00NmVmLWEwZmQtM2M0ZmJhNGY3NmRjLm1wND9YLUFtei1BbGdvcml0aG09QVdTNC1ITUFDLVNIQTI1NiZYLUFtei1DcmVkZW50aWFsPUFLSUFWQ09EWUxTQTUzUFFLNFpBJTJGMjAyNjA4MTElMkZ1cy1lYXN0LTElMkZzMyUyRmF3czRfcmVxdWVzdCZYLUFtei1EYXRlPTIwMjYwODExVDExNDcwOVomWC1BbXotRXhwaXJlcz0zMDAmWC1BbXotU2lnbmF0dXJlPTc0NTM3ZDVmZDczMTIzZDdiNGVkMWUwODdiZTNhYmI2YzMwNWQ0N2I0ZTYyYmUxNGQzMmM0NTA3NDM5YjY4YTcmWC1BbXotU2lnbmVkSGVhZGVycz1ob3N0JnJlc3BvbnNlLWNvbnRlbnQtdHlwZT12aWRlbyUyRm1wNCJ9.jFppa-xoONJToXgefdOPGNoGfmCo1_kBBWuyumRlrNY" controls="controls"></video>

## Contributing

Please see [CONTRIBUTING.md](https://github.com/microsoft/VibeVoice/blob/main/CONTRIBUTING.md) for detailed contribution guidelines.

## ⚠️ Risks and Limitations

While efforts have been made to optimize it through various techniques, it may still produce outputs that are unexpected, biased, or inaccurate. VibeVoice inherits any biases, errors, or omissions produced by its base model (specifically, Qwen2.5 1.5b in this release). Potential for Deepfakes and Disinformation: High-quality synthetic speech can be misused to create convincing fake audio content for impersonation, fraud, or spreading disinformation. Users must ensure transcripts are reliable, check content accuracy, and avoid using generated content in misleading ways. Users are expected to use the generated content and to deploy the models in a lawful manner, in full compliance with all applicable laws and regulations in the relevant jurisdictions. It is best practice to disclose the use of AI when sharing AI-generated content.

We do not recommend using VibeVoice in commercial or real-world applications without further testing and development. This model is intended for research and development purposes only. Please use responsibly.

[![Star History Chart](https://camo.githubusercontent.com/61ec5778b79905c3cd6fdde812df954feb841c69298c944cefe3729e5e2d039f/68747470733a2f2f6170692e737461722d686973746f72792e636f6d2f7376673f7265706f733d4d6963726f736f66742f76696265766f69636526747970653d64617465266c6567656e643d746f702d6c656674)](https://camo.githubusercontent.com/61ec5778b79905c3cd6fdde812df954feb841c69298c944cefe3729e5e2d039f/68747470733a2f2f6170692e737461722d686973746f72792e636f6d2f7376673f7265706f733d4d6963726f736f66742f76696265766f69636526747970653d64617465266c6567656e643d746f702d6c656674)