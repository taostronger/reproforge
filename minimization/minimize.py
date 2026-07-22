"""minimization/minimize.py — 最小复现算法（plan Task 2.3，核心创新）

删冗余步骤重跑求稳定 1-minimal 复现路径（任一剩余步骤无法再单独删除，不保证全局最短）。纯确定性，不依赖 LLM。
"""
from dataclasses import dataclass

IRRELEVANT_KEYWORDS = {"个人中心", "帮助", "切换图片", "返回", "关闭", "详情"}
CRITICAL_KEYWORDS = {"优惠", "券", "数量", "提交", "加入购物车", "付款", "登录", "应用"}


def is_candidate_for_removal(action_type, text=""):
    """候选可删：click/hover 都候选（fill/select 等关键填写保留）。

    靠 minimize 重跑验证决定真删/保留，而非关键词硬判——避免「中文关键词 vs 英文 testid
    不匹配」导致只删 hover 的问题。关键 click（如 apply-btn）删了 Bug 不在 → 自动保留；
    冗余 click（多余 add/remove）删了 Bug 仍在 → 真删。
    """
    return action_type in ("click", "hover")


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
