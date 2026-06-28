"""KB 检索工具（Phase2：corpus.json 语料 + LLM relevance grader 门控 abstain）。

管线：建一次索引（懒加载，修了旧版每次 run 重建的浪费）→ 向量检索 top_k →
LLM grader 判「这些片段真能回答吗」→ 答不上返回 ABSTAIN（让 agent 走 escalate/诚实
拒答，而非拿话题贴脸但没答案的片段硬编）。

为什么要 grader：几何信号（top1 相似度 / top1-top2 margin）分不出「话题贴近但没答案」
（保质期≈保修 0.718、未付款取消≈支付失败 0.764 都骗过相似度阈值）。验证：10 负样本+17
gold 上 grader 27/27，阈值法漏 2。分层（cutoff 粗筛+grader 灰区）省一半 call 但 cutoff
钉在小样本极值上过拟合，等合成更大评估集校准后再上——现取最稳的纯 grader。
"""
import json
from pathlib import Path

import chromadb
from openai import OpenAI

from src import config

CHROMA_DIR = Path(__file__).parents[2] / ".chroma"
COLLECTION_NAME = "faq"
CORPUS_PATH = Path(__file__).parents[2] / "data" / "faq" / "corpus.json"
ABSTAIN = "知识库中未找到能回答该问题的相关内容。"

GRADER_ENABLED = True  # 测试可关，做 before/after 对比

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
embed_client = OpenAI(api_key=config.EMBED_API_KEY, base_url=config.EMBED_BASE_URL)
chat_client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

GRADER_PROMPT = """你是检索相关性裁判。给你用户问题和若干已编号的知识库片段，【逐个】判断每个片段是否与问题【相关】（在问题所问的话题上、提供了对回答有用的信息）。
关键原则：片段只要落在问题的话题上、有可用信息就算相关，哪怕没覆盖问题的每个细节（细节缺失交给下游诚实说明，不是丢弃的理由）。只有当片段讲的是【另一个话题】、对该问题毫无帮助时才算不相关。
例：问"换货怎么弄"，片段讲"换货时限/运费" → 相关（换货话题、有用，即使没给操作步骤）。
例：问"保质期多久"，片段讲"保修1年" → 不相关（保修≠保质期，另一个话题）。
例：问"未付款多久自动取消"，片段讲"支付失败10分钟可重下单" → 不相关（讲的是支付失败、非自动取消，帮不上）。
只输出 JSON：{"verdicts": [{"idx": 0, "relevant": true/false, "reason": "一句话"}, ...]}（idx 对应片段编号，逐个判全）"""


def _embed(texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for i in range(0, len(texts), 10):  # 通义 batch 上限保守取 10
        r = embed_client.embeddings.create(model=config.EMBED_MODEL, input=texts[i:i + 10])
        out.extend(d.embedding for d in r.data)
    return out


_indexed = False


def _ensure_index():
    """首次调用建一次索引（语料静态，进程内只建一次）。"""
    global _indexed
    if _indexed:
        return
    items = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    try:
        chroma_client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    coll = chroma_client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    texts = [f"{it['heading']}\n{it['content']}" for it in items]
    coll.add(
        ids=[it["id"] for it in items],
        embeddings=_embed(texts),
        documents=texts,
        metadatas=[{"item_id": it["id"], "theme": it["theme"]} for it in items],
    )
    _indexed = True


def _grade_chunks(query: str, passages: list[str]) -> list[dict]:
    """逐块判相关性（CRAG/self-RAG grade_documents）：一个结构化 call 返回 per-chunk 裁定。
    返回与 passages 对齐的 [{relevant: bool, reason: str}]。"""
    numbered = "\n".join(f"[{i}] {p}" for i, p in enumerate(passages))
    payload = f"用户问题：{query}\n\n知识库片段（共 {len(passages)} 条）：\n{numbered}"
    r = chat_client.chat.completions.create(
        model=config.MODEL, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": GRADER_PROMPT},
                  {"role": "user", "content": payload}],
    )
    by_idx = {d["idx"]: d for d in json.loads(r.choices[0].message.content).get("verdicts", [])}
    return [by_idx.get(i, {"relevant": True, "reason": ""}) for i in range(len(passages))]


# RAG 可观测性：记录每次检索的「query→逐块命中(sim,relevant)→留哪些/abstain」，供回归追溯与人工裁决
TRACE: list = []


def run(query: str, top_k: int = 3) -> str:
    _ensure_index()
    coll = chroma_client.get_collection(COLLECTION_NAME)
    result = coll.query(query_embeddings=[_embed([query])[0]], n_results=top_k,
                        include=["documents", "metadatas", "distances"])
    passages = result["documents"][0]
    verdicts = (_grade_chunks(query, passages) if GRADER_ENABLED
                else [{"relevant": True, "reason": ""} for _ in passages])
    kept = [p for p, v in zip(passages, verdicts) if v["relevant"]]
    chunks = [{"item": m["item_id"], "sim": round(1 - d, 3),
               "relevant": v["relevant"], "reason": v["reason"]}
              for m, d, v in zip(result["metadatas"][0], result["distances"][0], verdicts)]
    TRACE.append({"query": query, "chunks": chunks, "kept": len(kept),
                  "outcome": "answer" if kept else "abstain"})
    return "\n\n".join(kept) if kept else ABSTAIN


if __name__ == "__main__":
    for q in ["食品能退吗", "七天无理由退货怎么申请", "支持海外直邮到美国吗", "商品的保质期是多久"]:
        print(f"\nquery: {q}\n→ {run(q)}")
