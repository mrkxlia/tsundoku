"""Webページ・PDFメタデータからの発行日抽出ユーティリティ(標準ライブラリのみ)。

もともと suggest_similar.py 内にあった発行日抽出(JSON-LD > metaタグ > <time datetime> の
優先順)を、organize/backfill の取り込み経路(frontmatter `published_at` の耐久書き込み)と
共用するために切り出したモジュール。organize / media_types / llm_client には依存しない
(suggest_similar → organize → media_types → page_meta の一方向依存を保つ)。

採用キー一覧は2系統ある:
- ADVISORY(従来のsuggest用): article:modified_time を「最後の手がかり」として含む。
  提案画面の参考表示なので多少の誤差(更新日を発行日扱い)を許容する。
- STRICT(耐久書き込み用): modified_time を含まない。frontmatterに書いた発行日は
  期間フィルタ・ソートの入力になるため、「更新日で新しく見える」汚染を避ける。

耐久書き込み前には sanitize_published() で範囲チェックを通すこと
(発行日は収集日より未来にならない、等)。
"""

from __future__ import annotations

import datetime
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

# 発行日メタデータは<head>付近にあるため全文は要らない。巨大ページで詰まらないよう上限を設ける
MAX_HTML_BYTES = 400_000
# 本文取得を伴うGETのタイムアウト(HEADのみだった頃の5秒より余裕を持たせる)
FETCH_CHECK_TIMEOUT = 10

# 発行日を持つmetaタグ名(優先順)。property/name/itemprop のいずれかで一致を見る。
# modified_timeは「発行日」ではないが、suggest(参考表示)では最後の手がかりとして使う。
PUBLISHED_META_KEYS_ADVISORY = (
    "article:published_time",
    "og:published_time",
    "datepublished",
    "pubdate",
    "citation_publication_date",
    "date",
    "article:modified_time",
)
# frontmatter耐久書き込み用: modified_time を採用しない(更新日を発行日として焼き付けない)
PUBLISHED_META_KEYS_STRICT = PUBLISHED_META_KEYS_ADVISORY[:-1]
# 後方互換の別名(suggest_similar.py 由来の従来挙動 = ADVISORY)
PUBLISHED_META_KEYS = PUBLISHED_META_KEYS_ADVISORY

DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# sanitize_published のガード値。1995年以前のWebページ発行日はほぼ抽出ミス
# (テンプレートの創立年・コピーライト等)とみなす。
MIN_PUBLISHED_DATE = "1995-01-01"
# 発行日は収集日より未来にならないはずだが、タイムゾーン差・予約公開の揺れを許容する
FUTURE_TOLERANCE_DAYS = 2

_PDF_DATE_RE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")

# to_ascii_url() で path/query に残す文字: RFC 3986 の pchar/sub-delims と既存の %XX エスケープ
# ('%' を safe に含めることで、既に percent-encode 済みの部分を二重エンコードしない)。
_PATH_SAFE = "/%:@!$&'()*+,;=~"
_QUERY_SAFE = _PATH_SAFE + "?"


