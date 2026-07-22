"""Task 2.3 测试：候选检测 + 最小复现算法。runner 用 mock。"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from minimization.minimize import minimize, is_candidate_for_removal


class _R:
    def __init__(self, passed):
        self.passed = passed


def test_candidate_detection():
    # click/hover 都候选（minimize 重跑验证决定真删/保留）；fill/select 保留
    assert is_candidate_for_removal("click", text="查看个人中心")
    assert is_candidate_for_removal("click", text="加入购物车")  # 加入购物车也候选
    assert is_candidate_for_removal("click", text="apply-btn")
    assert is_candidate_for_removal("hover", text="任意")
    assert not is_candidate_for_removal("fill", text="优惠码")
    assert not is_candidate_for_removal("select", text="x")


def test_minimize_removes_irrelevant():
    # runner: 关键三步都在才复现(passed=False)；删关键→Bug不在(True)→保留，删无关→Bug仍在→真删
    original = [
        {"type": "click", "text": "查看个人中心"},   # 无关→删
        {"type": "fill", "text": "优惠码"},          # 关键(fill 不候选)→保留
        {"type": "click", "text": "应用"},           # 关键→删了Bug不在→保留
        {"type": "click", "text": "切换图片"},       # 无关→删
        {"type": "fill", "text": "数量"},            # 关键→保留
    ]
    critical = {"优惠码", "应用", "数量"}
    runner = lambda steps: _R(False) if critical <= {s["text"] for s in steps} else _R(True)
    result = minimize(original, runner)
    texts = [s["text"] for s in result.steps]
    assert "优惠码" in texts and "应用" in texts and "数量" in texts  # 关键保留
    assert "查看个人中心" not in texts and "切换图片" not in texts    # 无关删
    assert result.minimized_count == 3 and result.removed_count == 2


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
