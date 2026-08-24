"""興味ありトピック(tsundoku-site の data/suggest/clusters.json + interests.json)について、
類似サイトをGoogle Search groundingで調査し、data/suggest/suggestions.json / history.json
を更新するスクリプト。

処理内容:
1. --data-dir から clusters.json / interests.json / feedback.json / history.json を読む
   (このスクリプトはtsundoku-siteリポジトリのsparse-checkout先を指す想定)
2. 除外集合を構築: library全ノートのurl+sources(正規化済み) ∪ Inbox未処理クリップのURL ∪
   feedbackに記録済みの全URL(採用/却下問わず) ∪ historyに記録済みの全URL
3. 興味ありクラスタを、historyの最終調査時刻が古い順(未調査を最優先)に --max-clusters 件選ぶ
4. 各クラスタについて、代表ノートのタイトルを種に llm_client.suggest_similar_sites() を1回呼ぶ
5. 返却候補を1回のGETで「実在確認 + リダイレクト解決 + 発行日抽出」し、解決後の最終URLを
   normalize_url() で正規化して除外集合と突合、クラスタあたり最大5件採用
   (--no-fetch-check指定時はGETを行わず候補URLをそのまま使う)
6. suggestions.json(調査したクラスタのみ更新。grounding失敗クラスタは前回分を温存)と
   history.json を --data-dir へ書き出す(Vaultへは一切書き込まない)

groundingが返すURLは https://vertexaisearch.cloud.google.com/grounding-api-redirect/... という
不透明なリダイレクトURLであることが多い。これをそのまま保存すると (a) サイト側のドメイン表示が
全て vertexaisearch.cloud.google.com になり (b) 発行日が取得できず (c) 正規化URLでの重複判定が
実URLと噛み合わず機能しない。そのため5.で必ず最終URLまで解決してから採用する。

環境変数:
    DRY_RUN : "1" で外部APIを呼ばずMockClientで動作確認する
    (Gemini関連の環境変数は llm_client.py を参照)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import llm_client
import organize

MAX_ITEMS_PER_CLUSTER = 5
MAX_HISTORY_ENTRIES = 500
# 本文取得を伴うGETに変えたためHEADのみだった頃(5秒)より余裕を持たせる
FETCH_CHECK_TIMEOUT = 10
# 発行日メタデータは<head>付近にあるため全文は要らない。巨大ページで詰まらないよう上限を設ける
MAX_HTML_BYTES = 400_000
DEFAULT_MAX_CLUSTERS = 8

# 発行日を持つmetaタグ名(優先順)。property/name/itemprop のいずれかで一致を見る。
# modified_timeは「発行日」ではないが、他が無い場合の最後の手がかりとして末尾に置く。
PUBLISHED_META_KEYS = (
    "article:published_time",
    "og:published_time",
    "datepublished",
    "pubdate",
    "citation_publication_date",
    "date",
    "article:modified_time",
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data-dir", type=Path, required=True, help="clusters.json等を含む tsundoku-site の data/suggest/ パス"
    )
    p.add_argument(
        "--max-clusters",
        type=int,
        default=DEFAULT_MAX_CLUSTERS,
        help="このジョブで調査する興味ありクラスタ数の上限(超過分は次回実行へ持ち越し)",
    )
    p.add_argument(
        "--no-fetch-check",
        action="store_true",
        help="候補URLの実在チェック(HEAD/GET)を省略する(DRY_RUNでの配管確認用)",
    )
    return p.parse_args()


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"警告: {path} を解釈できません。既定値で続行します", file=sys.stderr)
        return default


def suggestion_id(normalized_url: str) -> str:
    return hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:8]


def build_excluded_urls() -> set[str]:
    """既存library・現Inbox未処理クリップの正規化済みURL集合(重複提案の一次防止線)。"""
    excluded: set[str] = set()
    for note in organize.load_library():
        excluded |= note.urls
    for path in organize.collect_candidates():
        clip = organize.parse_clip(path)
        if clip:
            excluded.add(organize.normalize_url(clip.url))
    return excluded


class _MetaDateParser(HTMLParser):
    """<meta>/<time>/JSON-LD から発行日候補を集めるだけのパーサ。

    HTMLParserは属性名を小文字化して渡すため、ZennのようにReact SSR由来で
    `dateTime` とキャメルケースで出力されるサイトもそのまま `datetime` で拾える。
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
            if key in PUBLISHED_META_KEYS and a.get("content"):
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


def extract_published_date(html: str) -> str:
    """HTMLから発行日を "YYYY-MM-DD" で返す。判定できなければ空文字。

    JSON-LDのdatePublished > 発行日系metaタグ > 最初の<time datetime> の順に採用する
    (構造化データを最優先し、曖昧な<time>は最後の手段にする)。
    """
    parser = _MetaDateParser()
    try:
        parser.feed(html)
    except Exception:  # 壊れたHTMLでもそこまでに拾えた分で判定する
        pass

    candidate = (
        _ld_published_date(parser.ld_blocks)
        or next((parser.meta[k] for k in PUBLISHED_META_KEYS if k in parser.meta), None)
        or (parser.times[0] if parser.times else None)
    )
    match = DATE_RE.search(candidate or "")
    return match.group(0) if match else ""


