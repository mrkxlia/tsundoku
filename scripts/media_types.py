"""URL種別判定とメディア系コンテンツ取得モジュール。

URLから type(video/slides/post/image/pdf/article)を判定し、種別ごとに
oEmbed等でタイトル・本文・要約用コンテンツを取得する。

方針:
- ノートに保存する本文(note_body)とLLMに渡す入力(llm_body)を分離する。
  字幕やPDFはLLM入力にのみ使い、vaultには書き込まない(リポジトリ肥大防止)
- PDF・動画はメモリ上のbytesのみで扱い、ディスクには書かない。
  画像(X添付・直リンク)のみ例外で、bytesをMediaInfo.imagesに載せて
  organize.py側が assets/ に保存する
- 例外: type: slides(Speaker Deck/SlideShare/Docswell)のスライド実体(PDF原本+
  ページ画像)は MediaInfo.slide_pdf / slide_images に載せ、organize.py側が
  vault-assets/(tsundoku-site、private)相当の保存先へ書き出す対象とする。
  第三者コンテンツだがpublicなvaultリポジトリには書き込まないため、上記の
  「ディスクに書かない」原則には抵触しない(実体はprivateなtsundoku-site側で
  管理される。詳細はtsundoku-site側 vault-assets/README.md 参照)
- 外部アクセスは全てソフトフェイル: 失敗しても needs-review タグを付けて続行し、
  ワークフロー全体は落とさない
"""

from __future__ import annotations

import html
import json
import math
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
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # これ以上の画像は保存しない
MAX_IMAGES_PER_NOTE = 4
USER_AGENT = "Mozilla/5.0 (compatible; tsundoku-organizer)"

# スライドのページ画像化(PDFレンダリング・CDN直取得の両方に適用する共通上限)
SLIDE_MAX_PAGES = 120  # これ以上のページを持つデッキは先頭のみ画像化する
SLIDE_IMAGE_WIDTH = 1280  # ページ画像の目標幅(px)。Docswellのプレビュー実測でも1280が
# 実寸(1920x1080)まで綺麗に得られる解像度だったため、Speaker Deck/Docswell 共通で採用
SLIDE_IMAGE_QUALITY = 80  # JPEG品質

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".heic")

YOUTUBE_ID_RE = re.compile(r"^[0-9A-Za-z_-]{11}$")
NICONICO_ID_RE = re.compile(r"(?:watch/|nico\.ms/)((?:sm|so|nm)?\d+)")
SPEAKERDECK_PDF_RES = (
    re.compile(r'href="(https://files\.speakerdeck\.com/[^"]+\.pdf[^"]*)"'),
    re.compile(r'"(https://speakerd\.s3\.amazonaws\.com/[^"]+\.pdf[^"]*)"'),
)
# Docswellはページ内の<form method="POST" action="…/download">経由でPDF実体を取得できる
# (認証・CSRFトークン無しの空POSTで200が返ることを実データで確認済み)。
DOCSWELL_DOWNLOAD_FORM_RE = re.compile(
    r'<form[^>]+method="POST"[^>]+action="(https://www\.docswell\.com/slide/[^"]+/download)"'
)
# PDFダウンロードに失敗した場合のフォールバック用、ページプレビュー画像(サーバレンダリング
# された分のみで全ページ分とは限らない)。?width=クエリで実寸まで拡大できることを確認済み。
DOCSWELL_PAGE_IMAGE_RE = re.compile(r"https://bcdn\.docswell\.com/page/([A-Za-z0-9]+)\.jpg")
# SlideShareはbot対策でサーバ側からのページ取得がほぼ常にブロックされる(実測確認済み)ため、
# クリップ時にブラウザ側で保存済みの本文中URL(image.slidesharecdn.com)を主な取得源とする。
SLIDESHARE_IMAGE_RE = re.compile(r"https://image\.slidesharecdn\.com/[^\s)\]\"'<>]+")
PBS_MEDIA_RE = re.compile(r"https://pbs\.twimg\.com/media/[^\s)\]\"'<>]+")


@dataclass
class ImageAsset:
    data: bytes
    mime: str  # マジックバイトから判定(Content-Typeは信用しない)
    ext: str  # jpg / png / gif / webp
    source_url: str


