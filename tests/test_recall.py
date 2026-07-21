"""recall 测试：store=None / 空库 / 异常 → 降级；有命中 → used=True。"""
from unittest.mock import MagicMock

from agents.recall import recall, HistoricalRef


def test_recall_no_store_returns_empty():
    """store=None → 空 HistoricalRef（降级）。"""
    ref = recall(MagicMock(events=[], expected="160", actual="80"), [], store=None)
    assert isinstance(ref, HistoricalRef)
    assert ref.used is False
    assert ref.items == []


def test_recall_empty_store_returns_empty():
    """库空 → used=False。"""
    store = MagicMock()
    store.query_similar.return_value = []
    ref = recall(MagicMock(events=[], expected="160", actual="80"), [], store=store)
    assert ref.used is False


def test_recall_with_hits_marks_used():
    """有命中 → used=True，items 非空。"""
    store = MagicMock()
    store.query_similar.return_value = [
        {"doc": "预期160实际80 App.tsx", "metadata": {"suspected": "App.tsx"}, "distance": 0.1}]
    ref = recall(MagicMock(events=[], expected="160", actual="80"), [], store=store)
    assert ref.used is True
    assert len(ref.items) == 1


def test_recall_store_failure_degrades():
    """store.query_similar 抛异常 → 空 HistoricalRef（降级）。"""
    store = MagicMock()
    store.query_similar.side_effect = Exception("db down")
    ref = recall(MagicMock(events=[], expected="160", actual="80"), [], store=store)
    assert ref.used is False
