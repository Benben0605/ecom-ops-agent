"""Phase2 检索评估判分器（依赖链③）。

裁判地基：读 corpus.json + retrieval_eval.json，对 baseline 检索管线算
Recall@k / Precision@k / MRR（item 级，跨 chunk 策略可比，见检索评估数据契约）。

设计：
- chunker 可插拔（EXP-2 换 chunk 策略零改判分器）；baseline = 1 item/chunk。
- 用独立 chroma collection（不碰 kb_search 的 "faq"，Phase0/L1/L2 零回归）。
- 指标锚 item_id 不锚 chunk_id：chunk 带 item_ids metadata，判分把检索回的
  chunk 映射回它覆盖的 item_ids 再比 gold。chunk 策略随便换、gold 不动。
- 负样本（gold=[]）单列：Recall 不适用，报 top 相似度，为后续 abstain 阈值铺路。
"""
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import chromadb
from openai import OpenAI

from src import config

ROOT = Path(__file__).parents[1]
CORPUS_PATH = ROOT / "data" / "faq" / "corpus.json"
EVAL_PATH = ROOT / "data" / "retrieval_eval.json"
CHROMA_DIR = ROOT / ".chroma_eval"  # 独立目录，与生产 kb_search 的 .chroma 隔离
COLLECTION = "faq_corpus_eval"

KS = (1, 3, 5)  # 报多个 k，给 top_k EXP-3 看曲线

embed_client = OpenAI(api_key=config.EMBED_API_KEY, base_url=config.EMBED_BASE_URL)


def _embed(texts: list[str]) -> list[list[float]]:
    # 通义 batch 上限保守取 10
    out: list[list[float]] = []
    for i in range(0, len(texts), 10):
        r = embed_client.embeddings.create(model=config.EMBED_MODEL, input=texts[i:i + 10])
        out.extend(d.embedding for d in r.data)
    return out


@dataclass
class Chunk:
    id: str
    text: str               # 喂 embedding 的文本
    item_ids: list[str]     # 这个 chunk 覆盖哪些原子单元（判分命根子）


# ========== 可插拔 chunker（EXP-2 在这里加策略）==========
def chunk_baseline(items: list[dict]) -> list[Chunk]:
    """baseline：1 item/chunk，text = heading + content。"""
    return [Chunk(id=it["id"], text=f"{it['heading']}\n{it['content']}", item_ids=[it["id"]])
            for it in items]


def build_index(chunks: list[Chunk]) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # 每次重建保证干净（chunk 策略可能变），collection 名固定
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    embeddings = _embed([c.text for c in chunks])
    coll.add(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=[c.text for c in chunks],
        metadatas=[{"item_ids": ",".join(c.item_ids)} for c in chunks],
    )
    return coll


@dataclass
class Retrieved:
    chunk_id: str
    item_ids: list[str]
    distance: float


def retrieve(coll, query_emb: list[float], top_k: int) -> list[Retrieved]:
    r = coll.query(query_embeddings=[query_emb], n_results=top_k,
                   include=["metadatas", "distances"])
    return [Retrieved(chunk_id=cid,
                      item_ids=m["item_ids"].split(",") if m["item_ids"] else [],
                      distance=dist)
            for cid, m, dist in zip(r["ids"][0], r["metadatas"][0], r["distances"][0])]


def score_query(retrieved: list[Retrieved], gold: set[str], k: int) -> dict:
    """item 级指标。gold 非空才算 Recall/Precision/MRR。"""
    topk = retrieved[:k]
    covered = set()
    for r in topk:
        covered |= (set(r.item_ids) & gold)
    recall = len(covered) / len(gold) if gold else None
    # Precision@k：top-k 里"命中至少一个 gold item"的 chunk 占比
    hit_chunks = sum(1 for r in topk if set(r.item_ids) & gold)
    precision = hit_chunks / k if gold else None
    # MRR：第一个命中 gold 的 chunk 排名倒数
    mrr = 0.0
    top3sims = [round(1 - r.distance, 3) for r in retrieved[:3]]
    for rank, r in enumerate(topk, 1):
        if set(r.item_ids) & gold:
            mrr = 1 / rank
            break
    return {"recall": recall, "precision": precision, "mrr": mrr,
            "covered": sorted(covered), "top3sims": top3sims}


