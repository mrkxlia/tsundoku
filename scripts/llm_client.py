"""LLM呼び出しモジュール。

要約・タグ生成のLLM呼び出しをこのモジュールに集約する。
将来ClaudeやOpenAIに差し替える場合は LLMClient を実装したクラスを追加し、
create_client() の分岐を変えるだけでよい。

環境変数:
    GEMINI_API_KEY     : Google AI Studio のAPIキー(必須。DRY_RUN時は不要)
    LLM_MODEL_CHAIN    : カンマ区切りのモデル名。先頭から順に試し、
                         枠超過(429)等で次のモデルへフォールバックする
    LLM_SLEEP_SECONDS  : API呼び出し後のスリープ秒数(無料枠のRPM対策)
    EMBEDDING_MODEL    : 埋め込みモデル名(既定 gemini-embedding-2)
    EMBED_DIM          : 埋め込み次元数(既定 768)
    EMBED_SLEEP_SECONDS: 埋め込みAPI呼び出し後のスリープ秒数(生成系とは別枠のため独立変数)
    DRY_RUN            : "1" で外部APIを呼ばないモッククライアントを使う
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
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

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-2"
DEFAULT_EMBED_DIM = 768
DEFAULT_EMBED_SLEEP_SECONDS = 6.0
EMBED_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"

SHELF_LIFE_INSTRUCTION = """- shelf_life は記事の情報が陳腐化するまでの目安期間を次の3値から選ぶこと
  - "short": 速報・ニュース・キャンペーン・価格等、数日〜数週間で古くなる情報
  - "medium": 技術トレンド・製品情報・統計等、数か月〜1年程度で古くなる情報
  - "long": 原理解説・リファレンス・歴史等、長期間陳腐化しない情報"""

PROMPT_TEMPLATE = """あなたはWebクリップ記事を整理する司書です。以下の記事を読み、次のJSONだけを出力してください。JSON以外の文字は一切出力しないでください。

{{"title": "内容を表す簡潔な日本語タイトル(30字以内)", "summary": "記事の要約(日本語で3行程度。行は\\nで区切る)", "tags": ["タグ1", "タグ2", "タグ3"], "shelf_life": "short/medium/longのいずれか"}}

