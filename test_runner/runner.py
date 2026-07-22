"""test_runner/runner.py — Playwright 测试运行器（plan Task 2.2）

运行生成的 Playwright spec，判通过/失败；连跑 N 次判"稳定复现"。
通过 subprocess 调 `npx playwright test --reporter=json`，解析 JSON 报告；
解析失败时用 exit code 兜底。纯确定性，不依赖 LLM。
"""
import json
import os
import subprocess
import time
from dataclasses import dataclass, field


@dataclass
class RunResult:
    passed: bool
    stdout: str = ""
    screenshots: list = field(default_factory=list)
    duration: float = 0.0


@dataclass
class RunTimesResult:
    """连跑 N 次的汇总。测试失败 = Bug 复现（断言 expected，buggy 版本失败）。

    每次独立 subprocess 跑 `npx playwright test`：playwright 每个 test 默认新建
    BrowserContext（浏览器侧隔离）；前端 demo 每次 page.goto 重载 → 状态天然重置。
    """
    pass_count: int = 0
    fail_count: int = 0
    results: list = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.results)

    @property
    def reproduction_rate(self) -> float:
        """Bug 复现率 = fail_count / n（测试失败 = Bug 复现）。"""
        return self.fail_count / self.n if self.n else 0.0

    @property
    def stable_fail(self) -> bool:
        """全部失败 = 稳定复现 Bug（向后兼容）。"""
        return self.n > 0 and self.fail_count == self.n

    @property
    def classification(self) -> str:
        """复现稳定性分类：deterministic(全复现) / intermittent(部分) / unconfirmed(未复现)。"""
        if self.n == 0 or self.fail_count == 0:
            return "unconfirmed"
        return "deterministic" if self.fail_count == self.n else "intermittent"


def _build_cmd(spec_path):
    """构造 `npx playwright test --reporter=json` 命令。
    Windows 下 npx 是 .cmd 脚本，需经 cmd /c 调用。"""
    prefix = ["cmd", "/c"] if os.name == "nt" else []
    return prefix + ["npx", "playwright", "test", spec_path, "--reporter=json"]


def _parse_report(stdout):
    """解析 playwright JSON 报告 → (passed, screenshots)。
    返回 (None, []) 表示无法解析，交由调用方用 exit code 兜底。"""
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError):
        return None, []
    if not isinstance(data, dict) or "stats" not in data:
        return None, []
    stats = data["stats"]
    failures = stats.get("failures", 0) + stats.get("unexpected", 0)
    # screenshots: 真实报告嵌在 suites→specs→tests→results[].error.screenshot，
    # 此处先留空，端到端阶段再增强（不阻塞接口）。
    return (failures == 0), []


def run_test(spec_path, timeout: int = 60, cwd=None) -> RunResult:
    start = time.monotonic()
    # playwright 把参数当正则匹配文件路径：给 cwd 时转相对 posix 路径，
    # 避免绝对路径反斜杠被当转义 → "No tests found"
    if cwd:
        spec_arg = os.path.relpath(spec_path, cwd).replace(os.sep, "/")
    else:
        spec_arg = spec_path
    proc = subprocess.run(
        _build_cmd(spec_arg), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, cwd=cwd,
    )
    duration = time.monotonic() - start
    parsed, screenshots = _parse_report(proc.stdout)
    passed = (proc.returncode == 0) if parsed is None else parsed
    return RunResult(
        passed=passed, stdout=proc.stdout or "", screenshots=screenshots, duration=duration
    )


def run_n_times(spec_path, n: int = 3, cwd=None) -> RunTimesResult:
    results = [run_test(spec_path, cwd=cwd) for _ in range(n)]
    pass_count = sum(1 for r in results if r.passed)
    fail_count = len(results) - pass_count
    return RunTimesResult(pass_count=pass_count, fail_count=fail_count, results=results)
