"""Reranker benchmark（Phase2 backlog·三档决策框架补 reranker 档）。

两阶段：向量召回 top-N → gte-rerank(dashscope，同 EMBED key) → top-k。
对比 baseline(向量 top-3) vs rerank(向量 top-N → rerank top-3)，验证四问：
- H1 排序：rerank 提 MRR/R@1？
- H2 跨族/049：gold 跨 ≥2 族的 query，rerank 把弱势族(如换货)顶进 top-3、修 049？
- H3a abstain(query 级/top1)：每条 query 的 top1 rerank 分，能否阈值分开 in-scope/out-of-scope？
- H3b grader 替代(块级/per-chunk)：相关块 vs 不相关块的 rerank 分，能否阈值分开 → 替 per-chunk grader？

跑：python -m src.eval.rerank_benchmark
"""
import json
import os
from collections import defaultdict

import requests
from dotenv import load_dotenv

from src.eval.retrieval import (_embed, chunk_baseline, build_index, retrieve,
                                score_query, CORPUS_PATH, EVAL_PATH, ROOT)

load_dotenv(ROOT / ".env")
RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
RERANK_KEY = os.environ["EMBED_API_KEY"]
N_RECALL = 8   # 向量召回池大小
TOP_K = 3


def _rerank(query: str, docs: list[str]) -> list[dict]:
    """gte-rerank：返回 [{index, relevance_score}] 按分降序。"""
    payload = {"model": "gte-rerank-v2",
               "input": {"query": query, "documents": docs},
               "parameters": {"return_documents": False, "top_n": len(docs)}}
    r = requests.post(RERANK_URL, headers={"Authorization": f"Bearer {RERANK_KEY}",
                                           "Content-Type": "application/json"},
                      json=payload, timeout=30)
    return sorted(r.json()["output"]["results"], key=lambda x: -x["relevance_score"])


def _family(item_id: str) -> str:
    return item_id.split("-")[0]


def run():
    items = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    queries = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    chunks = chunk_baseline(items)
    coll = build_index(chunks)
    id2text = {c.id: c.text for c in chunks}
    id2item = {c.id: c.item_ids[0] for c in chunks}
    q_embs = _embed([q["query"] for q in queries])
    print(f"索引 {len(chunks)} chunk；召回池 N={N_RECALL} → rerank top{TOP_K}\n")

    agg = defaultdict(lambda: defaultdict(list))   # H1: method -> metric -> [vals]
    gold_rr, neg_rr = [], []                       # H3a: query 级 top1 分
    rel_ch, irr_goldq_ch, irr_negq_ch = [], [], []  # H3b: 块级分（相关/gold-query非gold/负样本query块）
    cross = {}                                     # H2: 跨族 query 覆盖

    for q, qe in zip(queries, q_embs):
        gold = set(q["relevant_items"])
        is_neg = not gold
        pool = retrieve(coll, qe, N_RECALL)                 # 向量 top-N
        docs = [id2text[r.chunk_id] for r in pool]
        order = _rerank(q["query"], docs)
        reranked = [pool[o["index"]] for o in order]

        # H3b：逐块收集 rerank 分 + 相关性标签
        for o in order:
            item = id2item[pool[o["index"]].chunk_id]
            s = round(o["relevance_score"], 4)
            (rel_ch if item in gold else (irr_negq_ch if is_neg else irr_goldq_ch)
             ).append((q["id"], item, s))

        # H3a：query 级 top1
        rr_top1 = round(order[0]["relevance_score"], 4)
        if is_neg:
            neg_rr.append((q["id"], rr_top1))
            continue
        gold_rr.append((q["id"], rr_top1))

        # H1：向量 top3 vs rerank top3
        for method, rlist in [("vec_top3", pool), ("rerank_top3", reranked)]:
            for k in (1, 3):
                agg[method][f"R@{k}"].append(score_query(rlist, gold, k)["recall"])
            agg[method]["MRR"].append(score_query(rlist, gold, TOP_K)["mrr"])
            agg[method]["P@3"].append(score_query(rlist, gold, 3)["precision"])

        # H2：gold 跨 ≥2 族 = 跨族 query
        if len({_family(g) for g in gold}) >= 2:
            cross[q["id"]] = {"gold": sorted(gold),
                              "vec_top3命中": score_query(pool, gold, 3)["covered"],
                              "rerank_top3命中": score_query(reranked, gold, 3)["covered"]}

    def avg(xs): return sum(xs) / len(xs) if xs else 0.0
    print("=" * 62, "\nH1 排序：向量 top3 vs rerank top3（gold 桶聚合）")
    print(f"  {'method':14} {'R@1':>6} {'R@3':>6} {'MRR':>6} {'P@3':>6}")
    for m in ("vec_top3", "rerank_top3"):
        d = agg[m]
        print(f"  {m:14} {avg(d['R@1']):6.2f} {avg(d['R@3']):6.2f} {avg(d['MRR']):6.2f} {avg(d['P@3']):6.2f}")

    print("\nH2 跨族(gold 跨≥2族)：rerank 有没有把弱势族顶进 top3")
    for qid, d in cross.items():
        print(f"  [{qid}] gold={d['gold']}\n        vec命中={d['vec_top3命中']}  rerank命中={d['rerank_top3命中']}")

    print("\nH3a abstain(query 级 top1)：in-scope 该高、out-of-scope 该低")
    g = sorted(s for _, s in gold_rr); n = sorted(s for _, s in neg_rr)
    print(f"  in-scope(n={len(g)}): min={g[0]} ~ max={g[-1]}")
    print(f"  out-scope(n={len(n)}): min={n[0]} ~ max={n[-1]}")
    print(f"  → in最低 {g[0]} vs out最高 {n[-1]}：{'分得开 gap='+str(round(g[0]-n[-1],4)) if g[0]>n[-1] else '重叠 '+str(round(n[-1]-g[0],4))}")

    print("\nH3b grader替代(块级 per-chunk)：相关块 vs 不相关块")
    irr = irr_goldq_ch + irr_negq_ch
    rs = sorted(x[2] for x in rel_ch); is_ = sorted(x[2] for x in irr)
    print(f"  相关块(n={len(rel_ch)}): min={rs[0]} ~ max={rs[-1]}  中位≈{rs[len(rs)//2]}")
    print(f"  不相关块(n={len(irr)}): min={is_[0]} ~ max={is_[-1]}  中位≈{is_[len(is_)//2]}")
    leak = sum(1 for s in is_ if s >= rs[0])
    print(f"  → 相关最低 {rs[0]} vs 不相关最高 {is_[-1]}：{'分得开' if rs[0]>is_[-1] else '重叠 '+str(round(is_[-1]-rs[0],4))}"
          f"；阈值卡相关最低时不相关漏 {leak}/{len(irr)}")
    print("  不相关块 top5 高分(骗过 rerank)：", sorted(irr, key=lambda x: -x[2])[:5])
    print("  相关块 bottom5 低分(rerank 失手)：", sorted(rel_ch, key=lambda x: x[2])[:5])

    (ROOT / "logs" / "rerank_benchmark_result.json").write_text(
        json.dumps({"H1": {m: {k: avg(v) for k, v in d.items()} for m, d in agg.items()},
                    "H2_cross_family": cross,
                    "H3a_query_top1": {"gold": gold_rr, "neg": neg_rr},
                    "H3b_per_chunk": {"relevant": rel_ch, "irr_goldq": irr_goldq_ch, "irr_negq": irr_negq_ch},
                    "config": {"n_recall": N_RECALL, "top_k": TOP_K, "model": "gte-rerank-v2"}},
                   ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    run()
