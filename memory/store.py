"""memory/store.py — chromadb 持久化 + bge-large-zh embedding（RAG 记忆库）

ingest_issue：Issue 入库；query_similar：检索相似历史 Bug。
失败/空库 → 由上层 recall 降级（investigator 照旧）。
"""
import os
import uuid

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


class MemoryStore:
    """本地持久化向量库（chromadb + bge-large-zh）。

    复用 faster-whisper 的 HF 下载环境变量（HF_ENDPOINT=hf-mirror + HF_HUB_DISABLE_XET=1）。
    """

    def __init__(self, path=None, model="BAAI/bge-large-zh-v1.5"):
        self.path = path or os.getenv("REPROFORGE_MEMORY_PATH", "./reproforge_memory")
        self.client = chromadb.PersistentClient(path=self.path)
        self.ef = SentenceTransformerEmbeddingFunction(model_name=model)
        self.col = self.client.get_or_create_collection("bug_issues", embedding_function=self.ef)

    def ingest_issue(self, issue, timeline, top_files):
        """Issue 入库。文档=expected+actual+可疑文件+testid；metadata 存复现细节。"""
        testids = " ".join(e.target for e in timeline.events if getattr(e, "target", None))
        doc = f"预期 {timeline.expected} 实际 {timeline.actual} "
        doc += " ".join(issue.suspected_files) + " " + testids
        self.col.add(
            documents=[doc],
            metadatas=[{
                "expected": timeline.expected or "",
                "actual": timeline.actual or "",
                "suspected": ",".join(issue.suspected_files),
                "minimal_steps": " | ".join(issue.minimal_steps),
                "stable_rate": issue.stable_rate or "",
            }],
            ids=[str(uuid.uuid4())],
        )

    def query_similar(self, timeline, actions, top_k=3):
        """检索相似历史 Bug。空库返回 []（冷启动）。"""
        if self.col.count() == 0:
            return []
        testids = " ".join(e.target for e in timeline.events if getattr(e, "target", None))
        query = f"预期 {timeline.expected} 实际 {timeline.actual} {testids}"
        res = self.col.query(query_texts=[query], n_results=top_k)
        return [{"doc": res["documents"][0][i], "metadata": res["metadatas"][0][i],
                 "distance": res["distances"][0][i]}
                for i in range(len(res["documents"][0]))]


def get_memory_store():
    """构造 MemoryStore；REPROFORGE_MEMORY=off 或初始化失败 → 返回 None（降级）。"""
    if os.getenv("REPROFORGE_MEMORY", "on").lower() == "off":
        return None
    try:
        return MemoryStore()
    except Exception:
        return None
