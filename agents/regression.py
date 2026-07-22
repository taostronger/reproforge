"""agents/regression.py — Agent4 回归审查（plan Task 2.7）

审核生成的测试（断言对应 expected、选择器脆弱性）+ 生成 Markdown Bug Issue。
结构字段确定性组装，正文由 LLM 生成（失败降级 _fallback_body）。
"""
from dataclasses import dataclass, field

from llm.client import chat


@dataclass
class Issue:
    title: str = ""
    expected: str = ""
    actual: str = ""
    minimal_steps: list = field(default_factory=list)
    stable_rate: str = ""
    stability_class: str = ""       # deterministic / intermittent / unconfirmed
    reproduction_rate: float = 0.0  # Bug 复现率
    suspected_files: list = field(default_factory=list)
    body: str = ""           # Markdown 全文


_REVIEW_PROMPT = """你是测试工程师，正在审核一个自动生成的 Playwright 回归测试并撰写 Bug Issue。
生成的测试代码：
```
{spec}
```
Bug：预期 {expected}，实际 {actual}。
复现稳定性：{stability_class}（复现率 {reproduction_rate}）；连跑稳定率：{stable_rate}
可疑代码文件：{suspected}

请审核并生成 Markdown Issue：
1. 断言是否对应"预期值"
2. 选择器是否脆弱（避免 nth/css，优先 testid/role）
3. 输出含以下段落的 Markdown：标题、## 预期、## 实际、## 最小复现步骤、## 稳定率、## 可疑代码、## 截图

只输出 Markdown Issue 正文，不要额外解释。"""


def _steps_to_human(steps):
    """step dicts → 人类可读步骤列表。"""
    out = []
    for i, s in enumerate(steps, 1):
        v = f" 输入 {s.get('value')}" if s.get("value") else ""
        out.append(f"{i}. {s.get('type', '操作')} {s.get('target', '')}{v}".strip())
    return out


def _fallback_body(timeline, minimal_steps, stable_rate, suspected, stability_class="", reproduction_rate=0.0):
    """LLM 不可用时的确定性 Issue 正文。"""
    rate_txt = f"{reproduction_rate:.0%}" if reproduction_rate else "N/A"
    lines = [
        f"# Bug：预期 {timeline.expected}，实际 {timeline.actual}",
        "## 预期", timeline.expected or "(未提取)",
        "## 实际", timeline.actual or "(未提取)",
        "## 最小复现步骤",
        *(minimal_steps or ["(无)"]),
        "## 稳定率", stable_rate or "(未跑)",
        f"- 分类：{stability_class or '(未分类)'}（复现率 {rate_txt}）",
        "## 可疑代码",
        *(suspected or ["(无)"]),
    ]
    return "\n".join(lines)


def review(spec, timeline, top_files, repro_result=None):
    """审核测试 + 生成 Markdown Issue。结构字段确定性组装，正文 LLM 生成（失败降级）。"""
    suspected = [f.path for f in (top_files.files if top_files else [])]
    min_raw = []
    if repro_result and getattr(repro_result, "minimized", None):
        min_raw = getattr(repro_result.minimized, "steps", []) or []
    if not min_raw:
        min_raw = [
            {"type": e.action, "target": e.target, "value": e.value}
            for e in timeline.events
        ]
    minimal_steps = _steps_to_human(min_raw)
    stable_rate = getattr(repro_result, "stable_rate", "") if repro_result else ""
    stability_class = getattr(repro_result, "classification", "") if repro_result else ""
    reproduction_rate = getattr(repro_result, "reproduction_rate", 0.0) if repro_result else 0.0
    prompt = _REVIEW_PROMPT.format(
        spec=spec or "(无)", expected=timeline.expected or "(未提取)",
        actual=timeline.actual or "(未提取)", stable_rate=stable_rate or "(未跑)",
        stability_class=stability_class or "(未分类)",
        reproduction_rate=f"{reproduction_rate:.0%}" if reproduction_rate else "N/A",
        suspected=", ".join(suspected) or "(无)",
    )
    try:
        body = chat([{"role": "user", "content": prompt}])
    except Exception:
        body = _fallback_body(timeline, minimal_steps, stable_rate, suspected,
                              stability_class, reproduction_rate)
    return Issue(
        title=f"Bug：预期 {timeline.expected}，实际 {timeline.actual}",
        expected=timeline.expected,
        actual=timeline.actual,
        minimal_steps=minimal_steps,
        stable_rate=stable_rate,
        stability_class=stability_class,
        reproduction_rate=reproduction_rate,
        suspected_files=suspected,
        body=body,
    )