@dataclass
class MediaInfo:
    type: str  # video / slides / post / image / pdf / article
    note_body: str  # ノートに保存する本文
    llm_body: str  # LLMに渡す本文(コンテキスト行 + 字幕など)
    extra_tags: list[str] = field(default_factory=list)  # needs-review, has-media
    pdf: bytes | None = None  # Gemini inline入力用のPDF(ディスクには書かない)
    video_uri: str | None = None  # Gemini動画入力用のYouTube正規URL(字幕が取れない場合)
    title_hint: str = ""  # oEmbed等から得たタイトル(クリップ側にヒントが無い場合に使う)
    images: list[ImageAsset] = field(default_factory=list)  # assets/保存用(organize.py側で書き出す)
    slide_pdf: bytes | None = None  # スライドPDF原本(vault-assets/への保存用。pdfとは別枠)
    slide_images: list[ImageAsset] = field(default_factory=list)  # スライドのページ画像(同上)


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


def _download_pdf(pdf_url: str, method: str = "GET", post_data: bytes | None = None) -> bytes | None:
    req = urllib.request.Request(
        pdf_url, method=method, data=post_data, headers={"User-Agent": USER_AGENT}
    )
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


def _sniff_image(data: bytes) -> tuple[str, str] | None:
    """マジックバイトから (mime, ext) を判定する。対応外の形式は None。"""
    if data.startswith(b"\xff\xd8\xff"):
        return ("image/jpeg", "jpg")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image/png", "png")
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return ("image/gif", "gif")
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ("image/webp", "webp")
    return None


