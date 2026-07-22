"""memory/store 测试：mock chromadb + RemoteEmbeddingFunction，验证 ingest/query/冷启动/降级。"""
from unittest.mock import patch, MagicMock

import pytest


def test_remote_embedding_function_posts_and_returns_vectors():
    """RemoteEF.__call__ → POST /v1/embeddings，解析返回向量列表。"""
    with patch("memory.store.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp
        from memory.store import RemoteEmbeddingFunction
        ef = RemoteEmbeddingFunction("http://bge:8002")
        out = ef(["文本1", "文本2"])
        assert out == [[0.1, 0.2], [0.3, 0.4]]
        body = mock_post.call_args.kwargs["json"]
        assert body["input"] == ["文本1", "文本2"]
        assert body["model"] == "bge-large-zh"
        assert mock_post.call_args.args[0] == "http://bge:8002/v1/embeddings"


def test_memory_store_init_requires_embedding_url(monkeypatch):
    """无 EMBEDDING_BASE_URL 且未传 embedding_url → RuntimeError（→ get_memory_store 降级 None）。"""
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    with patch("memory.store.chromadb.PersistentClient"):
        from memory.store import MemoryStore
        with pytest.raises(RuntimeError):
            MemoryStore(path="./tmp_nourl")


def test_memory_store_ingest_calls_add_with_expected_actual_suspected():
    """ingest_issue → col.add，文档含 expected/actual/suspected。"""
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.RemoteEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore(path="./tmp", embedding_url="http://x")
        ms.col = MagicMock()
        issue = MagicMock(expected="160", actual="80", suspected_files=["App.tsx"],
                          minimal_steps=["1 click x"], stable_rate="3/3")
        timeline = MagicMock(events=[MagicMock(target="qty-input")], expected="160", actual="80")
        ms.ingest_issue(issue, timeline, None)
        ms.col.add.assert_called_once()
        doc = ms.col.add.call_args.kwargs["documents"][0]
        assert "160" in doc and "80" in doc and "App.tsx" in doc
        assert ms.col.add.call_args.kwargs["ids"][0]


def test_query_similar_empty_collection_returns_empty():
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.RemoteEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore(path="./tmp", embedding_url="http://x")
        ms.col = MagicMock()
        ms.col.count.return_value = 0
        timeline = MagicMock(events=[], expected="160", actual="80")
        assert ms.query_similar(timeline, []) == []


def test_query_similar_returns_ranked_results():
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.RemoteEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore(path="./tmp", embedding_url="http://x")
        ms.col = MagicMock()
        ms.col.count.return_value = 2
        ms.col.query.return_value = {
            "documents": [["d1", "d2"]],
            "metadatas": [[{"expected": "160"}, {"expected": "99"}]],
            "distances": [[0.1, 0.5]],
        }
        timeline = MagicMock(events=[MagicMock(target="qty")], expected="160", actual="80")
        out = ms.query_similar(timeline, [], top_k=2)
        assert len(out) == 2
        assert out[0]["doc"] == "d1" and out[0]["distance"] == 0.1


def test_get_memory_store_off_returns_none(monkeypatch):
    monkeypatch.setenv("REPROFORGE_MEMORY", "off")
    from memory.store import get_memory_store
    assert get_memory_store() is None


def test_get_memory_store_init_failure_returns_none(monkeypatch):
    """无 EMBEDDING_BASE_URL → MemoryStore 抛 RuntimeError → get_memory_store 返回 None。"""
    monkeypatch.setenv("REPROFORGE_MEMORY", "on")
    monkeypatch.delenv("EMBEDDING_BASE_URL", raising=False)
    with patch("memory.store.chromadb.PersistentClient"):
        from memory.store import get_memory_store
        assert get_memory_store() is None
