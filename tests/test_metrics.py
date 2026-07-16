"""Task 3.3 测试：评测指标（mock run_pipeline / state，不真调）。"""
from unittest.mock import patch, MagicMock

from eval.metrics import Metrics, metrics_from_state, run_eval
from agents.reproduction import ReproductionResult
from agents.evidence import BugTimeline

_ACTIONS = [{"type": "fill", "target": "qty-input", "value": "2", "timestamp": 1.0}]


def _state(success=True, rounds=0, orig=4, mini=2):
    minimized = MagicMock(original_count=orig, minimized_count=mini, removed_count=orig - mini)
    repro = ReproductionResult(
        success=success, spec_code="import {test}", stable_rate="3/3",
        rounds=rounds, reason="stable_repro", minimized=minimized)
    return {"repro_result": repro, "timeline": BugTimeline(events=[], expected="160", actual="80")}


def test_metrics_from_state_success():
    m = metrics_from_state(_state(success=True, rounds=1, orig=4, mini=2), latency=12.5)
    assert isinstance(m, Metrics)
    assert m.test_gen_success is True
    assert m.reproduce_success_rate == 1.0
    assert m.minimization_ratio == 0.5          # 2/4
    assert m.locator_fix_rounds == 1
    assert m.p95_latency == 12.5


def test_metrics_from_state_failed_repro():
    m = metrics_from_state(_state(success=False), latency=5.0)
    assert m.reproduce_success_rate == 0.0
    assert m.test_gen_success is True           # spec_code 仍非空


def test_run_eval_collects_cases_and_summary():
    cases = [("bug1", _ACTIONS, "口述1"), ("bug2", _ACTIONS, "口述2")]
    with patch("eval.metrics.run_pipeline", side_effect=[_state(), _state(success=False)]):
        report = run_eval(cases, repo_path="C:/repo", project_dir="C:/demo")
    assert len(report["cases"]) == 2
    assert report["cases"][0]["name"] == "bug1"
    assert "summary" in report
    assert report["summary"]["reproduce_success_rate"] == 0.5     # (1.0+0.0)/2
    assert report["summary"]["test_gen_success_rate"] == 1.0
