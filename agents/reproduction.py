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
    classification: str = ""      # deterministic / intermittent / unconfirmed（review 二.3）
    reproduction_rate: float = 0.0  # Bug 复现率 = fail_count / n


_GEN_PROMPT = """你是测试工程师。根据操作步骤生成一个 Playwright (TypeScript) 测试来复现 Bug。
被测页面：{base_url}
操作步骤（按顺序，元素用 data-testid 定位）：
{actions}
预期值：{expected}；实际值（Bug 表现）：{actual}
要求：
1. 开头必须 import {{ test, expect }} from '@playwright/test';
2. 用 test('...', async ({{ page }}) => {{ ... }}) 语法
3. 定位器优先 getByTestId，其次 getByRole / getByPlaceholder
4. 末尾断言关键元素（如 [data-testid=total-price]）的文本为【预期值】
5. 只输出测试代码（```ts ... ```），不要解释。"""

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


def _dedup_steps(steps):
    """合并连续同 target 步骤：同 target 的 fill 覆盖留最后值，冗余 click 跳过。

    录制时常有 qty fill 2→1→2 + 每次 click 的冗余；合并后 spec 更短，Playwright 真跑
    和 minimize 都更快。不同 target（apply-btn / add-* / remove-btn）的 click 保留。
    """
    out = []
    for s in steps:
        t = s.get("target")
        if t and out and out[-1].get("target") == t:
            if s.get("type") == "fill":
                out[-1] = s        # 同 target fill：覆盖，留最后值
            continue                # 同 target click：跳过（冗余）
        out.append(s)
    return out


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


def _ensure_import(spec):
    """保证 spec 含 Playwright import（LLM 偶尔漏，真跑会 ReferenceError）。"""
    if "@playwright/test" not in spec:
        return "import { test, expect } from '@playwright/test';\n\n" + spec
    return spec


def generate_test(steps, expected, actual, base_url="http://localhost:5173"):
    prompt = _GEN_PROMPT.format(
        base_url=base_url,
        actions=_steps_to_actions_desc(steps),
        expected=expected,
        actual=actual,
    )
    return _ensure_import(_strip_fence(chat([{"role": "user", "content": prompt}])))


def _extract_assert(spec_code):
    """从 spec 提取断言行（expect...），供 minimize 确定性复用，不重新调 LLM。"""
    import re
    m = re.search(r'(await expect\([^;]+\);)', spec_code)
    return m.group(1) if m else "await expect(page.getByTestId('total-price')).toHaveText('0');"


def _det_spec(steps, assert_line, base_url="http://localhost:5173"):
    """确定性生成 spec（goto + actions + 断言），不调 LLM —— minimize 提速用。"""
    lines = [
        "import { test, expect } from '@playwright/test';",
        f"test('repro', async ({{ page }}) => {{",
        f"  await page.goto('{base_url}');",
    ]
    for s in steps:
        t = s.get("target") or ""
        if s.get("type") == "fill":
            lines.append(f"  await page.getByTestId('{t}').fill('{s.get('value', '')}');")
        elif s.get("type") == "click":
            lines.append(f"  await page.getByTestId('{t}').click();")
    lines.append(f"  {assert_line}")
    lines.append("});")
    return "\n".join(lines)


def fix_locator(spec_code, error_msg):
    prompt = _FIX_PROMPT.format(spec=spec_code, error=error_msg or "locator not found")
    return chat([{"role": "user", "content": prompt}])


def reproduce(timeline, run_test_fn=None, run_n_fn=None, workdir=None, project_dir=None):
    """主流程：生成测试 → 连跑判稳定 → 修定位器（≤2 轮）→ 最小复现。
    结束自动清理生成的 spec 临时文件（避免污染被测项目 / code_search）。"""
    run_test_fn = run_test_fn or _default_run_test
    run_n_fn = run_n_fn or _default_run_n
    # spec 写进被测项目目录（playwright 要求 testDir 内 + cwd），否则 No tests found
    spec_dir = project_dir or workdir or tempfile.gettempdir()
    cwd = project_dir
    written = []

    def _write(code):
        p = _write_spec(code, spec_dir)
        written.append(p)
        return p

    steps = _dedup_steps(_events_to_steps(timeline))
    spec_code = generate_test(steps, timeline.expected, timeline.actual)
    spec_path = _write(spec_code)
    # 连跑次数：默认 3（冒烟速度）；严谨评测建议 REPROFORGE_RUNS=10（review 二.3）
    n = int(os.getenv("REPROFORGE_RUNS", "3"))
    try:
        rounds = 0
        last = None
        stable = False
        for _ in range(3):                       # 1 次初始 + 最多 2 轮修定位器
            last = run_n_fn(spec_path, n, cwd=cwd)
            if last.stable_fail:
                stable = True
                break
            if last.pass_count == len(last.results):
                return ReproductionResult(success=False, spec_code=spec_code, spec_path=spec_path,
                                          rounds=rounds, reason="no_bug",
                                          classification="unconfirmed", reproduction_rate=0.0)
            if rounds >= 2:
                break
            spec_code = fix_locator(spec_code, _extract_error(last))
            spec_path = _write(spec_code)
            rounds += 1

        if not stable:
            return ReproductionResult(success=False, spec_code=spec_code, spec_path=spec_path,
                                      rounds=rounds, reason="unstable",
                                      classification=last.classification,
                                      reproduction_rate=last.reproduction_rate)

        # 最小复现：删候选步骤后用确定性 spec（复用首次断言，不重新调 LLM）真跑 —— 提速
        assert_line = _extract_assert(spec_code)
        def min_runner(subset):
            sub_code = _det_spec(subset, assert_line)
            return run_test_fn(_write(sub_code), cwd=cwd)

        minimized = minimize(steps, min_runner, max_attempts=5)
        return ReproductionResult(
            success=True,
            spec_code=spec_code,
            spec_path=spec_path,
            minimized=minimized,
            stable_rate=f"{last.fail_count}/{len(last.results)}",
            rounds=rounds,
            reason="stable_repro",
            classification="deterministic",
            reproduction_rate=last.reproduction_rate,
        )
    finally:
        for p in written:
            try:
                os.unlink(p)
            except OSError:
                pass
