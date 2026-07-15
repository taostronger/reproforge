"""Task 2.3 测试：候选检测 + 最小复现算法。runner 用 mock。"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from minimization.minimize import minimize, is_candidate_for_removal


class _R:
    def __init__(self, passed):
        self.passed = passed


def test_candidate_detection():
    assert is_candidate_for_removal("click", text="查看个人中心")
    assert is_candidate_for_removal("click", text="切换图片")
    assert is_candidate_for_removal("hover", text="任意")
    assert not is_candidate_for_removal("fill", text="优惠码")
    assert not is_candidate_for_removal("click", text="加入购物车")


def test_minimize_removes_irrelevant():
    # runner 永远复现(passed=False) → 所有候选都删
    original = [
        {"type": "click", "text": "查看个人中心"},   # 候选
        {"type": "fill", "text": "优惠码"},          # 关键，保留
        {"type": "click", "text": "应用"},           # 关键，保留
        {"type": "click", "text": "切换图片"},       # 候选
        {"type": "fill", "text": "数量"},            # 关键，保留
    ]
    result = minimize(original, lambda s: _R(False))
    assert result.original_count == 5
    assert result.removed_count == 2  # 删 2 个候选
    assert result.minimized_count == 3
    texts = [s["text"] for s in result.steps]
    assert "优惠码" in texts and "应用" in texts and "数量" in texts


def test_minimize_keeps_when_bug_gone():
    # runner 删候选后 Bug 消失(passed=True) → 不删
    original = [
        {"type": "click", "text": "切换图片"},
        {"type": "fill", "text": "数量"},
    ]
    full = lambda steps: _R(False) if len(steps) == 2 else _R(True)
    result = minimize(original, full)
    assert result.removed_count == 0  # 删了 Bug 消失，保留
    assert result.minimized_count == 2
