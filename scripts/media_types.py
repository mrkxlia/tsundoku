"""URL種別判定とメディア系コンテンツ取得モジュール。

URLから type(video/slides/post/image/pdf/article)を判定し、種別ごとに
oEmbed等でタイトル・本文・要約用コンテンツを取得する。

方針:
- ノートに保存する本文(note_body)とLLMに渡す入力(llm_body)を分離する。
  字幕やPDFはLLM入力にのみ使い、vaultには書き込まない(リポジトリ肥大防止)
- PDFはメモリ上のbytesのみで扱い、ディスクにも書かない
- 外部アクセスは全てソフトフェイル: 失敗しても needs-review タグを付けて続行し、
  ワークフロー全体は落とさない
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

FETCH_TIMEOUT = 15
PDF_TIMEOUT = 60
MAX_PDF_BYTES = 15 * 1024 * 1024  # これ以上のPDFは要約せず needs-review に落とす
MAX_TRANSCRIPT_CHARS = 24000  # 字幕は本文より長くなりがちなので専用の上限を設ける
MAX_PAGE_BYTES = 2 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; tsundoku-organizer)"

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".heic")

YOUTUBE_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")
NICONICO_ID_RE = re.compile(r"(?:watch/|nico\.ms/)((?:sm|so|nm)?\d+)")
SPEAKERDECK_PDF_RES = (
    re.compile(r'href="(https://files\.speakerdeck\.com/[^"]+\.pdf[^"]*)"'),
    re.compile(r'"(https://speakerd\.s3\.amazonaws\.com/[^"]+\.pdf[^"]*)"'),
)


@dataclass
class MediaInfo:
    type: str  # video / slides / post / image / pdf / article
    note_body: str  # ノートに保存する本文
    llm_body: str  # LLMに渡す本文(コンテキスト行 + 字幕など)
    extra_tags: list[str] = field(default_factory=list)  # needs-review, has-media
    pdf: bytes | None = None  # Gemini inline入力用のPDF(ディスクには書かない)
    video_uri: str | None = None  # Gemini動画入力用のYouTube正規URL(字幕が取れない場合)
    title_hint: str = ""  # oEmbed等から得たタイトル(クリップ側にヒントが無い場合に使う)


# ---------------------------------------------------------------- 種別判定

def _host(url: str) -> str:
    host = urllib.parse.urlsplit(url).netloc.lower()
    for prefix in ("www.", "m.", "mobile.", "sp."):
        host = host.removeprefix(prefix)
    return host


def _is_youtube(host: str) -> bool:
    return host in ("youtube.com", "music.youtube.com", "youtu.be")


def _is_vimeo(host: str) -> bool:
    return host == "vimeo.com" or host.endswith(".vimeo.com")


def _is_niconico(host: str) -> bool:
    return host in ("nicovideo.jp", "nico.ms") or host.endswith(".nicovideo.jp")


def _is_slideshare(host: str) -> bool:
    return host == "slideshare.net" or host.endswith(".slideshare.net")


def is_x_url(url: str) -> bool:
    return _host(url) in ("x.com", "twitter.com")


def detect_media_type(url: str) -> str:
    host = _host(url)
    if _is_youtube(host) or _is_vimeo(host) or _is_niconico(host):
        return "video"
    if host in ("speakerdeck.com", "docswell.com") or _is_slideshare(host):
        return "slides"
    if is_x_url(url):
        return "post"
    path = urllib.parse.urlsplit(url).path.lower()
    if path.endswith(IMAGE_SUFFIXES):
        return "image"
    if path.endswith(".pdf"):
        return "pdf"
    return "article"


def extract_youtube_id(url: str) -> str | None:
    """watch?v= / youtu.be / shorts / live / embed から動画IDを取り出す。"""
    host = _host(url)
    p = urllib.parse.urlsplit(url)
    if host == "youtu.be":
        cand = p.path.lstrip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com"):
        if p.path == "/watch":
            cand = dict(urllib.parse.parse_qsl(p.query)).get("v", "")
        else:
            m = re.match(r"^/(?:shorts|live|embed|v)/([^/?]+)", p.path)
            cand = m.group(1) if m else ""
    else:
        return None
    return cand if YOUTUBE_ID_RE.fullmatch(cand) else None


# ---------------------------------------------------------------- 取得ヘルパ

def _fetch_json(api_url: str, label: str) -> dict | None:
    req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = json.load(resp)
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"    [media] {label} 取得失敗: {e}", file=sys.stderr)
        return None


def _fetch_text(url: str, label: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            return resp.read(MAX_PAGE_BYTES).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [media] {label} 取得失敗: {e}", file=sys.stderr)
        return ""


def _download_pdf(pdf_url: str) -> bytes | None:
    req = urllib.request.Request(pdf_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=PDF_TIMEOUT) as resp:
            length = resp.headers.get("Content-Length")
            if length and int(length) > MAX_PDF_BYTES:
                print(f"    [media] PDFがサイズ上限超過({length}バイト)", file=sys.stderr)
                return None
            data = resp.read(MAX_PDF_BYTES + 1)
    except Exception as e:
        print(f"    [media] PDF取得失敗: {e}", file=sys.stderr)
        return None
    if len(data) > MAX_PDF_BYTES:
        print("    [media] PDFがサイズ上限超過", file=sys.stderr)
        return None
    if not data.startswith(b"%PDF"):
        print("    [media] PDF形式でないため破棄", file=sys.stderr)
        return None
    return data


def _compose(context: list[str], *sections: str) -> str:
    parts = ["\n".join(c for c in context if c)] if context else []
    parts += [s for s in sections if s and s.strip()]
    return "\n\n".join(p for p in parts if p).strip()


def _add_tag(info: MediaInfo, tag: str) -> None:
    if tag not in info.extra_tags:
        info.extra_tags.append(tag)


# ---------------------------------------------------------------- YouTube

def fetch_youtube_transcript(video_id: str) -> str:
    """字幕を取得する(ja優先、なければen。手動字幕優先で自動生成も可)。

    YouTubeはクラウドIPからのアクセスをブロックすることが多いため、
    あらゆる失敗を日常的なソフトフェイルとして扱う(呼び出し側で動画入力へフォールバック)。
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["ja", "en"])
        text = " ".join(snippet.text for snippet in fetched)
        return re.sub(r"\s+", " ", text).strip()[:MAX_TRANSCRIPT_CHARS]
    except Exception as e:
        print(f"    [media] YouTube字幕取得失敗(動画入力へフォールバック): {e}", file=sys.stderr)
        return ""


