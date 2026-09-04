"""興味ありトピック(tsundoku-site の data/suggest/clusters.json + interests.json)について、
類似サイトをGoogle Search groundingで調査し、data/suggest/suggestions.json / history.json
を更新するスクリプト。

処理内容:
1. --data-dir から clusters.json / interests.json / feedback.json / history.json を読む
   (このスクリプトはtsundoku-siteリポジトリのsparse-checkout先を指す想定)
2. 除外集合を構築: library全ノートのurl+sources(正規化済み) ∪ Inbox未処理クリップのURL ∪
   feedbackに記録済みのURL(却下取り消し unrejected を除く) ∪ historyに記録済みのURL。
   ただし「unrejected かつ 取り消し後まだ再提案していない(historyのfirstSuggestedAtが
   取り消しtsより古い)」URLはhistory除外をワンショットでバイパスし、再提案可能に戻す
3. 興味ありクラスタを、historyの最終調査時刻が古い順(未調査を最優先)に --max-clusters 件選ぶ
4. 各クラスタについて、代表ノートのタイトルを種に llm_client.suggest_similar_sites() を1回呼ぶ。
   却下済み(rejected)titleを負例としてプロンプトに注入し、似た傾向の候補の優先度を下げる
   (完全排除はしない。対象クラスタの却下を優先し、不足分は他クラスタの直近却下で補充)
5. 返却候補(最大 llm_client.MAX_SUGGEST_CANDIDATES 件)を全件、1回のGETで
   「実在確認 + リダイレクト解決 + 発行日抽出」し、解決後の最終URLを normalize_url() で
   正規化して除外集合と突合、発行日の新しい順(不明は末尾)にクラスタあたり最大5件採用
   (--no-fetch-check指定時はGETを行わず候補URLをそのまま使う)。却下が多いドメイン
   (却下数>=DOMAIN_PENALTY_THRESHOLD かつ 却下数>採用数)の候補は採用順を後ろへ回し、
   クラスタあたり最大 PENALIZED_ADOPT_MAX 件だけ採用する(探索の幅を保つ「突然変異」枠)
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
from urllib.parse import urlsplit

import llm_client
import organize
import page_meta

MAX_ITEMS_PER_CLUSTER = 5
# 日次実行では最大 DEFAULT_MAX_CLUSTERS×MAX_ITEMS_PER_CLUSTER=15件/日のペースでhistoryが
# 増えるため、500のままだとLRUが1〜2ヶ月で一巡し同じURLが再提案されやすくなる。
# 2000なら最速ペースでも4ヶ月超は保持できる
MAX_HISTORY_ENTRIES = 2000
# 週次(8クラスタ/週)から日次(3クラスタ/日)へ変更。1日の新提案を最大15件に抑えつつ
# 興味ありトピック全体を数日で一巡する。suggest.yml の max_clusters 既定値と揃えること
DEFAULT_MAX_CLUSTERS = 3
# ドメイン減点: 同一ホストの却下(rejected)がこの回数以上、かつ却下数>採用数のホストは
# 候補の採用順を非減点候補の後ろへ回す(完全排除はしない)。「却下数>採用数」条件は、
# よく読む媒体(zenn等)を数回の却下で恒久減点しないための保険。値を大きくすれば実質無効化
# できる(切り戻しレバー)。負例注入側のレバーは llm_client.NEGATIVE_EXAMPLES_MAX。
DOMAIN_PENALTY_THRESHOLD = 2
# 減点ドメイン候補のクラスタあたり採用上限(探索の幅を保つための「突然変異」枠)
PENALIZED_ADOPT_MAX = 1

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


def normalize_or_none(url) -> str | None:
    """organize.normalize_url の「落ちない」版。feedback.json のキー(サイト側JSの normalizeUrl)や
    LLM が返した生URLを Python 側の正規化へ寄せる。両者は www./x.com/トラッキング除去は同規則だが、
    YouTube の watch 統一は Python 側にしか無く、youtu.be / shorts / m.youtube.com が別キーになる。
    history.json のキーと候補側のホスト判定は Python 正規化なので、突合前に必ずこれを通す。
    URLとして解釈できない値(手編集で壊れたキー、LLM出力の '[' 混入など)は None(呼び出し側で除外)。
    日次の無人実行なので、1件の不正値で run 全体を落とさないことを優先する。"""
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        return organize.normalize_url(url)
    except ValueError:  # urlsplit の "Invalid IPv6 URL" 等
        return None


def normalized_host(url) -> str | None:
    """正規化後URLのホスト名(判定・ログ用)。解釈不能なら None。"""
    key = normalize_or_none(url)
    return urlsplit(key).hostname if key else None


def parse_ts(value) -> datetime | None:
    """history(isoformatの+00:00形式)とfeedback(JS toISOString()の.sssZ形式)のISO時刻を
    比較可能な形でパースする。両者は文字列比較では順序が壊れる('+' < '.')ため必須。
    naive(tz情報なし)はaware値との比較がTypeErrorになるためNone扱い(=安全側)。
    末尾 'Z' の解釈は Python 3.11+ が必要(suggest.yml は 3.12 固定)。"""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def sanitize_negative_title(title) -> str:
    """負例titleをプロンプトへ入れる前のサニタイズ。titleはsite側でsuggestions.json照合済み
    だが元はWebページ由来の文字列なので、制御文字(改行含む)除去+長さ上限で注入面を絞る。"""
    if not isinstance(title, str):
        return ""
    cleaned = "".join(ch if ch.isprintable() else " " for ch in title)
    return " ".join(cleaned.split())[: llm_client.NEGATIVE_TITLE_MAX_CHARS].strip()


# 対象クラスタ外の却下を負例へ補充するときの接頭辞(ログの内訳集計にも使う)
GLOBAL_NEGATIVE_MARKER = "[別トピックでの却下] "


def collect_negative_titles(feedback_items: dict, cluster_id: str) -> list[str]:
    """却下済み(action=="rejected")のtitleを負例として最大 NEGATIVE_EXAMPLES_MAX 件集める。

    対象クラスタの却下を新しい順に優先し、不足分は他クラスタの直近却下で補充する
    (マーカー付き)。補充するのは、類似コンテンツがクラスタを跨いで現れることと、
    re-clusterでclusterIdが変わると旧却下のクラスタ紐付けが外れて負例が消えてしまうため。"""
    if llm_client.NEGATIVE_EXAMPLES_MAX <= 0:
        return []
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    rejected: list[tuple[datetime, str, str]] = []
    for v in feedback_items.values():
        if v.get("action") != "rejected":
            continue
        title = sanitize_negative_title(v.get("title"))
        if not title:
            continue
        rejected.append((parse_ts(v.get("ts")) or epoch, v.get("clusterId") or "", title))
    rejected.sort(key=lambda r: r[0], reverse=True)
    picked = [t for _, cid, t in rejected if cid == cluster_id][: llm_client.NEGATIVE_EXAMPLES_MAX]
    for _, cid, title in rejected:
        if len(picked) >= llm_client.NEGATIVE_EXAMPLES_MAX:
            break
        if cid != cluster_id:
            picked.append(f"{GLOBAL_NEGATIVE_MARKER}{title}")
    return picked


def penalized_hosts(feedback_items: dict) -> tuple[set[str], dict[str, tuple[int, int]]]:
    """ホスト別の却下/採用件数を集計し、(減点対象ホスト集合, 対象ホストの(却下,採用)件数)を返す。

    判定式は「rejected >= DOMAIN_PENALTY_THRESHOLD かつ rejected > adopted」。キーは正規化URL
    なので同一URLの重複カウントは起きない(閾値2=同一ドメインの別URL2件の却下)。
    unrejected(却下取り消し)はどちら側にも数えない。件数はログ出力(減点の可視化)用。
    ホストは normalized_host()(Python 正規化)で取る: feedback のキーはサイト側正規化で
    youtu.be 等が残りうるが、候補側の判定(partition_candidates)と同じ youtube.com に寄せる。"""
    counts: dict[str, list[int]] = {}
    for url, v in feedback_items.items():
        action = v.get("action")
        if action not in ("rejected", "adopted"):
            continue
        host = normalized_host(url)
        if not host:
            continue
        pair = counts.setdefault(host, [0, 0])
        pair[0 if action == "rejected" else 1] += 1
    penalized = {
        host
        for host, (rej, ado) in counts.items()
        if rej >= DOMAIN_PENALTY_THRESHOLD and rej > ado
    }
    return penalized, {h: (r, a) for h, (r, a) in counts.items() if h in penalized}


def partition_candidates(candidates: list[tuple], penalized: set[str]) -> list[tuple[tuple, bool]]:
    """発行日降順ソート済みの候補を「非減点→減点」の2区画に並べ替える。

    各区画内は元の順序(発行日降順、PR #24の鮮度優先)を維持する。区画間では鮮度が反転する
    (減点ドメインの新記事より非減点の旧記事が先)が、これは意図したトレードオフ。
    減点判定は解決後URLの正規化ホスト名(penalized_hosts 側も同じ Python 正規化に寄せてある)。
    解釈不能なURLは減点なし扱い(後段の重複突合で除外される)。"""

    def is_penalized(cand: tuple) -> bool:
        host = normalized_host(cand[1])
        return host is not None and host in penalized

    flagged = [(c, is_penalized(c)) for c in candidates]
    return [(c, p) for c, p in flagged if not p] + [(c, p) for c, p in flagged if p]


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


def revivable_history_keys(feedback_items: dict, history_urls: dict[str, dict]) -> set[str]:
    """却下取り消し(unrejected)のうち、まだ再提案していないURLの history キー集合を返す。

    条件は history.firstSuggestedAt < 取り消しts(再提案されると採用時の history 上書きで
    偽になり、次回から通常の除外へ自動復帰する)。feedback のキーはサイト側(JS)正規化、
    history のキーは Python 正規化なので normalize_or_none で history 側へ寄せて突合し、
    返すのも history キー(呼び出し側が history 除外から差し引く単位)。履歴に無いURL
    (LRU で失効済み等)・ts比較不能(形式不正・naive)は安全側=復活させない。前者はログに残す。"""
    revivable: set[str] = set()
    for u, v in feedback_items.items():
        if v.get("action") != "unrejected":
            continue
        key = normalize_or_none(u)
        hist = history_urls.get(key) if key else None
        if not isinstance(hist, dict):
            print(f"却下取り消しURLが調査履歴に無いため復活対象外: {u}", file=sys.stderr)
            continue
        h_ts, f_ts = parse_ts(hist.get("firstSuggestedAt")), parse_ts(v.get("ts"))
        if h_ts and f_ts and h_ts < f_ts:
            revivable.add(key)
    return revivable


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
    feedback_items = {
        u: v for u, v in feedback_data.get("items", {}).items() if isinstance(v, dict)
    }
    excluded |= {u for u, v in feedback_items.items() if v.get("action") != "unrejected"}
    # 却下取り消し(unrejected)後、まだ再提案していないURLだけhistory除外をワンショットで
    # バイパスして再提案可能に戻す。再提案されると採用時のhistory上書き(firstSuggestedAt=now)
    # でこの条件が偽になり、次回から通常の除外へ自動復帰する(取り消したURLが毎回再提案されて
    # 枠を占有し続けるループを防ぐ)。ts比較不能(形式不正・naive)は安全側=除外維持。
    revivable = revivable_history_keys(feedback_items, history_urls)
    excluded |= set(history_urls) - revivable
    if revivable:
        print(f"却下取り消しにより再提案可能に戻したURL: {len(revivable)}件", file=sys.stderr)

    # 減点ドメインとre-cluster宙吊り却下の可視化(どのドメインがなぜ減点中かをActionsログに残す。
    # UI・台帳のどこにも出ない「静かな恒久ペナルティ」にしないため)
    penalized, penalized_stats = penalized_hosts(feedback_items)
    if penalized:
        stats = ", ".join(f"{h}(却下{r}/採用{a})" for h, (r, a) in sorted(penalized_stats.items()))
        print(f"減点対象ドメイン: {stats}", file=sys.stderr)
    dangling = sum(
        1
        for v in feedback_items.values()
        if v.get("action") == "rejected"
        and v.get("clusterId")
        and v.get("clusterId") not in clusters_by_id
    )
    if dangling:
        print(
            f"現行クラスタに紐付かない却下記録: {dangling}件(負例はグローバル補充で利用)",
            file=sys.stderr,
        )

    client = llm_client.create_client()
    suggestions_by_cluster = {c["clusterId"]: c for c in suggestions_data.get("clusters", [])}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for cid in target_ids:
        cluster = clusters_by_id[cid]
        seed_notes = [{"title": r.get("title", "")} for r in cluster.get("representatives", [])[:5]]
        print(f"* {cid}: {cluster.get('label', cid)}")
        negatives = collect_negative_titles(feedback_items, cid)
        if negatives:
            filled = sum(1 for t in negatives if t.startswith(GLOBAL_NEGATIVE_MARKER))
            print(
                f"  負例{len(negatives)}件をプロンプトに注入(対象クラスタ{len(negatives) - filled}/他クラスタ補充{filled})",
                file=sys.stderr,
            )
        try:
            raw_items = client.suggest_similar_sites(
                cluster.get("label", ""),
                cluster.get("description", ""),
                cluster.get("keywords", []),
                seed_notes,
                rejected_titles=negatives,
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
            raw_norm = normalize_or_none(item["url"])
            if raw_norm is None:
                print(f"  -> 除外(URLとして解釈不能): {item['url']!r}", file=sys.stderr)
                continue
            if raw_norm in excluded:
                continue

            if args.no_fetch_check:
                final_url, published_at = item["url"], ""
            else:
                try:
                    reachable, final_url, published_at = page_meta.fetch_url_meta(item["url"])
                except Exception as e:  # 契約上は投げないが、1URLの想定外で run 全体(grounding枠・履歴)を失わない
                    print(f"  -> 除外(取得エラー): {item['url']} ({type(e).__name__}: {e})", file=sys.stderr)
                    continue
                if not reachable:
                    print(f"  -> 除外(到達不能): {item['url']}", file=sys.stderr)
                    continue
            candidates.append((item, final_url, published_at))

        # フェーズ2: 発行日の新しい順へ。"YYYY-MM-DD" は辞書順=時系列順で、降順ソートにより
        # 空文字(発行日不明)は自然に末尾。安定ソートなので同日・不明同士はLLM返却順を保つ。
        candidates.sort(key=lambda c: c[2], reverse=True)

        # フェーズ2.5: 却下多発ドメインの候補を採用順の後ろへ回す(各区画内は発行日降順を維持)。
        # 候補のホスト分布もログに残す(負例・減点が効いているかの事後検証用)。
        ordered = partition_candidates(candidates, penalized)
        if candidates:
            hosts = ", ".join(normalized_host(c[1]) or "?" for c in candidates)
            print(f"  候補{len(candidates)}件: {hosts}", file=sys.stderr)

        # フェーズ3: 解決後URLで本命の重複突合をしつつ、新しい順に採用枠まで採用。
        # excluded への追加は採用確定時のみ: 枠あふれの不採用候補は history にも載らないため
        # 次回の調査で再び候補になりうる(今回は枠が埋まっただけなので、意図した挙動)。
        # 減点ドメイン候補は非減点候補の後にのみ、最大 PENALIZED_ADOPT_MAX 件(突然変異枠)。
        # 枠の予約はしない: 非減点候補で5枠が埋まれば減点候補は採用されない。
        accepted = []
        penalized_adopted = 0
        for (item, final_url, published_at), is_penalized in ordered:
            if len(accepted) >= MAX_ITEMS_PER_CLUSTER:
                break
            # 重複判定の本命。リダイレクト解決後の実URLで初めて既存ノートと突合できる。
            norm = normalize_or_none(final_url)
            if norm is None:
                print(f"  -> 除外(解決後URLが解釈不能): {final_url!r}", file=sys.stderr)
                continue
            if norm in excluded:
                print(f"  -> 除外(解決後に既知URLと重複): {final_url}", file=sys.stderr)
                continue
            if is_penalized:
                if penalized_adopted >= PENALIZED_ADOPT_MAX:
                    print(f"  -> 見送り(却下多発ドメイン、突然変異枠超過): {final_url}", file=sys.stderr)
                    continue
                penalized_adopted += 1
                print(f"  -> 却下多発ドメインだが突然変異枠で採用: {final_url}", file=sys.stderr)

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
