"""Task 2.5 测试：ripgrep + tree-sitter 代码检索（真实 demo_project + rg）。"""
from pathlib import Path

from code_search.search import search, FileHit

DEMO = Path(__file__).resolve().parent.parent / "demo_project"


def test_search_total_price_hits_app_tsx():
    hits = search(["total-price"], DEMO)
    assert hits, "应命中 total-price"
    paths = [h.path.replace("\\", "/") for h in hits]
    assert any("App.tsx" in p for p in paths), f"未命中 App.tsx: {paths}"


def test_search_aggregates_and_ranks_desc():
    hits = search(["coupon", "total-price"], DEMO)
    assert hits
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True), scores
    top = hits[0]
    assert isinstance(top, FileHit)
    assert top.matches >= 1
    assert top.snippet.strip()


def test_search_no_match_returns_empty():
    hits = search(["zzz_no_such_token_xyz_123"], DEMO)
    assert hits == []


def test_search_context_is_string_best_effort():
    # applyCoupon 是 App 内的函数；context best-effort 提取，不强非空，但不报错
    hits = search(["applyCoupon"], DEMO)
    assert isinstance(hits, list)
    if hits:
        assert isinstance(hits[0].context, str)
