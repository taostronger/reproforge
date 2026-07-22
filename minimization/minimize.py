"""minimization/minimize.py — 最小复现算法（plan Task 2.3，核心创新）

删冗余步骤重跑求稳定 1-minimal 复现路径（任一剩余步骤无法再单独删除，不保证全局最短）。纯确定性，不依赖 LLM。
"""
from dataclasses import dataclass

IRRELEVANT_KEYWORDS = {"个人中心", "帮助", "切换图片", "返回", "关闭", "详情"}
CRITICAL_KEYWORDS = {"优惠", "券", "数量", "提交", "加入购物车", "付款", "登录", "应用"}


def is_candidate_for_removal(action_type, text=""):
    """判断该步骤是否候选可删（只删点击/悬停类无关步骤，保留关键填写）。"""
    if action_type not in ("click", "hover"):
        return False
    t = text or ""
    if any(k in t for k in CRITICAL_KEYWORDS):
        return False
    return any(k in t for k in IRRELEVANT_KEYWORDS) or action_type == "hover"


@dataclass
class MinimizeResult:
    steps: list
    original_count: int
    minimized_count: int
    removed_count: int
    attempts: int


def minimize(steps, runner, max_attempts=10):
    """删候选步骤重跑：Bug 仍在(passed=False)则永久删除，否则保留。最多 max_attempts 轮。"""
    current = list(steps)
    removed = 0
    for _ in range(max_attempts):
        progressed = False
        for i, s in enumerate(current):
            if not is_candidate_for_removal(s.get("type"), s.get("text", "")):
                continue
            trial = current[:i] + current[i + 1:]
            if runner(trial).passed is False:  # Bug 仍在 → 可删
                current = trial
                removed += 1
                progressed = True
                break  # 索引变了，重头扫
        if not progressed:
            break
    return MinimizeResult(current, len(steps), len(current), removed, max_attempts)