def fetch_url_meta(url: str) -> tuple[bool, str, str]:
    """1回のGETで (到達可能か, リダイレクト解決後の最終URL, 発行日) を返す。

    groundingが返すリダイレクトURLを実URLへ解決するのが主目的。urlopenは既定で
    リダイレクトを追うため geturl() が最終URLになる。HTML以外(PDF等)は到達確認だけ行う。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "tsundoku-suggest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_CHECK_TIMEOUT) as resp:
            if resp.status >= 400:
                return False, url, ""
            final_url = resp.geturl() or url
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if "html" not in content_type:
                return True, final_url, ""
            raw = resp.read(MAX_HTML_BYTES)
    except urllib.error.HTTPError as e:
        # 4xx/5xx でも「ページは存在するがHEAD/GETを拒否」等がありうるため従来同様 <400 のみ到達扱い
        return e.code < 400, url, ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, url, ""

    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")
    return True, final_url, extract_published_date(html)


def select_target_clusters(
    interested_ids: list[str], history_urls: dict[str, dict], max_clusters: int
) -> list[str]:
    """興味ありクラスタを、直近の調査(historyに記録された最終提案時刻)が古い順
    (未調査は最優先)に並べ、上限件数まで選ぶ。"""

    def last_investigated(cluster_id: str) -> str:
        times = [v.get("firstSuggestedAt", "") for v in history_urls.values() if v.get("clusterId") == cluster_id]
        return max(times) if times else ""

    ordered = sorted(interested_ids, key=last_investigated)
    return ordered[:max_clusters]


def main() -> int:
    args = parse_args()

    clusters_data = load_json(args.data_dir / "clusters.json", {"clusters": []})
    interests_data = load_json(args.data_dir / "interests.json", {"clusters": {}})
    feedback_data = load_json(args.data_dir / "feedback.json", {"items": {}})
    history_data = load_json(args.data_dir / "history.json", {"urls": {}})
    suggestions_path = args.data_dir / "suggestions.json"
    suggestions_data = load_json(suggestions_path, {"clusters": []})

    clusters_by_id = {c["id"]: c for c in clusters_data.get("clusters", [])}
    interested_ids = [
        cid
        for cid, v in interests_data.get("clusters", {}).items()
        if v.get("interested") is True and cid in clusters_by_id
    ]
    if not interested_ids:
        print("興味ありトピックがありません(スキップ)")
        return 0

    history_urls: dict[str, dict] = history_data.get("urls", {})
    target_ids = select_target_clusters(interested_ids, history_urls, args.max_clusters)
    skipped = len(interested_ids) - len(target_ids)
    print(
        f"興味ありトピック{len(interested_ids)}件中{len(target_ids)}件を調査します"
        + (f"(残り{skipped}件は次回へ)" if skipped else "")
    )

    excluded = build_excluded_urls()
    excluded |= set(feedback_data.get("items", {}))
    excluded |= set(history_urls)

    client = llm_client.create_client()
    suggestions_by_cluster = {c["clusterId"]: c for c in suggestions_data.get("clusters", [])}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for cid in target_ids:
        cluster = clusters_by_id[cid]
        seed_notes = [{"title": r.get("title", "")} for r in cluster.get("representatives", [])[:5]]
        print(f"* {cid}: {cluster.get('label', cid)}")
        try:
            raw_items = client.suggest_similar_sites(
                cluster.get("label", ""), cluster.get("description", ""), cluster.get("keywords", []), seed_notes
            )
        except llm_client.LLMError as e:
            print(f"  -> 調査に失敗(前回分を維持、次回再試行): {e}", file=sys.stderr)
            continue

        accepted = []
        for item in raw_items:
            if len(accepted) >= MAX_ITEMS_PER_CLUSTER:
                break
            # 生URLの時点で既知なら通信せずに弾く(groundingリダイレクトURLでは通常ヒットしない
            # ので本命は解決後の再突合。ここは無駄なGETを減らすための安価な前段)。
            if organize.normalize_url(item["url"]) in excluded:
                continue

            if args.no_fetch_check:
                final_url, published_at = item["url"], ""
            else:
                reachable, final_url, published_at = fetch_url_meta(item["url"])
                if not reachable:
                    print(f"  -> 除外(到達不能): {item['url']}", file=sys.stderr)
                    continue

            # 重複判定の本命。リダイレクト解決後の実URLで初めて既存ノートと突合できる。
            norm = organize.normalize_url(final_url)
            if norm in excluded:
                print(f"  -> 除外(解決後に既知URLと重複): {final_url}", file=sys.stderr)
                continue

            excluded.add(norm)  # 同一クラスタ内・後続クラスタでの重複提案も防ぐ
            accepted.append(
                {
                    "id": suggestion_id(norm),
                    "url": final_url,
                    "normalizedUrl": norm,
                    "title": item.get("title") or final_url,
                    "reason": item.get("reason", ""),
                    "sources": item.get("sources", []),
                    "publishedAt": published_at,
                    "suggestedAt": now,
                }
            )
            history_urls[norm] = {"firstSuggestedAt": now, "clusterId": cid}

        if accepted:
            suggestions_by_cluster[cid] = {
                "clusterId": cid,
                "label": cluster.get("label", cid),
                "items": accepted,
            }
            print(f"  -> {len(accepted)}件を採用")
        else:
            print("  -> 採用できる候補なし(前回分を維持)")

    # history上限管理(古い順にLRU削除)
    if len(history_urls) > MAX_HISTORY_ENTRIES:
        sorted_keys = sorted(history_urls, key=lambda k: history_urls[k].get("firstSuggestedAt", ""))
        for k in sorted_keys[: len(history_urls) - MAX_HISTORY_ENTRIES]:
            del history_urls[k]

    suggestions_out = {
        "version": 1,
        "generatedAt": now,
        "clusters": list(suggestions_by_cluster.values()),
    }
    args.data_dir.mkdir(parents=True, exist_ok=True)
    suggestions_path.write_text(json.dumps(suggestions_out, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.data_dir / "history.json").write_text(
        json.dumps({"version": 1, "urls": history_urls}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"完了: {len(target_ids)}トピックを調査")
    return 0


if __name__ == "__main__":
    sys.exit(main())