def _enrich_youtube(url: str, info: MediaInfo) -> None:
    context = []
    oe = _fetch_json(
        "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"url": url, "format": "json"}),
        "YouTube oEmbed",
    )
    if oe:
        info.title_hint = str(oe.get("title", "")).strip()
        if info.title_hint:
            context.append(f"動画タイトル: {info.title_hint}")
        author = str(oe.get("author_name", "")).strip()
        if author:
            context.append(f"チャンネル: {author}")

    video_id = extract_youtube_id(url)
    if not video_id:  # playlist/チャンネルURL等は動画単体として扱えない
        info.llm_body = _compose(context, info.note_body)
        _add_tag(info, "needs-review")
        return
    transcript = fetch_youtube_transcript(video_id)
    if transcript:
        info.llm_body = _compose(context, info.note_body, "字幕:\n" + transcript)
    else:
        # 2段目: Gemini動画入力(file_uri)で要約を試みる。失敗時は呼び出し側でneeds-review
        info.video_uri = f"https://www.youtube.com/watch?v={video_id}"
        info.llm_body = _compose(context, info.note_body)


def _enrich_video(url: str, info: MediaInfo) -> None:
    host = _host(url)
    if _is_youtube(host):
        _enrich_youtube(url, info)
        return

    context = []
    if _is_vimeo(host):
        oe = _fetch_json(
            "https://vimeo.com/api/oembed.json?" + urllib.parse.urlencode({"url": url}),
            "Vimeo oEmbed",
        )
        if oe:
            info.title_hint = str(oe.get("title", "")).strip()
            if info.title_hint:
                context.append(f"動画タイトル: {info.title_hint}")
            author = str(oe.get("author_name", "")).strip()
            if author:
                context.append(f"作者: {author}")
    else:  # ニコニコ動画
        m = NICONICO_ID_RE.search(url)
        if m:
            xml = _fetch_text(f"https://ext.nicovideo.jp/api/getthumbinfo/{m.group(1)}", "ニコニコ動画情報")
            tm = re.search(r"<title>(.*?)</title>", xml, re.DOTALL)
            if tm:
                info.title_hint = html.unescape(tm.group(1)).strip()
                context.append(f"動画タイトル: {info.title_hint}")
    # Gemini動画入力はYouTube専用のため、タイトル情報のみで needs-review
    info.llm_body = _compose(context, info.note_body)
    _add_tag(info, "needs-review")


# ---------------------------------------------------------------- スライド

