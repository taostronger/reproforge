"""memory/store.py — chromadb 持久化 + 远程 bge embedding（spark-71 服务）。

ingest_issue：Issue 入库；query_similar：检索相似历史 Bug。
无 EMBEDDING_BASE_URL / 服务不可用 / 空库 → 由上层 recall 降级（investigator 照旧）。

设计：embedding 算力下沉 spark-71（bge 服务），本地只留 chromadb 向量库 + requests。
演示机不再需要 torch/sentence-transformers。
"""
import os
import uuid

import chromadb
import requests


class RemoteEmbeddingFunction:
    """调远程 bge 服务的 /v1/embeddings（OpenAI 兼容），符合 chromadb EF 协议。"""

    def __init__(self, base_url, model="bge-large-zh", timeout=30):
        self.base_url = base_url
        self.model = model
        self.timeout = timeout

    def __call__(self, input: list[str]) -> list[list[float]]:
        # chromadb 0.5+ 要求 __call__ 带 (input) -> Embeddings 类型注解
        resp = requests.post(
            f"{self.base_url}/v1/embeddings",
            json={"input": input, "model": self.model},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return [d["embedding"] for d in resp.json()["data"]]


class MemoryStore:
    """本地持久化向量库（chromadb）+ 远程 embedding（spark-71 bge）。"""

    def __init__(self, path=None, embedding_url=None, embedding_model="bge-large-zh"):
        self.path = path or os.getenv("REPROFORGE_MEMORY_PATH", "./reproforge_memory")
        url = embedding_url or os.getenv("EMBEDDING_BASE_URL")
        if not url:
            raise RuntimeError("无 EMBEDDING_BASE_URL，远程 embedding 不可用")
        self.client = chromadb.PersistentClient(path=self.path)
        self.ef = RemoteEmbeddingFunction(url, embedding_model)
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

    def list_all(self):
        """返回所有历史 Bug Issue（UI 展示用）。空库 → []。"""
        if self.col.count() == 0:
            return []
        data = self.col.get(include=["documents", "metadatas"])
        return [{"doc": data["documents"][i], **(data["metadatas"][i] or {})}
                for i in range(len(data["documents"]))]


def get_memory_store():
    """构造 MemoryStore；REPROFORGE_MEMORY=off 或初始化失败 → 返回 None（降级）。"""
    if os.getenv("REPROFORGE_MEMORY", "on").lower() == "off":
        return None
    try:
        return MemoryStore()
    except Exception:
        return None
