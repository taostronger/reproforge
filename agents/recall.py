"""agents/recall.py — RAG 检索节点（历史 Bug 记忆）

investigator 前置：检索相似历史 Bug 作参考。
store=None / 空库 / 任何失败 → 返回空 HistoricalRef（investigator 照旧，降级）。
"""
from dataclasses import dataclass, field


@dataclass
class HistoricalRef:
    items: list = field(default_factory=list)   # query_similar 结果
    used: bool = False                          # 是否真的用了记忆


def recall(timeline, actions, store=None, top_k=3):
    """检索相似历史 Bug。store=None / 空库 / 失败 → 空 HistoricalRef（降级）。"""
    if store is None:
        return HistoricalRef()
    try:
        items = store.query_similar(timeline, actions, top_k=top_k)
        return HistoricalRef(items=items, used=bool(items))
    except Exception:
        return HistoricalRef()
