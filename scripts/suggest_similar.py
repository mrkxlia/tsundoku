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
5. 返却候補を normalize_url() で正規化して除外集合と突合し、http(s)チェック
   (--no-fetch-check指定時を除きHEAD/GETで実在確認)、クラスタあたり最大5件採用
6. suggestions.json(調査したクラスタのみ更新。grounding失敗クラスタは前回分を温存)と
   history.json を --data-dir へ書き出す(Vaultへは一切書き込まない)

環境変数:
    DRY_RUN : "1" で外部APIを呼ばずMockClientで動作確認する
    (Gemini関連の環境変数は llm_client.py を参照)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import llm_client
import organize

MAX_ITEMS_PER_CLUSTER = 5
MAX_HISTORY_ENTRIES = 500
FETCH_CHECK_TIMEOUT = 5
DEFAULT_MAX_CLUSTERS = 8


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


def _url_reachable_once(url: str, method: str) -> bool:
    req = urllib.request.Request(url, method=method, headers={"User-Agent": "tsundoku-suggest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_CHECK_TIMEOUT) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as e:
        return e.code < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def url_is_reachable(url: str) -> bool:
    """HEADで確認し、405(HEAD非対応サイト)の場合のみGETで再確認する。"""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "tsundoku-suggest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_CHECK_TIMEOUT) as resp:
            return resp.status < 400
    except urllib.error.HTTPError as e:
        if e.code == 405:
            return _url_reachable_once(url, "GET")
        return False
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


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
            norm = organize.normalize_url(item["url"])
            if norm in excluded:
                continue
            if not args.no_fetch_check and not url_is_reachable(item["url"]):
                print(f"  -> 除外(到達不能): {item['url']}", file=sys.stderr)
                continue
            excluded.add(norm)  # 同一クラスタ内・後続クラスタでの重複提案も防ぐ
            accepted.append(
                {
                    "id": suggestion_id(norm),
                    "url": item["url"],
                    "normalizedUrl": norm,
                    "title": item.get("title") or item["url"],
                    "reason": item.get("reason", ""),
                    "sources": item.get("sources", []),
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
