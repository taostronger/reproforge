"""eval/metrics.py — 评测指标（plan Task 3.3）

从 pipeline State 提取复现率/最小化率/定位轮数等指标，跨 Bug 汇总输出 report。
"""
from dataclasses import asdict, dataclass

from asr.transcribe import Segment
from graph.workflow import run_pipeline


@dataclass
class Metrics:
    test_gen_success: bool = False       # 测试代码生成成功（spec_code 非空）
    reproduce_success_rate: float = 0.0  # 本 Bug 是否稳定复现（1.0/0.0）
    minimization_ratio: float = 0.0      # 最小化后/原始步数
    locator_fix_rounds: int = 0          # 定位器修复轮数
    p95_latency: float = 0.0             # 端到端延迟（秒，可选）
    token_cost: float = 0.0              # token 成本（可选）


def metrics_from_state(state, latency=0.0):
    """从 pipeline State 提取单 Bug 的指标。"""
    repro = state.get("repro_result") if state else None
    minimized = getattr(repro, "minimized", None) if repro else None
    orig = getattr(minimized, "original_count", 0) if minimized else 0
    mini = getattr(minimized, "minimized_count", 0) if minimized else 0
    return Metrics(
        test_gen_success=bool(repro and getattr(repro, "spec_code", "")),
        reproduce_success_rate=1.0 if (repro and getattr(repro, "success", False)) else 0.0,
        minimization_ratio=(mini / orig) if orig else 0.0,
        locator_fix_rounds=getattr(repro, "rounds", 0) if repro else 0,
        p95_latency=latency,
        token_cost=0.0,
    )


def run_eval(test_cases, run_pipeline_fn=None, repo_path=".", project_dir=None):
    """对多个 Bug 跑全流程，收集每 Bug 指标 + 汇总。test_cases: [(name, actions, narration), ...]。"""
    run_pipeline_fn = run_pipeline_fn or run_pipeline
    cases_out = []
    for name, actions, narration in test_cases:
        segments = [Segment(text=narration, start=0.0, end=10.0)] if narration else []
        state = run_pipeline_fn(actions, segments, console_log=[],
                                repo_path=repo_path, project_dir=project_dir)
        m = metrics_from_state(state)
        cases_out.append({"name": name, "metrics": asdict(m)})
    n = len(cases_out) or 1
    summary = {
        "reproduce_success_rate": sum(c["metrics"]["reproduce_success_rate"] for c in cases_out) / n,
        "test_gen_success_rate": sum(1 for c in cases_out if c["metrics"]["test_gen_success"]) / n,
        "avg_minimization_ratio": sum(c["metrics"]["minimization_ratio"] for c in cases_out) / n,
        "avg_locator_fix_rounds": sum(c["metrics"]["locator_fix_rounds"] for c in cases_out) / n,
    }
    return {"cases": cases_out, "summary": summary}