def _download_image(image_url: str) -> ImageAsset | None:
    req = urllib.request.Request(image_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            length = resp.headers.get("Content-Length")
            if length and int(length) > MAX_IMAGE_BYTES:
                print(f"    [media] 画像がサイズ上限超過({length}バイト): {image_url}", file=sys.stderr)
                return None
            data = resp.read(MAX_IMAGE_BYTES + 1)
    except Exception as e:
        print(f"    [media] 画像取得失敗: {e}", file=sys.stderr)
        return None
    if len(data) > MAX_IMAGE_BYTES:
        print(f"    [media] 画像がサイズ上限超過: {image_url}", file=sys.stderr)
        return None
    sniffed = _sniff_image(data)
    if sniffed is None:
        print(f"    [media] 対応外の画像形式のため破棄: {image_url}", file=sys.stderr)
        return None
    mime, ext = sniffed
    return ImageAsset(data=data, mime=mime, ext=ext, source_url=image_url)


def _download_slide_images(urls: list[str], limit: int) -> list[ImageAsset]:
    """スライドのページ画像URL列を先頭limit件までダウンロードする。1件失敗しても続行する。"""
    images: list[ImageAsset] = []
    for image_url in urls[:limit]:
        asset = _download_image(image_url)
        if asset:
            images.append(asset)
    return images


def _render_pdf_pages(pdf_bytes: bytes, source_url: str) -> list[ImageAsset]:
    """PDFを1ページ1枚のJPEG画像へレンダリングする(スライドをRAG検索・サイト表示に載せるため)。

    重い依存(pymupdf)はこの関数の中でのみ遅延importする。未インストール環境でも
    他の処理は普段どおり動かせるようにするため(既存のyoutube_transcript_apiと同じ方針)。
    """
    try:
        import pymupdf
    except ImportError as e:
        print(f"    [media] pymupdf未インストールのためページ画像化をスキップ: {e}", file=sys.stderr)
        return []

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        print(f"    [media] PDF解析に失敗: {e}", file=sys.stderr)
        return []

    images: list[ImageAsset] = []
    try:
        page_count = min(doc.page_count, SLIDE_MAX_PAGES)
        if doc.page_count > SLIDE_MAX_PAGES:
            print(
                f"    [media] PDFが{doc.page_count}ページ(上限{SLIDE_MAX_PAGES})を超過、"
                f"先頭{SLIDE_MAX_PAGES}ページのみ画像化",
                file=sys.stderr,
            )
        for i in range(page_count):
            page = doc[i]
            width = page.rect.width or 1.0
            zoom = SLIDE_IMAGE_WIDTH / width
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            data = pix.tobytes(output="jpg", jpg_quality=SLIDE_IMAGE_QUALITY)
            images.append(ImageAsset(data=data, mime="image/jpeg", ext="jpg", source_url=source_url))
    except Exception as e:
        print(f"    [media] PDFページ画像化に失敗: {e}", file=sys.stderr)
    finally:
        doc.close()
    return images


def _find_docswell_download_url(page_html: str) -> str | None:
    m = DOCSWELL_DOWNLOAD_FORM_RE.search(page_html)
    return html.unescape(m.group(1)) if m else None


def _find_docswell_page_image_urls(page_html: str) -> list[str]:
    """サーバレンダリングされたページプレビュー画像URLを出現順・重複除去で列挙する
    (全ページ分とは限らない、PDFダウンロード失敗時のフォールバック用)。"""
    ids: list[str] = []
    seen: set[str] = set()
    for image_id in DOCSWELL_PAGE_IMAGE_RE.findall(page_html):
        if image_id in seen:
            continue
        seen.add(image_id)
        ids.append(image_id)
    return [f"https://bcdn.docswell.com/page/{i}.jpg?width={SLIDE_IMAGE_WIDTH}" for i in ids]


def _find_slideshare_image_urls(text: str) -> list[str]:
    """テキスト中の image.slidesharecdn.com 画像URLを出現順・重複除去で列挙する。
    ライブページ取得(bot対策でブロックされがち)とクリップ済み本文(取得元ブラウザが
    保存した画像URLがそのまま残っている)の両方に対して使う共通ヘルパ。"""
    urls: list[str] = []
    seen: set[str] = set()
    for raw in SLIDESHARE_IMAGE_RE.findall(text or ""):
        url = html.unescape(raw)
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


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
            info.slide_pdf = info.pdf
            info.slide_images = _render_pdf_pages(info.pdf, url)
    elif _is_slideshare(host):
        # ライブ取得はbot対策でほぼ常にブロックされる(実測確認済み)ため、まず試したうえで
        # 取れなければクリップ済み本文(取得元ブラウザが保存した画像URL)から拾う。
        page_html = _fetch_text(url, "SlideShareページ")
        image_urls = _find_slideshare_image_urls(page_html)
        if not image_urls:
            image_urls = _find_slideshare_image_urls(info.note_body)
        info.slide_images = _download_slide_images(image_urls, SLIDE_MAX_PAGES)
        if not info.slide_images:
            _add_tag(info, "needs-review")
    else:  # docswell.com
        page_html = _fetch_text(url, "Docswellページ")
        download_url = _find_docswell_download_url(page_html) if page_html else None
        if download_url:
            info.slide_pdf = _download_pdf(download_url, method="POST", post_data=b"_token=")
        if info.slide_pdf:
            info.slide_images = _render_pdf_pages(info.slide_pdf, url)
        elif page_html:
            # PDFダウンロードに失敗した場合のフォールバック(プレビュー画像のみ、部分的)
            image_urls = _find_docswell_page_image_urls(page_html)
            info.slide_images = _download_slide_images(image_urls, SLIDE_MAX_PAGES)
        if not info.slide_images:
            _add_tag(info, "needs-review")


def fetch_slide_assets(url: str, note_body: str) -> MediaInfo:
    """type: slidesノート1件分のスライド実体(PDF・ページ画像)を取得する公開エントリポイント。

    organize.py の enrich() 経由(新規クリップ処理時)とは別に、fetch_slides.py
    (バックフィル・取得失敗リカバリ)がlibrary/の既存ノートに対して直接呼ぶために用意する。
    enrich()の例外処理と同じ方針(想定外エラーでも needs-review を付けて続行)を踏襲する。
    """
    info = MediaInfo(type="slides", note_body=note_body, llm_body=note_body)
    try:
        _enrich_slides(url, info)
    except Exception as e:
        print(f"    [media] スライド取得でエラー(needs-reviewで続行): {e}", file=sys.stderr)
        info.slide_pdf = None
        info.slide_images = []
        _add_tag(info, "needs-review")
    return info


# ---------------------------------------------------------------- X(Twitter)

def extract_tweet_id(url: str) -> str | None:
    m = re.search(r"/status/(\d+)", urllib.parse.urlsplit(url).path)
    return m.group(1) if m else None


def _scan_pbs_urls(body: str) -> list[str]:
    """本文中の pbs.twimg.com 画像URLを原寸(?name=orig)形式に正規化して列挙する。"""
    urls: list[str] = []
    seen: set[str] = set()
    for raw in PBS_MEDIA_RE.findall(body):
        p = urllib.parse.urlsplit(raw)
        if p.path in seen:
            continue
        seen.add(p.path)
        query = dict(urllib.parse.parse_qsl(p.query))
        if re.search(r"\.(jpg|jpeg|png|gif|webp)$", p.path, re.IGNORECASE):
            urls.append(f"https://{p.netloc}{p.path}?name=orig")
        else:
            fmt = query.get("format", "jpg")
            urls.append(f"https://{p.netloc}{p.path}?format={fmt}&name=orig")
    return urls


def _js_to_string_36(value: float) -> str:
    """JSの Number.prototype.toString(36) と同一の文字列を返す。

    V8のDoubleToRadixCString相当: 小数部は値の半ULPをdeltaとして持ち回り、
    誤差の範囲に入ったら停止・丸め(繰り上がり伝播)する。
    """
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    integer = math.floor(value)
    fraction = value - integer
    delta = max(0.5 * math.ulp(value), 5e-324)

    frac_digits: list[int] = []
    if fraction >= delta:
        while True:
            fraction *= 36
            delta *= 36
            digit = int(fraction)
            frac_digits.append(digit)
            fraction -= digit
            if fraction > 0.5 or (fraction == 0.5 and digit % 2 == 1):
                if fraction + delta > 1:
                    # 繰り上げ(35=最大桁が続く間は桁を落として伝播)
                    while frac_digits and frac_digits[-1] == 35:
                        frac_digits.pop()
                    if frac_digits:
                        frac_digits[-1] += 1
                    else:
                        integer += 1
                    break
            if fraction < delta:
                break

    int_str = ""
    n = int(integer)
    while n:
        int_str = digits[n % 36] + int_str
        n //= 36
    int_str = int_str or "0"
    if frac_digits:
        return int_str + "." + "".join(digits[d] for d in frac_digits)
    return int_str


def _syndication_token(tweet_id: str) -> str:
    """公式埋め込みウィジェットと同じ計算でsyndication API用トークンを生成する。

    JS実装: ((id / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')
    """
    x = (int(tweet_id) / 1e15) * math.pi
    return re.sub(r"(0+|\.)", "", _js_to_string_36(x))


def _fetch_syndication_media(tweet_id: str) -> list[str]:
    """無認証のsyndication API(公式埋め込みが使用)で投稿の画像URLを列挙する。"""
    api = "https://cdn.syndication.twimg.com/tweet-result?" + urllib.parse.urlencode(
        {"id": tweet_id, "token": _syndication_token(tweet_id), "lang": "ja"}
    )
    data = _fetch_json(api, "x syndication")
    if not data:
        return []
    urls = []
    for m in data.get("mediaDetails") or []:
        if isinstance(m, dict) and m.get("type") == "photo" and m.get("media_url_https"):
            urls.append(str(m["media_url_https"]) + "?name=orig")
    return urls


def _gather_post_images(url: str, info: MediaInfo) -> None:
    """本文のpbsリンク → (無ければ)syndication API の順で添付画像を取得する。"""
    urls = _scan_pbs_urls(info.note_body)
    if not urls:
        # 本文に痕跡が無くても画像付きの可能性はあるため、常にsyndicationで確認する
        tweet_id = extract_tweet_id(url)
        if tweet_id:
            urls = _fetch_syndication_media(tweet_id)
    for image_url in urls:
        if len(info.images) >= MAX_IMAGES_PER_NOTE:
            break
        asset = _download_image(image_url)
        if asset:
            info.images.append(asset)
    if info.images:
        # pic.twitter.com表記が無くても実体が取れたらメディア付き扱いにする
        _add_tag(info, "has-media")


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
    if not info.note_body:
        oe = fetch_x_oembed(url)
        raw = (oe or {}).get("html", "")
        if "pic.twitter.com" in raw:
            _add_tag(info, "has-media")
        text = x_text_from_html(raw) if raw else ""
        info.note_body = text
        info.llm_body = text
        if not text:
            _add_tag(info, "needs-review")
    _gather_post_images(url, info)


# ---------------------------------------------------------------- エントリポイント

def enrich(url: str, body: str, dry_run: bool = False) -> MediaInfo:
    """URL種別を判定し、種別に応じたコンテンツ取得を行う唯一のエントリポイント。

    dry_run時は種別判定のみ行い、ネットワークアクセスは一切しない。
    想定外の例外が出ても needs-review を付けて続行し、呼び出し側を落とさない。
    """
    info = MediaInfo(type=detect_media_type(url), note_body=body, llm_body=body)
    if info.type == "image":
        # LLM向け本文は空(URLからの推測)。実体は取得してassets保存用に載せる。
        # needs-review は画像説明の成功時に organize.py 側で外す
        info.llm_body = ""
        info.extra_tags = ["has-media", "needs-review"]
        if not dry_run:
            asset = _download_image(url)
            if asset:
                info.images = [asset]
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
        info.images = []
        info.slide_pdf = None
        info.slide_images = []
        _add_tag(info, "needs-review")
    return info
