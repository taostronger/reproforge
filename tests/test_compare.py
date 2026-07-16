"""Task 4.3 测试：远程 vs 本地指标对比（mock run_pipeline，不依赖 spark-71）。"""
from unittest.mock import patch

from eval.compare import compare
from agents.evidence import BugTimeline
from agents.reproduction import ReproductionResult
from agents.code_investigator import TopFiles
from agents.regression import Issue
from minimization.minimize import MinimizeResult


def _fake_state():
    return {
        "timeline": BugTimeline(events=[], expected="160", actual="80"),
        "repro_result": ReproductionResult(
            success=True, spec_code="x", stable_rate="3/3", rounds=0,
            reason="stable_repro", minimized=MinimizeResult([], 4, 2, 2, 1)),
        "top_files": TopFiles(files=[]),
        "issue": Issue(body="x"),
    }


def test_compare_runs_both_profiles(tmp_path):
    actions = [{"type": "fill", "target": "qty-input", "value": "2", "timestamp": 1.0}]
    with patch("eval.compare.run_pipeline", return_value=_fake_state()):
        report = compare([("bug1", actions, "口述")],
                         repo_path=str(tmp_path), project_dir=str(tmp_path))
    assert len(report) == 2
    assert {r["profile"] for r in report} == {"local", "remote"}
    assert all("metrics" in r for r in report)


def test_compare_resets_llm_client_between_profiles(tmp_path):
    # 切 profile 必须重置 llm.client._client，否则缓存旧 base_url
    import llm.client
    actions = [{"type": "click", "target": "apply-btn", "timestamp": 1.0}]
    with patch("eval.compare.run_pipeline", return_value=_fake_state()):
        compare([("b", actions, "n")], repo_path=str(tmp_path), project_dir=str(tmp_path))
    # 跑完后 _client 应被重置（None）
    assert llm.client._client is None
