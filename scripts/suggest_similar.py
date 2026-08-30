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
5. 返却候補(最大 llm_client.MAX_SUGGEST_CANDIDATES 件)を全件、1回のGETで
   「実在確認 + リダイレクト解決 + 発行日抽出」し、解決後の最終URLを normalize_url() で
   正規化して除外集合と突合、発行日の新しい順(不明は末尾)にクラスタあたり最大5件採用
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
import sys
from datetime import datetime, timezone
from pathlib import Path

import llm_client
import organize
import page_meta

MAX_ITEMS_PER_CLUSTER = 5
MAX_HISTORY_ENTRIES = 500
DEFAULT_MAX_CLUSTERS = 8

# 発行日抽出(HTMLパース・GET・採用metaキー)は page_meta.py に共用化した。
# suggest用途は従来どおり modified_time も最後の手がかりに使う(ADVISORY、既定値)。


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


def heal_preserved_items(
    suggestions_by_cluster: dict[str, dict], history_urls: dict[str, dict], now: str
) -> int:
    """前回以前に採用された、URL未解決 or 発行日未取得のアイテムをHTTPだけで補修する。

    groundingが失敗(HTTP 429等)したクラスタは「前回分を維持」して温存されるが、その温存分は
    どのループにも入らないため放置すると永久に古い形式(リダイレクトURL・発行日なし)のまま
    残ってしまう。補修にLLMは不要なので、調査の成否と無関係にこのパスで直す。
    """
    healed = 0
    for entry in suggestions_by_cluster.values():
        for item in entry.get("items", []):
            url = item.get("url", "")
            if not url:
                continue
            # 既に解決済みかつ発行日取得済みなら触らない(publishedAtが空文字なのは
            # 「発行日を持たないページ」として確定済みなので再取得しない)
            if "publishedAt" in item and "/grounding-api-redirect/" not in url:
                continue

            reachable, final_url, published_at = page_meta.fetch_url_meta(url)
            if not reachable:
                # 到達できないだけなら消さない(一時的な障害の可能性)。次回また試す。
                print(f"  -> 補修できず(到達不能): {url}", file=sys.stderr)
                continue

            old_norm = item.get("normalizedUrl", "")
            norm = organize.normalize_url(final_url)
            item["url"] = final_url
            item["normalizedUrl"] = norm
            item["id"] = suggestion_id(norm)
            item["publishedAt"] = published_at
            if item.get("title", "") == url:
                item["title"] = final_url

            # 解決後のURLもhistoryに載せて再提案を防ぐ。初回提案時刻は引き継ぐ。
            first = history_urls.get(old_norm, {}).get("firstSuggestedAt", now)
            history_urls[norm] = {"firstSuggestedAt": first, "clusterId": entry.get("clusterId", "")}
            healed += 1
            print(f"  -> 補修: {final_url}" + (f" (発行日 {published_at})" if published_at else ""))
    return healed


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

        # フェーズ1: 候補全件をGET(実在確認+リダイレクト解決+発行日抽出)。採用枠より多い
        # 候補プールを先に全件実測してから発行日で選ぶため、従来の「先着で枠まで」と違い
        # GETは候補全件(最大 MAX_SUGGEST_CANDIDATES 件/クラスタ)に走る。
        candidates = []
        for item in raw_items:
            # 生URLの時点で既知なら通信せずに弾く(groundingリダイレクトURLでは通常ヒットしない
            # ので本命は解決後の再突合。ここは無駄なGETを減らすための安価な前段)。
            if organize.normalize_url(item["url"]) in excluded:
                continue

            if args.no_fetch_check:
                final_url, published_at = item["url"], ""
            else:
                reachable, final_url, published_at = page_meta.fetch_url_meta(item["url"])
                if not reachable:
                    print(f"  -> 除外(到達不能): {item['url']}", file=sys.stderr)
                    continue
            candidates.append((item, final_url, published_at))

        # フェーズ2: 発行日の新しい順へ。"YYYY-MM-DD" は辞書順=時系列順で、降順ソートにより
        # 空文字(発行日不明)は自然に末尾。安定ソートなので同日・不明同士はLLM返却順を保つ。
        candidates.sort(key=lambda c: c[2], reverse=True)

        # フェーズ3: 解決後URLで本命の重複突合をしつつ、新しい順に採用枠まで採用。
        # excluded への追加は採用確定時のみ: 枠あふれの不採用候補は history にも載らないため
        # 次回の調査で再び候補になりうる(今回は枠が埋まっただけなので、意図した挙動)。
        accepted = []
        for item, final_url, published_at in candidates:
            if len(accepted) >= MAX_ITEMS_PER_CLUSTER:
                break
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

    # 温存分の補修(LLM不要。groundingが全滅した回でもここは効く)
    if not args.no_fetch_check:
        healed = heal_preserved_items(suggestions_by_cluster, history_urls, now)
        if healed:
            print(f"温存されていた提案{healed}件のURL・発行日を補修しました")

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