def run():
    items = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(EVAL_PATH.read_text(encoding="utf-8"))

    chunks = chunk_baseline(items)
    coll = build_index(chunks)
    print(f"索引：{len(chunks)} chunk（baseline 1 item/chunk）\n")

    q_embs = _embed([q["query"] for q in queries])
    maxk = max(KS)

    # 分桶聚合
    from collections import defaultdict
    agg = defaultdict(lambda: defaultdict(list))   # bucket -> metric@k -> [vals]
    neg_rows = []
    per_query = []

    for q, qe in zip(queries, q_embs):
        gold = set(q["relevant_items"])
        retrieved = retrieve(coll, qe, maxk)
        if not gold:  # 负样本
            top3sims = [round(1 - r.distance, 3) for r in retrieved[:3]]
            neg_rows.append((q["id"], q["query"], retrieved[0].item_ids, top3sims,
                             [r.item_ids[0] for r in retrieved]))
            continue
        row = {"id": q["id"], "bucket": q["bucket"], "gold": sorted(gold)}
        for k in KS:
            s = score_query(retrieved, gold, k)
            row[f"R@{k}"] = s["recall"]
            row[f"P@{k}"] = s["precision"]
            agg[q["bucket"]][f"R@{k}"].append(s["recall"])
            agg[q["bucket"]][f"P@{k}"].append(s["precision"])
            agg["ALL"][f"R@{k}"].append(s["recall"])
            agg["ALL"][f"P@{k}"].append(s["precision"])
        final = score_query(retrieved, gold, maxk)
        row["MRR"] = final["mrr"]
        row["top3sims"] = final["top3sims"]
        agg[q["bucket"]]["MRR"].append(final["mrr"])
        agg["ALL"]["MRR"].append(final["mrr"])
        row["missed"] = sorted(gold - set(final["covered"]))
        per_query.append(row)

    # ---- 打印 ----
    print("=" * 70, "\n每条 query（gold 桶）")
    for r in per_query:
        miss = f"  漏:{r['missed']}" if r["missed"] else ""
        sims = r["top3sims"]
        print(f"  [{r['id']}] {r['bucket']:10} R@1={r['R@1']:.2f} R@3={r['R@3']:.2f} "
              f"R@5={r['R@5']:.2f} P@3={r['P@3']:.2f} MRR={r['MRR']:.2f}{miss} "
              f"top3sims={sims}")

    print("\n负样本（gold=[]，top1相似度越低越该 abstain）")
    for qid, query, top_items, top3sims, _ in neg_rows:
        print(f"  [{qid}] top3sims={top3sims}  误检top1={top_items}  «{query}»")

    def avg(xs): return sum(xs) / len(xs) if xs else 0.0
    print("\n" + "=" * 70, "\n分桶聚合（macro 平均）")
    order = ["direct", "cross_item", "paraphrase", "confusing", "ALL"]
    print(f"  {'bucket':12} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'P@3':>6} {'MRR':>6}  n")
    for b in order:
        if b not in agg: continue
        m = agg[b]
        n = len(m["R@3"])
        print(f"  {b:12} {avg(m['R@1']):6.2f} {avg(m['R@3']):6.2f} {avg(m['R@5']):6.2f} "
              f"{avg(m['P@3']):6.2f} {avg(m['MRR']):6.2f}  {n}")

    out = {"per_query": per_query, "negative": neg_rows,
           "aggregate": {b: {k: avg(v) for k, v in m.items()} for b, m in agg.items()}}
    (ROOT / "logs" / "retrieval_eval_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run()
