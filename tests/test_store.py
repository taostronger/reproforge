"""memory/store 测试：mock chromadb，验证 ingest/query/冷启动/开关降级。

不真初始化 bge（mock PersistentClient + SentenceTransformerEmbeddingFunction）。
"""
from unittest.mock import patch, MagicMock


def test_memory_store_ingest_calls_add_with_expected_actual_suspected():
    """ingest_issue → col.add，文档含 expected/actual/suspected。"""
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.SentenceTransformerEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore()
        ms.col = MagicMock()
        issue = MagicMock(expected="160", actual="80", suspected_files=["App.tsx"],
                          minimal_steps=["1 click x"], stable_rate="3/3")
        timeline = MagicMock(events=[MagicMock(target="qty-input")], expected="160", actual="80")
        ms.ingest_issue(issue, timeline, None)
        ms.col.add.assert_called_once()
        doc = ms.col.add.call_args.kwargs["documents"][0]
        assert "160" in doc and "80" in doc and "App.tsx" in doc
        assert ms.col.add.call_args.kwargs["ids"][0]   # uuid 非空


def test_query_similar_empty_collection_returns_empty():
    """空库（count=0）→ []（冷启动）。"""
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.SentenceTransformerEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore()
        ms.col = MagicMock()
        ms.col.count.return_value = 0
        timeline = MagicMock(events=[], expected="160", actual="80")
        assert ms.query_similar(timeline, []) == []


def test_query_similar_returns_ranked_results():
    """有数据 → 返回 doc/metadata/distance 列表。"""
    with patch("memory.store.chromadb.PersistentClient"), \
         patch("memory.store.SentenceTransformerEmbeddingFunction"):
        from memory.store import MemoryStore
        ms = MemoryStore()
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
    """REPROFORGE_MEMORY=off → None（降级）。"""
    monkeypatch.setenv("REPROFORGE_MEMORY", "off")
    from memory.store import get_memory_store
    assert get_memory_store() is None


def test_get_memory_store_init_failure_returns_none(monkeypatch):
    """MemoryStore 初始化失败 → None（降级，不抛）。"""
    monkeypatch.setenv("REPROFORGE_MEMORY", "on")
    with patch("memory.store.chromadb.PersistentClient", side_effect=Exception("no chromadb")):
        from memory.store import get_memory_store
        assert get_memory_store() is None