def _find_speakerdeck_pdf_url(page_url: str) -> str | None:
    page = _fetch_text(page_url, "SpeakerDeckページ")
    for pattern in SPEAKERDECK_PDF_RES:
        m = pattern.search(page)
        if m:
            return html.unescape(m.group(1))
    return None


def _enrich_slides(url: str, info: MediaInfo) -> None:
    host = _host(url)
    if host == "speakerdeck.com":
        api = "https://speakerdeck.com/oembed.json?" + urllib.parse.urlencode({"url": url})
        label = "SpeakerDeck oEmbed"
    elif _is_slideshare(host):
        api = "https://www.slideshare.net/api/oembed/2?" + urllib.parse.urlencode(
            {"url": url, "format": "json"}
        )
        label = "SlideShare oEmbed"
    else:  # docswell.com
        api = "https://www.docswell.com/service/oembed?" + urllib.parse.urlencode({"url": url})
        label = "Docswell oEmbed"

    context = []
    oe = _fetch_json(api, label)
    if oe:
        info.title_hint = str(oe.get("title", "")).strip()
        if info.title_hint:
            context.append(f"スライドタイトル: {info.title_hint}")
        author = str(oe.get("author_name", "")).strip()
        if author:
            context.append(f"作者: {author}")
    info.llm_body = _compose(context, info.note_body)

    if host == "speakerdeck.com":
        pdf_url = _find_speakerdeck_pdf_url(url)
        info.pdf = _download_pdf(pdf_url) if pdf_url else None
        if info.pdf is None:
            _add_tag(info, "needs-review")
    else:
        # SlideShare/Docswellは自動取得しない(oEmbed情報のみ)
        _add_tag(info, "needs-review")


# ---------------------------------------------------------------- X(Twitter)

def fetch_x_oembed(url: str) -> dict | None:
    """publish.twitter.com/oembed(認証不要)でポスト情報の取得を試みる。"""
    query_url = re.sub(r"//(www\.|mobile\.)?x\.com/", "//twitter.com/", url)
    api = "https://publish.twitter.com/oembed?" + urllib.parse.urlencode(
        {"url": query_url, "omit_script": "1", "lang": "ja"}
    )
    return _fetch_json(api, "x oEmbed")


def x_text_from_html(raw: str) -> str:
    """oEmbedのHTMLから本文テキストを取り出す(帰属情報「— 投稿者 (@id) 日付」を含む)。"""
    text = re.sub(r"<br\s*/?>", "\n", raw)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _enrich_post(url: str, info: MediaInfo) -> None:
    # 本文が既にある場合はoEmbed不要(has-media判定はenrich側で本文スキャン済み)
    if info.note_body:
        return

    oe = fetch_x_oembed(url)
    raw = (oe or {}).get("html", "")
    if "pic.twitter.com" in raw:
        _add_tag(info, "has-media")
    text = x_text_from_html(raw) if raw else ""
    info.note_body = text
    info.llm_body = text
    if not text:
        _add_tag(info, "needs-review")


# ---------------------------------------------------------------- エントリポイント

def enrich(url: str, body: str, dry_run: bool = False) -> MediaInfo:
    """URL種別を判定し、種別に応じたコンテンツ取得を行う唯一のエントリポイント。

    dry_run時は種別判定のみ行い、ネットワークアクセスは一切しない。
    想定外の例外が出ても needs-review を付けて続行し、呼び出し側を落とさない。
    """
    info = MediaInfo(type=detect_media_type(url), note_body=body, llm_body=body)
    if info.type == "image":
        # URLのみ保存。実体は取得しない(LLMはURLからの推測でタイトル・タグを付ける)
        info.llm_body = ""
        info.extra_tags = ["has-media", "needs-review"]
        return info
    if info.type == "post" and "pic.twitter.com" in body:
        # クリップ済み本文にメディアリンクが含まれる場合はネットワーク不要で判定できる
        _add_tag(info, "has-media")
    if dry_run or info.type == "article":
        return info

    try:
        if info.type == "video":
            _enrich_video(url, info)
        elif info.type == "slides":
            _enrich_slides(url, info)
        elif info.type == "post":
            _enrich_post(url, info)
        elif info.type == "pdf":
            info.pdf = _download_pdf(url)
            if info.pdf is None:
                _add_tag(info, "needs-review")
    except Exception as e:  # 取得系の想定外エラーでもワークフローは落とさない
        print(f"    [media] 種別処理でエラー(needs-reviewで続行): {e}", file=sys.stderr)
        info.pdf = None
        info.video_uri = None
        _add_tag(info, "needs-review")
    return info
