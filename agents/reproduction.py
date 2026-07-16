"""agents/reproduction.py — Agent2 复现工程（plan Task 2.4）

生成 Playwright 测试 → 连跑判稳定 → 修定位器（最多 2 轮）→ 最小复现。
确定性部分（写文件/循环/最小化编排）+ LLM 部分（generate_test/fix_locator 调 chat）。
"""
import os
import re
import tempfile
from dataclasses import dataclass

from llm.client import chat
from test_runner.runner import run_test as _default_run_test, run_n_times as _default_run_n
from minimization.minimize import minimize


@dataclass
class ReproductionResult:
    success: bool = False
    spec_code: str = ""
    spec_path: str = ""
    minimized: object = None      # MinimizeResult
    stable_rate: str = ""         # 如 "3/3"
    rounds: int = 0               # 定位器修复轮数
    reason: str = ""              # "stable_repro" / "no_bug" / "unstable"


_GEN_PROMPT = """你是测试工程师。根据操作步骤生成一个 Playwright (TypeScript) 测试来复现 Bug。
被测页面：{base_url}
操作步骤（按顺序，元素用 data-testid 定位）：
{actions}
预期值：{expected}；实际值（Bug 表现）：{actual}
要求：
1. 用 test('...', async ({{ page }}) => {{ ... }}) 语法
2. 定位器优先 getByTestId，其次 getByRole / getByPlaceholder
3. 末尾断言关键元素（如 [data-testid=total-price]）的文本为【预期值】
4. 只输出测试代码（```ts ... ```），不要解释。"""

_FIX_PROMPT = """这个 Playwright 测试运行失败，原因是定位器问题。
失败信息：{error}
原测试代码：
```
{spec}
```
请仅修正定位器（按 testid→role→placeholder→label→text→css 降级），保持测试逻辑与断言不变。
只输出修正后的完整测试代码（```ts ... ```），不要解释。"""


def _write_spec(spec_code, workdir=None):
    """把 spec 代码写到临时文件，返回路径。"""
    d = workdir or tempfile.gettempdir()
    fd, path = tempfile.mkstemp(suffix=".spec.ts", dir=d, text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(spec_code)
    return path


def _events_to_steps(timeline):
    """timeline.events → minimize/generate 用的 step dicts。"""
    return [
        {"type": e.action, "target": e.target, "value": e.value, "text": e.target or e.value}
        for e in timeline.events
    ]


def _steps_to_actions_desc(steps):
    lines = []
    for s in steps:
        v = f" = {s.get('value')}" if s.get("value") else ""
        lines.append(f"- {s.get('type', 'action')}: {s.get('target') or s.get('text')}{v}")
    return "\n".join(lines)


def _extract_error(run_times_result):
    for r in run_times_result.results:
        if not r.passed and r.stdout:
            return r.stdout[:500]
    return ""


def _strip_fence(text):
    """剥离 markdown 代码围栏（```ts ... ```），保留纯代码（真跑前必需）。"""
    m = re.search(r"```(?:typescript|ts|js|javascript)?\s*\n?(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def generate_test(steps, expected, actual, base_url="http://localhost:5173"):
    prompt = _GEN_PROMPT.format(
        base_url=base_url,
        actions=_steps_to_actions_desc(steps),
        expected=expected,
        actual=actual,
    )
    return _strip_fence(chat([{"role": "user", "content": prompt}]))


def fix_locator(spec_code, error_msg):
    prompt = _FIX_PROMPT.format(spec=spec_code, error=error_msg or "locator not found")
    return chat([{"role": "user", "content": prompt}])


def reproduce(timeline, run_test_fn=None, run_n_fn=None, workdir=None):
    """主流程：生成测试 → 连跑判稳定 → 修定位器（≤2 轮）→ 最小复现。"""
    run_test_fn = run_test_fn or _default_run_test
    run_n_fn = run_n_fn or _default_run_n
    steps = _events_to_steps(timeline)
    spec_code = generate_test(steps, timeline.expected, timeline.actual)
    spec_path = _write_spec(spec_code, workdir)

    rounds = 0
    last = None
    stable = False
    for _ in range(3):                       # 1 次初始 + 最多 2 轮修定位器
        last = run_n_fn(spec_path, 3)
        if last.stable_fail:
            stable = True
            break
        if last.pass_count == len(last.results):
            return ReproductionResult(success=False, spec_code=spec_code, spec_path=spec_path,
                                      rounds=rounds, reason="no_bug")
        if rounds >= 2:
            break
        spec_code = fix_locator(spec_code, _extract_error(last))
        spec_path = _write_spec(spec_code, workdir)
        rounds += 1

    if not stable:
        return ReproductionResult(success=False, spec_code=spec_code, spec_path=spec_path,
                                  rounds=rounds, reason="unstable")

    # 最小复现：删候选步骤后用子集重新生成 spec 再跑
    def min_runner(subset):
        sub_code = generate_test(subset, timeline.expected, timeline.actual)
        return run_test_fn(_write_spec(sub_code, workdir))

    minimized = minimize(steps, min_runner)
    return ReproductionResult(
        success=True,
        spec_code=spec_code,
        spec_path=spec_path,
        minimized=minimized,
        stable_rate=f"{last.fail_count}/{len(last.results)}",
        rounds=rounds,
        reason="stable_repro",
    )
