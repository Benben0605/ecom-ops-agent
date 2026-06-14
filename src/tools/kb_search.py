from dataclasses import dataclass
import hashlib
from pathlib import Path

import chromadb
from openai import OpenAI
from src import config

CHROMA_DIR = Path(__file__).parents[2] / ".chroma"
COLLECTION_NAME = "faq"

chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))

embed_client = OpenAI(api_key=config.EMBED_API_KEY, base_url=config.EMBED_BASE_URL)

@dataclass
class Chunk:
    id: str
    content: str
    heading: str

def _embed(texts: list[str]) -> list[list[float]]:
    r = embed_client.embeddings.create(model=config.EMBED_MODEL, input=texts)
    return [d.embedding for d in r.data]

def init_chunks_embeddings(path: Path):
    raw_text = path.read_text()

    chunks: list[Chunk] = []
    for section in raw_text.split("\n## ")[1:]:
        heading, _, content = section.partition("\n")
        chunks.append(Chunk(
            id=hashlib.md5(f"{path.name}::{heading}::{content}".encode()).hexdigest(),
            content=content.strip(),
            heading=heading,
            )
        )
    
    embeddings = _embed([f"{c.heading}\n{c.content}" for c in chunks])

    collection = chroma_client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    collection.upsert(
        ids=[c.id for c in chunks],
        embeddings=embeddings,
        documents=[c.content for c in chunks],
        metadatas=[{"heading": c.heading} for c in chunks],
    )

def run(query: str, top_k: int=3) -> str:
    # TODO(你来写 · Week1-Step4)：基础 RAG 检索
    #   1. 加载 data/faq/ 下的文档并切分成块
    #   2. embedding + 存向量库（如 chroma），首次构建后可缓存
    #   3. 用 query 检索 top-k，拼成上下文字符串返回
    init_chunks_embeddings(Path(__file__).parents[2] / "data" / "faq" / "退换货政策.md")
    
    query_embedding = _embed([query])[0]

    collection = chroma_client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas"],
    )
    return "\n".join(f"{m['heading']}\n{d}" for m, d in zip(result["metadatas"][0], result["documents"][0]))

if __name__ == "__main__":
    run(query="七天可以退货吗", top_k=1)