制約:
- tags は3〜5個。日本語または英小文字で、スペースを含めないこと(例: "生成ai", "プログラミング", "キャリア")
- title にはファイル名に使えない記号(/ \\ : * ? " < > |)を使わないこと
- 本文が無い場合はURLから推測できる範囲で構わない
{shelf_life_instruction}

URL: {url}
タイトルのヒント: {title_hint}
本文:
{body}
"""

PDF_PROMPT_TEMPLATE = """あなたはWebクリップを整理する司書です。添付のスライドPDFを読み、次のJSONだけを出力してください。JSON以外の文字は一切出力しないでください。

{{"title": "内容を表す簡潔な日本語タイトル(30字以内)", "summary": "スライドの要約(日本語で3行程度。行は\\nで区切る)", "tags": ["タグ1", "タグ2", "タグ3"], "shelf_life": "short/medium/longのいずれか"}}

制約:
- tags は3〜5個。日本語または英小文字で、スペースを含めないこと(例: "生成ai", "プログラミング", "キャリア")
- title にはファイル名に使えない記号(/ \\ : * ? " < > |)を使わないこと
{shelf_life_instruction}

URL: {url}
タイトルのヒント: {title_hint}
"""

IMAGE_PROMPT_TEMPLATE = """あなたはWebクリップを整理する司書です。添付された{count}枚の画像について、添付順に、それぞれ次の形式で日本語で出力してください。出力はこの形式のテキストのみとし、前置きや後書きは不要です。

### 画像1
(画像の内容の説明を1〜2文。続けて、画像内に文字があればその全文を書き起こす。文字がなければ書き起こしは省略)

### 画像2
(以下同様)

URL: {url}
"""

VIDEO_PROMPT_TEMPLATE = """あなたはWebクリップを整理する司書です。添付の動画の内容を確認し、次のJSONだけを出力してください。JSON以外の文字は一切出力しないでください。

{{"title": "内容を表す簡潔な日本語タイトル(30字以内)", "summary": "動画内容の要約(日本語で3行程度。行は\\nで区切る)", "tags": ["タグ1", "タグ2", "タグ3"], "shelf_life": "short/medium/longのいずれか"}}

制約:
- tags は3〜5個。日本語または英小文字で、スペースを含めないこと(例: "生成ai", "プログラミング", "キャリア")
- title にはファイル名に使えない記号(/ \\ : * ? " < > |)を使わないこと
{shelf_life_instruction}

URL: {url}
タイトルのヒント: {title_hint}
"""

SHELF_LIFE_CLASSIFY_TEMPLATE = """あなたはWebクリップ記事を整理する司書です。以下の記事のタイトルと要約から、情報が陳腐化するまでの目安期間を判定し、次のJSONだけを出力してください。JSON以外の文字は一切出力しないでください。

{{"shelf_life": "short/medium/longのいずれか"}}

判定基準:
{shelf_life_instruction}

タイトル: {title}
要約:
{summary}
"""

SUPERSESSION_JUDGE_TEMPLATE = """あなたはWebクリップ記事を整理する司書です。新しい記事(new)が、古い記事(old)の内容を更新・上書きしている、\
または明確に矛盾する情報を含んでいるかを判定してください。単に話題が似ているだけ、関連トピックというだけでは\
supersedesはfalseとしてください。次のJSONだけを出力してください。JSON以外の文字は一切出力しないでください。

{{"supersedes": true または false, "reason": "判定理由(日本語1文)"}}

[new] タイトル: {new_title}
[new] 要約: {new_summary}
[new] 本文抜粋:
{new_excerpt}

[old] タイトル: {old_title}
[old] 要約: {old_summary}
[old] 本文抜粋:
{old_excerpt}
"""

MERGE_JUDGE_TEMPLATE = """あなたはWebクリップ記事を整理する司書です。2つの記事(A, B)が同一トピックについて\
密接に関連する内容であり、1つのノートに統合すべきかを判定してください。単に話題が近い・\
カテゴリが同じというだけではmergeはfalseとしてください(例: 同じ製品カテゴリの別サービス紹介、\
同じ技術領域の別トピックの解説はfalse)。統合すべきなのは、内容の主題が実質的に同一、\
片方がもう片方の断片的な言及に過ぎない、続報・詳細版の関係にある、といった場合です。\
次のJSONだけを出力してください。JSON以外の文字は一切出力しないでください。

{{"merge": true または false, "reason": "判定理由(日本語1文)"}}

[A] タイトル: {a_title}
[A] 要約: {a_summary}
[A] 本文抜粋:
{a_excerpt}

[B] タイトル: {b_title}
[B] 要約: {b_summary}
[B] 本文抜粋:
{b_excerpt}
"""

MERGE_META_TEMPLATE = """あなたはWebクリップ記事を整理する司書です。2つの記事を1つのノートに統合しました。\
統合後の本文(結合済み、末尾に統合元記事の内容を含む)を読み、新しい要約とタグを次のJSONだけで\
出力してください。JSON以外の文字は一切出力しないでください。

{{"summary": "統合後の内容を表す要約(日本語で3行程度。行は\\nで区切る)", "tags": ["タグ1", "タグ2", "タグ3"]}}

制約:
- tags は3〜5個。**必ず次の候補タグ一覧から選ぶこと(新規のタグを作らないこと)**
- 候補になければ最も近い意味の候補を選ぶ。候補が3個未満の場合はそのまま全部使う

タイトル: {title}
候補タグ一覧: {candidate_tags}
統合後本文(抜粋):
{merged_body_excerpt}
"""


class LLMError(Exception):
    """全モデルで生成に失敗した場合に送出される。"""


class LLMClient:
    """要約・タグ生成のインターフェース。"""

    def generate_note_meta(self, url: str, title_hint: str, body: str) -> dict:
        """クリップ1件から {"title": str, "summary": str, "tags": [str]} を返す。"""
        raise NotImplementedError

    def generate_note_meta_from_pdf(self, url: str, title_hint: str, pdf_bytes: bytes) -> dict:
        """PDF(スライド等)を入力として同じ形式のメタ情報を返す。"""
        raise NotImplementedError

    def generate_note_meta_from_video(self, url: str, title_hint: str, video_uri: str) -> dict:
        """YouTube動画URLを直接入力として同じ形式のメタ情報を返す。"""
        raise NotImplementedError

    def describe_images(self, url: str, images: list[tuple[bytes, str]]) -> str:
        """画像[(bytes, mime), ...]の説明+OCR全文を日本語フリーテキストで返す。"""
        raise NotImplementedError

    def embed_content(self, parts: list[dict]) -> list[float]:
        """テキスト(+画像等)のpartsから正規化済み埋め込みベクトルを返す。"""
        raise NotImplementedError

    def classify_shelf_life(self, title: str, summary: str) -> str:
        """既存ノート(タイトル+要約)から shelf_life ("short"/"medium"/"long") を判定する。"""
        raise NotImplementedError

    def judge_supersession(
        self,
        new_title: str,
        new_summary: str,
        new_excerpt: str,
        old_title: str,
        old_summary: str,
        old_excerpt: str,
    ) -> dict:
        """新ノートが旧ノートを上書き/矛盾させるかを判定し {"supersedes": bool, "reason": str} を返す。"""
        raise NotImplementedError

    def judge_merge(
        self,
        a_title: str,
        a_summary: str,
        a_excerpt: str,
        b_title: str,
        b_summary: str,
        b_excerpt: str,
    ) -> dict:
        """2ノートが統合すべき関係にあるかを判定し {"merge": bool, "reason": str} を返す。"""
        raise NotImplementedError

    def generate_merged_meta(
        self, title: str, merged_body_excerpt: str, candidate_tags: list[str]
    ) -> dict:
        """統合後本文から {"summary": str, "tags": [str]} を返す(tagsはcandidate_tagsから選択)。"""
        raise NotImplementedError


def l2_normalize(values: list[float]) -> list[float]:
    """非デフォルト次元指定時はAPI側が自動再正規化するとされているが、手動での
    再正規化は冪等(既に単位ベクトルなら無害)なため保険として常に適用する。"""
    norm = math.sqrt(sum(v * v for v in values))
    return values if norm == 0 else [v / norm for v in values]


class GeminiClient(LLMClient):
    """Google AI Studio (Generative Language API) をRESTで直接呼ぶ実装。

    モデルチェーンの先頭から順に試し、レート制限(429)やサーバエラーで
    次のモデルへフォールバックする。Gemma系モデルはJSONモード非対応のため
    プロンプト内指示 + レスポンスからのJSON抽出で対応する。
    """

    def __init__(
        self,
        api_key: str,
        model_chain: list[str],
        sleep_seconds: float,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        embed_dim: int = DEFAULT_EMBED_DIM,
        embed_sleep_seconds: float = DEFAULT_EMBED_SLEEP_SECONDS,
    ):
        if not api_key:
            raise LLMError("GEMINI_API_KEY が設定されていません")
        self.api_key = api_key
        self.model_chain = model_chain
        self.sleep_seconds = sleep_seconds
        self.embedding_model = embedding_model
        self.embed_dim = embed_dim
        self.embed_sleep_seconds = embed_sleep_seconds

    def generate_note_meta(self, url: str, title_hint: str, body: str) -> dict:
        prompt = PROMPT_TEMPLATE.format(
            url=url,
            title_hint=title_hint or "(なし)",
            body=(body or "(本文なし)")[:MAX_BODY_CHARS],
            shelf_life_instruction=SHELF_LIFE_INSTRUCTION,
        )
        return self._generate_with_parts([{"text": prompt}], self.model_chain)

    def generate_note_meta_from_pdf(self, url: str, title_hint: str, pdf_bytes: bytes) -> dict:
        prompt = PDF_PROMPT_TEMPLATE.format(
            url=url, title_hint=title_hint or "(なし)", shelf_life_instruction=SHELF_LIFE_INSTRUCTION
        )
        parts = [
            {"text": prompt},
            {
                "inline_data": {
                    "mime_type": "application/pdf",
                    "data": base64.b64encode(pdf_bytes).decode("ascii"),
                }
            },
        ]
        return self._generate_with_parts(parts, self._multimodal_chain())

    def generate_note_meta_from_video(self, url: str, title_hint: str, video_uri: str) -> dict:
        prompt = VIDEO_PROMPT_TEMPLATE.format(
            url=url, title_hint=title_hint or "(なし)", shelf_life_instruction=SHELF_LIFE_INSTRUCTION
        )
        parts = [{"text": prompt}, {"file_data": {"file_uri": video_uri}}]
        # 動画はトークン消費が大きいため低解像度で処理する
        return self._generate_with_parts(
            parts, self._multimodal_chain(), media_resolution="MEDIA_RESOLUTION_LOW"
        )

    def describe_images(self, url: str, images: list[tuple[bytes, str]]) -> str:
        prompt = IMAGE_PROMPT_TEMPLATE.format(url=url, count=len(images))
        parts: list[dict] = [{"text": prompt}]
        parts += [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}}
            for data, mime in images
        ]
        # OCRには既定解像度が必要なため mediaResolution は指定しない
        return self._generate_text_with_parts(parts, self._multimodal_chain())

    def embed_content(self, parts: list[dict]) -> list[float]:
        payload = {
            "content": {"parts": parts},
            "outputDimensionality": self.embed_dim,
        }
        req = urllib.request.Request(
            EMBED_ENDPOINT.format(model=self.embedding_model),
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
                if self.embed_sleep_seconds > 0:
                    time.sleep(self.embed_sleep_seconds)
                values = data["embedding"]["values"]
                return l2_normalize(values)
            except urllib.error.HTTPError as e:
                last_err = e
                if self.embed_sleep_seconds > 0:
                    time.sleep(self.embed_sleep_seconds)
                if e.code in (429, 500, 503) and attempt == 0:
                    time.sleep(max(self.embed_sleep_seconds, 10))
                    continue
                raise LLMError(f"embed_content失敗: HTTP {e.code}")
            except (KeyError, IndexError) as e:
                raise LLMError(f"embed_content失敗: 想定外のレスポンス形式: {e}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                raise LLMError(f"embed_content失敗: {e}")
        raise LLMError(f"embed_content失敗: {last_err}")

    def classify_shelf_life(self, title: str, summary: str) -> str:
        prompt = SHELF_LIFE_CLASSIFY_TEMPLATE.format(
            shelf_life_instruction=SHELF_LIFE_INSTRUCTION, title=title, summary=summary or "(要約なし)"
        )
        errors = []
        for model in self.model_chain:
            try:
                text = self._call_model(model, [{"text": prompt}])
                value = _parse_shelf_life_json(text)
                if value:
                    return value
                errors.append(f"{model}: レスポンスのJSON解釈に失敗")
            except urllib.error.HTTPError as e:
                errors.append(f"{model}: HTTP {e.code}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                errors.append(f"{model}: {e}")
        raise LLMError("classify_shelf_life失敗: " + "; ".join(errors))

    def judge_supersession(
        self,
        new_title: str,
        new_summary: str,
        new_excerpt: str,
        old_title: str,
        old_summary: str,
        old_excerpt: str,
    ) -> dict:
        prompt = SUPERSESSION_JUDGE_TEMPLATE.format(
            new_title=new_title,
            new_summary=new_summary,
            new_excerpt=(new_excerpt or "")[:MAX_BODY_CHARS],
            old_title=old_title,
            old_summary=old_summary,
            old_excerpt=(old_excerpt or "")[:MAX_BODY_CHARS],
        )
        errors = []
        for model in self.model_chain:
            try:
                text = self._call_model(model, [{"text": prompt}])
                result = _parse_supersession_json(text)
                if result is not None:
                    return result
                errors.append(f"{model}: レスポンスのJSON解釈に失敗")
            except urllib.error.HTTPError as e:
                errors.append(f"{model}: HTTP {e.code}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                errors.append(f"{model}: {e}")
        raise LLMError("judge_supersession失敗: " + "; ".join(errors))

    def judge_merge(
        self,
        a_title: str,
        a_summary: str,
        a_excerpt: str,
        b_title: str,
        b_summary: str,
        b_excerpt: str,
    ) -> dict:
        prompt = MERGE_JUDGE_TEMPLATE.format(
            a_title=a_title,
            a_summary=a_summary,
            a_excerpt=(a_excerpt or "")[:MAX_BODY_CHARS],
            b_title=b_title,
            b_summary=b_summary,
            b_excerpt=(b_excerpt or "")[:MAX_BODY_CHARS],
        )
        errors = []
        for model in self.model_chain:
            try:
                text = self._call_model(model, [{"text": prompt}])
                result = _parse_merge_json(text)
                if result is not None:
                    return result
                errors.append(f"{model}: レスポンスのJSON解釈に失敗")
            except urllib.error.HTTPError as e:
                errors.append(f"{model}: HTTP {e.code}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                errors.append(f"{model}: {e}")
        raise LLMError("judge_merge失敗: " + "; ".join(errors))

    def generate_merged_meta(
        self, title: str, merged_body_excerpt: str, candidate_tags: list[str]
    ) -> dict:
        prompt = MERGE_META_TEMPLATE.format(
            title=title,
            candidate_tags=", ".join(candidate_tags),
            merged_body_excerpt=(merged_body_excerpt or "")[:MAX_BODY_CHARS],
        )
        errors = []
        for model in self.model_chain:
            try:
                text = self._call_model(model, [{"text": prompt}])
                meta = _parse_merged_meta_json(text, candidate_tags)
                if meta:
                    return meta
                errors.append(f"{model}: レスポンスのJSON解釈に失敗")
            except urllib.error.HTTPError as e:
                errors.append(f"{model}: HTTP {e.code}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                errors.append(f"{model}: {e}")
        raise LLMError("generate_merged_meta失敗: " + "; ".join(errors))

    def _multimodal_chain(self) -> list[str]:
        # Gemma系はPDF・動画・画像入力に非対応
        return [m for m in self.model_chain if "gemma" not in m.lower()]

    def _generate_with_parts(
        self, parts: list[dict], chain: list[str], media_resolution: str | None = None
    ) -> dict:
        if not chain:
            raise LLMError("PDF/動画入力に対応するモデルがチェーンにありません")
        errors = []
        for model in chain:
            try:
                text = self._call_model(model, parts, media_resolution=media_resolution)
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

    def _generate_text_with_parts(
        self, parts: list[dict], chain: list[str], media_resolution: str | None = None
    ) -> str:
        """JSONスキーマを課さないフリーテキスト生成(画像説明用)。"""
        if not chain:
            raise LLMError("マルチモーダル入力に対応するモデルがチェーンにありません")
        errors = []
        for model in chain:
            try:
                text = self._call_model(
                    model, parts, media_resolution=media_resolution, json_mode=False
                ).strip()
                if text:
                    return text
                errors.append(f"{model}: 空のレスポンス")
            except urllib.error.HTTPError as e:
                errors.append(f"{model}: HTTP {e.code}")
                print(f"    [llm] {model} が HTTP {e.code} — 次のモデルへフォールバック", file=sys.stderr)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                errors.append(f"{model}: {e}")
                print(f"    [llm] {model} で通信エラー — 次のモデルへフォールバック: {e}", file=sys.stderr)
        raise LLMError("全モデルで生成に失敗: " + "; ".join(errors))

    def _call_model(
        self,
        model: str,
        parts: list[dict],
        media_resolution: str | None = None,
        json_mode: bool = True,
    ) -> str:
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.3},
        }
        # Gemma系はresponseMimeType(JSONモード)非対応
        if json_mode and "gemma" not in model.lower():
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if media_resolution:
            payload["generationConfig"]["mediaResolution"] = media_resolution

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
        return {"title": title, "summary": summary, "tags": ["未分類", "mock"], "shelf_life": self._mock_shelf_life(url)}

    def generate_note_meta_from_pdf(self, url: str, title_hint: str, pdf_bytes: bytes) -> dict:
        title = (title_hint or url)[:30] or "無題"
        return {
            "title": title,
            "summary": "(PDFモック要約)",
            "tags": ["未分類", "mock-pdf"],
            "shelf_life": self._mock_shelf_life(url),
        }

    def generate_note_meta_from_video(self, url: str, title_hint: str, video_uri: str) -> dict:
        title = (title_hint or url)[:30] or "無題"
        return {
            "title": title,
            "summary": "(動画モック要約)",
            "tags": ["未分類", "mock-video"],
            "shelf_life": self._mock_shelf_life(url),
        }

    def describe_images(self, url: str, images: list[tuple[bytes, str]]) -> str:
        return "\n\n".join(f"### 画像{i}\n(画像モック説明)" for i in range(1, len(images) + 1))

    def embed_content(self, parts: list[dict]) -> list[float]:
        # テキスト内容のハッシュから決定的な単位ベクトルを生成する(同じ入力は常に同じベクトル、
        # 異なる入力は異なるベクトルになるため、検索ロジック自体のテストに使える)。
        text = " ".join(p.get("text", "") for p in parts if "text" in p)
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        raw = [digest[i % len(digest)] / 255.0 * 2 - 1 for i in range(DEFAULT_EMBED_DIM)]
        return l2_normalize(raw)

    def classify_shelf_life(self, title: str, summary: str) -> str:
        return self._mock_shelf_life(title)

    def judge_supersession(
        self,
        new_title: str,
        new_summary: str,
        new_excerpt: str,
        old_title: str,
        old_summary: str,
        old_excerpt: str,
    ) -> dict:
        # 決定的な検証用: タイトルが同一なら上書きとみなす(実運用ではLLMが判定)
        return {"supersedes": new_title == old_title, "reason": "(mock判定)"}

    def judge_merge(
        self,
        a_title: str,
        a_summary: str,
        a_excerpt: str,
        b_title: str,
        b_summary: str,
        b_excerpt: str,
    ) -> dict:
        # 決定的な検証用: タイトルが同一なら統合対象とみなす(実運用ではLLMが判定)
        return {"merge": a_title == b_title, "reason": "(mock判定)"}

    def generate_merged_meta(
        self, title: str, merged_body_excerpt: str, candidate_tags: list[str]
    ) -> dict:
        lines = [ln.strip() for ln in (merged_body_excerpt or "").splitlines() if ln.strip()]
        summary = "\n".join(lines[:3])[:200] or "(統合後本文なし)"
        return {"summary": summary, "tags": list(candidate_tags)[:5] or ["未分類"]}

    @staticmethod
    def _mock_shelf_life(seed: str) -> str:
        digest = hashlib.sha256((seed or "").encode("utf-8")).digest()
        return VALID_SHELF_LIVES[digest[0] % len(VALID_SHELF_LIVES)]


VALID_SHELF_LIVES = ("short", "medium", "long")


def _extract_json_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        candidates.append(m.group(0))
    # ```json ... ``` フェンスを剥がす
    return [re.sub(r"^```(?:json)?\s*|\s*```$", "", c.strip()) for c in candidates]


def _parse_meta_json(text: str) -> dict | None:
    """LLM出力からJSONを取り出して検証する。Gemma等が前後に文字を付けても拾う。"""
    for cand in _extract_json_candidates(text):
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
        shelf_life = str(obj.get("shelf_life", "")).strip()
        if shelf_life not in VALID_SHELF_LIVES:
            shelf_life = "medium"  # モデルが省略/不正値を返した場合の安全側フォールバック
        return {"title": title, "summary": summary, "tags": tags[:5], "shelf_life": shelf_life}
    return None


def _parse_shelf_life_json(text: str) -> str | None:
    for cand in _extract_json_candidates(text):
        try:
            obj = json.loads(cand, strict=False)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        value = str(obj.get("shelf_life", "")).strip()
        if value in VALID_SHELF_LIVES:
            return value
    return None


def _parse_supersession_json(text: str) -> dict | None:
    for cand in _extract_json_candidates(text):
        try:
            obj = json.loads(cand, strict=False)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("supersedes"), bool):
            continue
        return {"supersedes": obj["supersedes"], "reason": str(obj.get("reason", "")).strip()}
    return None


def _parse_merge_json(text: str) -> dict | None:
    for cand in _extract_json_candidates(text):
        try:
            obj = json.loads(cand, strict=False)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("merge"), bool):
            continue
        return {"merge": obj["merge"], "reason": str(obj.get("reason", "")).strip()}
    return None


def _parse_merged_meta_json(text: str, candidate_tags: list[str]) -> dict | None:
    """generate_merged_meta()の出力を検証する。tagsは候補タグ一覧に含まれるものだけを
    採用する(LLMが候補外の新規タグを生成した場合の防御)。"""
    candidate_set = {re.sub(r"\s+", "-", str(t).strip()) for t in candidate_tags}
    for cand in _extract_json_candidates(text):
        try:
            obj = json.loads(cand, strict=False)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        summary = str(obj.get("summary", "")).strip()
        tags_raw = obj.get("tags", [])
        if not summary or not isinstance(tags_raw, list):
            continue
        tags = [re.sub(r"\s+", "-", str(t).strip()) for t in tags_raw if str(t).strip()]
        tags = [t for t in tags if t in candidate_set] or list(dict.fromkeys(candidate_tags))[:5]
        if not tags:
            continue
        return {"summary": summary, "tags": tags[:5]}
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
    embedding_model = os.environ.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
    embed_dim = int(os.environ.get("EMBED_DIM") or DEFAULT_EMBED_DIM)
    embed_sleep_seconds = float(os.environ.get("EMBED_SLEEP_SECONDS") or DEFAULT_EMBED_SLEEP_SECONDS)
    return GeminiClient(
        os.environ.get("GEMINI_API_KEY", ""),
        chain,
        sleep_seconds,
        embedding_model,
        embed_dim,
        embed_sleep_seconds,
    )