class _MetaDateParser(HTMLParser):
    """<meta>/<time>/JSON-LD から発行日候補を集めるだけのパーサ。

    HTMLParserは属性名を小文字化して渡すため、ZennのようにReact SSR由来で
    `dateTime` とキャメルケースで出力されるサイトもそのまま `datetime` で拾える。
    収集は上位集合(ADVISORY)で行い、どのキーを採用するかは extract_published_date() の
    keys 引数が決める。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.times: list[str] = []
        self.ld_blocks: list[str] = []
        self._in_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key in PUBLISHED_META_KEYS_ADVISORY and a.get("content"):
                self.meta.setdefault(key, a["content"])
        elif tag == "time":
            if a.get("datetime"):
                self.times.append(a["datetime"])
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_ld = False

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self.ld_blocks.append(data)


def _ld_published_date(blocks: list[str]) -> str | None:
    """JSON-LDブロック群から最初に見つかった datePublished を返す(入れ子・配列も探索)。"""
    for block in blocks:
        try:
            obj = json.loads(block, strict=False)
        except (json.JSONDecodeError, ValueError):
            continue
        stack = [obj]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                value = node.get("datePublished")
                if isinstance(value, str) and value.strip():
                    return value
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return None


def extract_published_date(html: str, keys: tuple[str, ...] = PUBLISHED_META_KEYS_ADVISORY) -> str:
    """HTMLから発行日を "YYYY-MM-DD" で返す。判定できなければ空文字。

    JSON-LDのdatePublished > 発行日系metaタグ(keys順) > 最初の<time datetime> の順に採用する
    (構造化データを最優先し、曖昧な<time>は最後の手段にする)。
    """
    parser = _MetaDateParser()
    try:
        parser.feed(html)
    except Exception:  # 壊れたHTMLでもそこまでに拾えた分で判定する
        pass

    candidate = (
        _ld_published_date(parser.ld_blocks)
        or next((parser.meta[k] for k in keys if k in parser.meta), None)
        or (parser.times[0] if parser.times else None)
    )
    match = DATE_RE.search(candidate or "")
    return match.group(0) if match else ""


def to_ascii_url(url: str) -> str:
    """非ASCII文字を含むURL(IRI)を、urllib が送信できるASCIIのURLへ変換する。

    ホストは IDNA(punycode)、path/query/fragment は UTF-8 で percent-encode する。既に %XX で
    エスケープされた部分は二重エンコードしない。ASCIIのみのURLは文字列として不変
    (既存の挙動を変えない)。urlsplit/IDNA が受け付けないURLは ValueError を投げる
    (fetch_url_meta 側で到達不能として扱う)。

    背景: urllib.request は URL をエンコードせずそのまま http.client へ渡すため、非ASCIIの
    ホストは Host ヘッダの latin-1 化で、非ASCIIの path は request line の ascii 化で
    UnicodeEncodeError になる(2026-08-31・09-01 の suggest 日次実行がこれで落ちた)。
    """
    if url.isascii():
        return url
    p = urllib.parse.urlsplit(url)
    host = p.hostname or ""
    if not host.isascii():
        host = host.encode("idna").decode("ascii")
    if ":" in host:  # IPv6 リテラルは hostname プロパティで [] が外れるので戻す
        host = f"[{host}]"
    netloc = host if p.port is None else f"{host}:{p.port}"
    if p.username is not None:
        userinfo = urllib.parse.quote(p.username, safe="")
        if p.password is not None:
            userinfo += ":" + urllib.parse.quote(p.password, safe="")
        netloc = f"{userinfo}@{netloc}"
    return urllib.parse.urlunsplit(
        (
            p.scheme,
            netloc,
            urllib.parse.quote(p.path, safe=_PATH_SAFE),
            urllib.parse.quote(p.query, safe=_QUERY_SAFE),
            urllib.parse.quote(p.fragment, safe=_QUERY_SAFE),
        )
    )


def fetch_url_meta(
    url: str,
    user_agent: str = "tsundoku-suggest/1.0",
    keys: tuple[str, ...] = PUBLISHED_META_KEYS_ADVISORY,
) -> tuple[bool, str, str]:
    """1回のGETで (到達可能か, リダイレクト解決後の最終URL, 発行日) を返す。

    groundingが返すリダイレクトURLを実URLへ解決するのが主目的。urlopenは既定で
    リダイレクトを追うため geturl() が最終URLになる。HTML以外(PDF等)は到達確認だけ行う。
    例外を外へ投げない(到達不能は (False, url, "") で表現する)。呼び出し元(suggest_similar /
    media_types.enrich の article 経路 / backfill_published)はこの契約に依存しており、
    ここで例外が漏れると1URLでジョブ全体が落ちる。

    非ASCIIのURLは to_ascii_url() で変換して送信し、リダイレクトが無ければ呼び出し元の
    表記(変換前のURL)をそのまま最終URLとして返す(history/除外集合のキーは
    organize.normalize_url(URL文字列) なので、表記を勝手に変えると既知URLと突合できなくなる)。
    """
    try:
        # Request() 自体も scheme 無し等で ValueError を投げるので try の内側で組み立てる
        req = urllib.request.Request(to_ascii_url(url), headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=FETCH_CHECK_TIMEOUT) as resp:
            if resp.status >= 400:
                return False, url, ""
            final_url = resp.geturl() or url
            if final_url == req.full_url:
                final_url = url  # リダイレクト無し: 変換前の表記を返す
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if "html" not in content_type:
                return True, final_url, ""
            raw = resp.read(MAX_HTML_BYTES)
    except urllib.error.HTTPError as e:
        # 4xx/5xx でも「ページは存在するがHEAD/GETを拒否」等がありうるため従来同様 <400 のみ到達扱い
        return e.code < 400, url, ""
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        # ValueError: 不正なURL(scheme無し・IPv6括弧不整合・非数値ポート=http.client.InvalidURL)、
        # IDNA変換不能(UnicodeError)、ヘッダ/リクエスト行のエンコード失敗(UnicodeEncodeError)。
        # いずれも「このURLは取得できない」であり、ジョブを落とす理由にはならない。
        return False, url, ""

    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")
    return True, final_url, extract_published_date(html, keys=keys)


def sanitize_published(value: str, created: str) -> str:
    """frontmatterへの耐久書き込み前のサニティガード。

    抽出した発行日が「収集日+許容日数より未来」「1995年より前」「日付として不正」の
    いずれかなら ''(到達したが発行日なし=確定不明)へ落とす。発行日は収集日より
    未来にならないはずで、これが更新日(modified_time)や無関係な<time>の混入を弾く
    最後の防波堤になる。空文字はそのまま通す(確定不明の意味を保つ)。
    """
    if not value:
        return ""
    m = DATE_RE.search(value)
    if not m:
        return ""
    date = m.group(0)
    try:
        parsed = datetime.date.fromisoformat(date)
    except ValueError:  # "2026-13-99" 等、正規表現は通るが日付でない
        return ""
    if date < MIN_PUBLISHED_DATE:
        return ""
    created_match = DATE_RE.search(created or "")
    if created_match:
        try:
            limit = datetime.date.fromisoformat(created_match.group(0)) + datetime.timedelta(
                days=FUTURE_TOLERANCE_DAYS
            )
            if parsed > limit:
                return ""
        except ValueError:
            pass  # createdが壊れている場合は未来チェックだけ諦める
    return date


def parse_pdf_date(raw: str) -> str:
    """PDFメタデータの日付("D:YYYYMMDDHHmmSS+09'00'" 形式)を "YYYY-MM-DD" へ。

    DATE_RE はハイフン区切り前提でPDF形式には絶対にマッチしないため専用にパースする。
    解釈できなければ空文字。
    """
    m = _PDF_DATE_RE.search(raw or "")
    if not m:
        return ""
    y, mo, d = (int(g) for g in m.groups())
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return ""
