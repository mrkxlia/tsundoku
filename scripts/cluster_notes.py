"""library/ 全ノートの埋め込みベクトルをクラスタリングし、tsundoku-site の
data/suggest/clusters.json 向けにトピック(クラスタ)定義を生成するスクリプト。

処理内容:
1. index/embeddings.json (build_embeddings.py が生成) を読み、ノートごとの
   チャンクベクトルを平均→L2再正規化してノート単位ベクトルにする
   (status: superseded、chunks空のノートは対象外)
2. 球面k-means(コサイン類似度ベース)でクラスタリングする。--prev(前回の
   clusters.json)が与えられれば、前回centroidをk-meansの初期値にして
   構造を安定させる(--recluster指定時は初期値に使わずk-means++で作り直す)
3. 新旧centroidのコサイン類似度で貪欲マッチングし、クラスタIDを引き継ぐ
   (未マッチのクラスタには新規IDを採番)
4. クラスタのメンバー集合が前回と変わらない(membersHash一致)場合は
   ラベル生成をスキップし、前回のlabel/description/keywordsを引き継ぐ
5. 変化したクラスタのみ llm_client.generate_cluster_label() でラベル生成
   (代表ノートのtitle/summary/tagsは library/ の実ファイルから読む)
6. --out へ clusters.json を書き出す(このスクリプトはVaultへは一切書き込まない)

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

import numpy as np

import llm_client
import organize

ROOT = organize.ROOT

DEFAULT_MIN_K = 6
DEFAULT_MAX_K = 15
MAX_REPRESENTATIVES = 8
MATCH_THRESHOLD = 0.6  # 新旧centroidをコサイン類似度で照合する際の下限
KMEANS_MAX_ITER = 50
KMEANS_SEED = 42  # 実行のたびに結果が揺れないよう固定(--prevによる初期値が主な安定化要因)

# organize.pyが内容とは無関係に自動付与する運用系タグ。ラベル生成のkeywordsに混入させない
# (tsundoku-site側 plugins/*/src/util/fm.ts の OPERATIONAL_TAGS と同じ意図・同じ値)。
OPERATIONAL_TAGS = {"has-media", "needs-review"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--embeddings",
        type=Path,
        default=ROOT / "index" / "embeddings.json",
        help="build_embeddings.py が生成した埋め込みindexのパス",
    )
    p.add_argument(
        "--prev",
        type=Path,
        default=None,
        help="前回生成した clusters.json のパス(あればID引き継ぎ・ラベル安定化に使う)",
    )
    p.add_argument("--out", type=Path, required=True, help="clusters.json の出力先")
    p.add_argument(
        "--k",
        type=int,
        default=None,
        help="クラスタ数を固定する(既定は clamp(round(sqrt(N/2)), 6, 15))",
    )
    p.add_argument(
        "--recluster",
        action="store_true",
        help="前回centroidを初期値に使わず、k-means++で完全に作り直す(ID照合は行う)",
    )
    return p.parse_args()


# ---------------------------------------------------------------- ノートベクトルの構築


def load_note_vectors(embeddings_path: Path) -> tuple[list[str], np.ndarray, dict]:
    """(相対パス一覧, ノート単位ベクトル行列(単位ベクトル), 埋め込みindexのメタ情報)を返す。"""
    if not embeddings_path.exists():
        return [], np.zeros((0, 0)), {}
    index = json.loads(embeddings_path.read_text(encoding="utf-8"))
    notes = index.get("notes") or {}
    paths: list[str] = []
    vectors: list[list[float]] = []
    for rel_path, meta in notes.items():
        if meta.get("status") == "superseded":
            continue
        chunks = meta.get("chunks") or []
        if not chunks:
            continue
        chunk_vectors = [c["vector"] for c in chunks if c.get("vector")]
        if not chunk_vectors:
            continue
        mean = np.mean(np.array(chunk_vectors, dtype=np.float64), axis=0)
        norm = np.linalg.norm(mean)
        if norm == 0:
            continue
        paths.append(rel_path)
        vectors.append((mean / norm).tolist())
    matrix = np.array(vectors, dtype=np.float64) if vectors else np.zeros((0, 0))
    meta_out = {"model": index.get("model"), "dim": index.get("dim")}
    return paths, matrix, meta_out


# ---------------------------------------------------------------- 球面k-means


def _kmeanspp_init(vectors: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    n = vectors.shape[0]
    centroids = [vectors[rng.integers(n)]]
    for _ in range(1, k):
        sims_to_nearest = np.max([vectors @ c for c in centroids], axis=0)
        dists = np.clip(1 - sims_to_nearest, 0, None)
        total = dists.sum()
        probs = dists / total if total > 0 else np.full(n, 1 / n)
        idx = rng.choice(n, p=probs)
        centroids.append(vectors[idx])
    return np.array(centroids)


def spherical_kmeans(
    vectors: np.ndarray, k: int, init_centroids: np.ndarray | None, max_iter: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """コサイン類似度ベースの球面k-means。(assignments, centroids)を返す。
    vectors は事前にL2正規化済みであること。"""
    rng = np.random.default_rng(seed)
    n = vectors.shape[0]
    k = max(1, min(k, n))

    if init_centroids is not None and len(init_centroids) > 0:
        base = np.array(init_centroids[:k], dtype=np.float64)
        norms = np.linalg.norm(base, axis=1, keepdims=True)
        norms[norms == 0] = 1
        base = base / norms
        if len(base) < k:
            extra = _kmeanspp_init(vectors, k - len(base), rng)
            centroids = np.vstack([base, extra])
        else:
            centroids = base
    else:
        centroids = _kmeanspp_init(vectors, k, rng)

    assignments = np.full(n, -1)
    for iteration in range(max_iter):
        sims = vectors @ centroids.T  # (n, k) コサイン類似度(両者単位ベクトルのため内積で求まる)
        new_assignments = np.argmax(sims, axis=1)
        if iteration > 0 and np.array_equal(new_assignments, assignments):
            break
        assignments = new_assignments

        new_centroids = np.zeros_like(centroids)
        for c in range(k):
            members = vectors[assignments == c]
            if len(members) == 0:
                # 空クラスタは、現在最も所属centroidから遠い点を新centroidとして再シードする
                nearest_sim = np.max(sims, axis=1)
                farthest = int(np.argmin(nearest_sim))
                new_centroids[c] = vectors[farthest]
                continue
            mean = members.mean(axis=0)
            norm = np.linalg.norm(mean)
            new_centroids[c] = mean / norm if norm > 0 else mean
        centroids = new_centroids

    return assignments, centroids


def choose_k(n: int, override: int | None) -> int:
    if override is not None:
        return max(1, min(override, n))
    k = round((n / 2) ** 0.5)
    return max(DEFAULT_MIN_K, min(DEFAULT_MAX_K, k, n))


# ---------------------------------------------------------------- ID引き継ぎ・ラベル生成


def members_hash(member_paths: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(member_paths)).encode("utf-8")).hexdigest()[:16]


def match_cluster_ids(
    new_centroids: np.ndarray, prev_clusters: list[dict], threshold: float = MATCH_THRESHOLD
) -> list[str | None]:
    """新クラスタそれぞれについて、コサイン類似度が最大かつ閾値以上の前回クラスタIDを
    貪欲マッチングで割り当てる(1対1)。マッチしなければNone(=新規ID採番)。"""
    if not prev_clusters or len(new_centroids) == 0:
        return [None] * len(new_centroids)

    prev_matrix = np.array([c["centroid"] for c in prev_clusters], dtype=np.float64)
    norms = np.linalg.norm(prev_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    prev_matrix = prev_matrix / norms

    sims = new_centroids @ prev_matrix.T  # (new_k, prev_k)
    pairs = [
        (sims[i, j], i, j)
        for i in range(sims.shape[0])
        for j in range(sims.shape[1])
        if sims[i, j] >= threshold
    ]
    pairs.sort(key=lambda x: -x[0])

    result: list[str | None] = [None] * len(new_centroids)
    assigned_new: set[int] = set()
    assigned_prev: set[int] = set()
    for _, i, j in pairs:
        if i in assigned_new or j in assigned_prev:
            continue
        result[i] = prev_clusters[j]["id"]
        assigned_new.add(i)
        assigned_prev.add(j)
    return result


def next_id_number(prev_clusters: list[dict]) -> int:
    nums = []
    for c in prev_clusters:
        cid = str(c.get("id", ""))
        if cid.startswith("c") and cid[1:].isdigit():
            nums.append(int(cid[1:]))
    return (max(nums) + 1) if nums else 1


def pick_representatives(
    member_indices: list[int], paths: list[str], vectors: np.ndarray, centroid: np.ndarray, fm_by_path: dict
) -> list[dict]:
    """centroidに近い順に代表ノートを選ぶ({"path", "title"}のリスト)。"""
    sims = [(float(vectors[i] @ centroid), i) for i in member_indices]
    sims.sort(key=lambda x: -x[0])
    reps = []
    for _, i in sims[:MAX_REPRESENTATIVES]:
        path = paths[i]
        fm = fm_by_path.get(path, {})
        reps.append({"path": path, "title": str(fm.get("title", path))})
    return reps


def main() -> int:
    args = parse_args()

    paths, vectors, embed_meta = load_note_vectors(args.embeddings)
    if len(paths) == 0:
        print("埋め込みindexにクラスタリング対象のノートがありません(スキップ)")
        return 0

    prev = {}
    prev_clusters: list[dict] = []
    if args.prev and args.prev.exists():
        try:
            prev = json.loads(args.prev.read_text(encoding="utf-8"))
            prev_clusters = prev.get("clusters") or []
        except json.JSONDecodeError:
            print(f"警告: {args.prev} を解釈できません。前回情報なしで実行します", file=sys.stderr)

    k = choose_k(len(paths), args.k)
    init_centroids = None
    if not args.recluster and prev_clusters:
        init_centroids = np.array([c["centroid"] for c in prev_clusters], dtype=np.float64)

    assignments, centroids = spherical_kmeans(vectors, k, init_centroids, KMEANS_MAX_ITER, KMEANS_SEED)
    actual_k = centroids.shape[0]

    matched_ids = match_cluster_ids(centroids, prev_clusters)
    next_num = next_id_number(prev_clusters)
    ids: list[str] = []
    for matched in matched_ids:
        if matched is not None:
            ids.append(matched)
        else:
            ids.append(f"c{next_num:02d}")
            next_num += 1

    prev_by_id = {c["id"]: c for c in prev_clusters}

    # 代表ノート選定・ラベル生成にはVault実ファイルのtitle/summary/tagsを使う
    # (embeddings.jsonのメタにはtagsが含まれないため)
    library = organize.load_library()
    fm_by_path = {str(n.path.relative_to(ROOT)): n.fm for n in library}

    client: llm_client.LLMClient | None = None
    pending_labels: list[int] = []

    clusters_out: list[dict] = []
    for c in range(actual_k):
        member_indices = [i for i, a in enumerate(assignments) if a == c]
        if not member_indices:
            continue  # 空クラスタは出力しない
        member_paths = [paths[i] for i in member_indices]
        m_hash = members_hash(member_paths)
        reps = pick_representatives(member_indices, paths, vectors, centroids[c], fm_by_path)

        prev_cluster = prev_by_id.get(ids[c])
        reuse_label = prev_cluster is not None and prev_cluster.get("membersHash") == m_hash

        entry = {
            "id": ids[c],
            "label": prev_cluster["label"] if reuse_label else None,
            "description": prev_cluster.get("description", "") if reuse_label else None,
            "keywords": prev_cluster.get("keywords", []) if reuse_label else None,
            "size": len(member_indices),
            "centroid": centroids[c].tolist(),
            "representatives": reps,
            "membersHash": m_hash,
        }
        if entry["label"] is None:
            pending_labels.append(len(clusters_out))
        clusters_out.append(entry)

    if pending_labels:
        client = llm_client.create_client()
        for idx in pending_labels:
            entry = clusters_out[idx]
            rep_info = [
                {
                    "title": fm_by_path.get(r["path"], {}).get("title", r["title"]),
                    "summary": fm_by_path.get(r["path"], {}).get("summary", ""),
                    "tags": [
                        t for t in (fm_by_path.get(r["path"], {}).get("tags", []) or [])
                        if t not in OPERATIONAL_TAGS
                    ],
                }
                for r in entry["representatives"]
            ]
            try:
                label_info = client.generate_cluster_label(rep_info)
            except llm_client.LLMError as e:
                print(f"警告: クラスタ{entry['id']}のラベル生成に失敗、暫定ラベルで続行: {e}", file=sys.stderr)
                label_info = {
                    "label": rep_info[0]["title"][:15] if rep_info else entry["id"],
                    "description": "",
                    "keywords": [],
                }
            entry["label"] = label_info["label"]
            entry["description"] = label_info["description"]
            entry["keywords"] = label_info["keywords"]
            print(f"* {entry['id']}: {entry['label']} ({entry['size']}件)")

    clusters_out.sort(key=lambda c: -c["size"])

    out = {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": embed_meta.get("model"),
        "dim": embed_meta.get("dim"),
        "clusters": clusters_out,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    relabeled = len(pending_labels)
    print(
        f"完了: {len(clusters_out)}クラスタ(対象{len(paths)}ノート) / "
        f"ラベル再生成{relabeled} / 据え置き{len(clusters_out) - relabeled}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
