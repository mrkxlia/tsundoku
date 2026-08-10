"""LLM呼び出しモジュール。

要約・タグ生成のLLM呼び出しをこのモジュールに集約する。
将来ClaudeやOpenAIに差し替える場合は LLMClient を実装したクラスを追加し、
create_client() の分岐を変えるだけでよい。

環境変数:
    GEMINI_API_KEY     : Google AI Studio のAPIキー(必須。DRY_RUN時は不要)
    LLM_MODEL_CHAIN    : カンマ区切りのモデル名。先頭から順に試し、
                         枠超過(429)等で次のモデルへフォールバックする
    LLM_SLEEP_SECONDS  : API呼び出し後のスリープ秒数(無料枠のRPM対策)
    DRY_RUN            : "1" で外部APIを呼ばないモッククライアントを使う
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

DEFAULT_MODEL_CHAIN = "gemini-3.6-flash,gemini-3.5-flash-lite,gemma-4-26b-a4b-it"
DEFAULT_SLEEP_SECONDS = 13.0  # Flash系無料枠(5RPM)に収まる間隔
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_BODY_CHARS = 8000  # トークン消費を抑えるため本文は先頭のみ渡す

PROMPT_TEMPLATE = """あなたはWebクリップ記事を整理する司書です。以下の記事を読み、次のJSONだけを出力してください。JSON以外の文字は一切出力しないでください。

{{"title": "内容を表す簡潔な日本語タイトル(30字以内)", "summary": "記事の要約(日本語で3行程度。行は\\nで区切る)", "tags": ["タグ1", "タグ2", "タグ3"]}}

制約:
- tags は3〜5個。日本語または英小文字で、スペースを含めないこと(例: "生成ai", "プログラミング", "キャリア")
- title にはファイル名に使えない記号(/ \\ : * ? " < > |)を使わないこと
- 本文が無い場合はURLから推測できる範囲で構わない

URL: {url}
タイトルのヒント: {title_hint}
本文:
{body}
"""


class LLMError(Exception):
    """全モデルで生成に失敗した場合に送出される。"""


class LLMClient:
    """要約・タグ生成のインターフェース。"""

    def generate_note_meta(self, url: str, title_hint: str, body: str) -> dict:
        """クリップ1件から {"title": str, "summary": str, "tags": [str]} を返す。"""
        raise NotImplementedError


class GeminiClient(LLMClient):
    """Google AI Studio (Generative Language API) をRESTで直接呼ぶ実装。

    モデルチェーンの先頭から順に試し、レート制限(429)やサーバエラーで
    次のモデルへフォールバックする。Gemma系モデルはJSONモード非対応のため
    プロンプト内指示 + レスポンスからのJSON抽出で対応する。
    """

    def __init__(self, api_key: str, model_chain: list[str], sleep_seconds: float):
        if not api_key:
            raise LLMError("GEMINI_API_KEY が設定されていません")
        self.api_key = api_key
        self.model_chain = model_chain
        self.sleep_seconds = sleep_seconds

    def generate_note_meta(self, url: str, title_hint: str, body: str) -> dict:
        prompt = PROMPT_TEMPLATE.format(
            url=url,
            title_hint=title_hint or "(なし)",
            body=(body or "(本文なし)")[:MAX_BODY_CHARS],
        )
        errors = []
        for model in self.model_chain:
            try:
                text = self._call_model(model, prompt)
                meta = _parse_meta_json(text)
                if meta:
                    return meta
                errors.append(f"{model}: レスポンスのJSON解釈に失敗")
            except urllib.error.HTTPError as e:
                errors.append(f"{model}: HTTP {e.code}")
                print(f"    [llm] {model} が HTTP {e.code} — 次のモデルへフォールバック", file=sys.stderr)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                errors.append(f"{model}: {e}")
                print(f"    [llm] {model} で通信エラー — 次のモデルへフォールバック: {e}", file=sys.stderr)
        raise LLMError("全モデルで生成に失敗: " + "; ".join(errors))

    def _call_model(self, model: str, prompt: str) -> str:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
        # Gemma系はresponseMimeType(JSONモード)非対応
        if "gemma" not in model.lower():
            payload["generationConfig"]["responseMimeType"] = "application/json"

        req = urllib.request.Request(
            GEMINI_ENDPOINT.format(model=model),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        last_err: Exception | None = None
        for attempt in range(2):  # 一時的な429/503は1回だけ待って再試行
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                self._sleep()
                parts = data["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts)
            except urllib.error.HTTPError as e:
                last_err = e
                self._sleep()
                if e.code in (429, 500, 503) and attempt == 0:
                    time.sleep(max(self.sleep_seconds, 10))
                    continue
                raise
            except (KeyError, IndexError) as e:
                # candidatesが空(セーフティブロック等)
                raise json.JSONDecodeError(f"unexpected response shape: {e}", "", 0)
        raise last_err  # 到達しないが型のため

    def _sleep(self):
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)


class MockClient(LLMClient):
    """外部APIを呼ばないローカル検証用クライアント(DRY_RUN=1で使用)。"""

    def generate_note_meta(self, url: str, title_hint: str, body: str) -> dict:
        lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
        title = title_hint or (lines[0][:30] if lines else url[:30]) or "無題"
        title = re.sub(r"^#+\s*", "", title)[:30]
        summary = "\n".join(lines[:3])[:200] or "(本文なし)"
        return {"title": title, "summary": summary, "tags": ["未分類", "mock"]}


def _parse_meta_json(text: str) -> dict | None:
    """LLM出力からJSONを取り出して検証する。Gemma等が前後に文字を付けても拾う。"""
    candidates = [text.strip()]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        # ```json ... ``` フェンスを剥がす
        cand = re.sub(r"^```(?:json)?\s*|\s*```$", "", cand.strip())
        try:
            # strict=False: 文字列中の生改行(Gemmaのプロンプトモード出力)を許容
            obj = json.loads(cand, strict=False)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        title = str(obj.get("title", "")).strip()
        summary = str(obj.get("summary", "")).strip()
        tags = obj.get("tags", [])
        if not title or not summary or not isinstance(tags, list):
            continue
        tags = [re.sub(r"\s+", "-", str(t).strip()) for t in tags if str(t).strip()]
        if not tags:
            continue
        return {"title": title, "summary": summary, "tags": tags[:5]}
    return None


def create_client() -> LLMClient:
    """環境変数に基づいてLLMクライアントを生成する。"""
    if os.environ.get("DRY_RUN") == "1":
        return MockClient()
    chain = [
        m.strip()
        for m in (os.environ.get("LLM_MODEL_CHAIN") or DEFAULT_MODEL_CHAIN).split(",")
        if m.strip()
    ]
    sleep_seconds = float(os.environ.get("LLM_SLEEP_SECONDS") or DEFAULT_SLEEP_SECONDS)
    return GeminiClient(os.environ.get("GEMINI_API_KEY", ""), chain, sleep_seconds)
