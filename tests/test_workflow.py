"""Task 3.1 测试：LangGraph 编排（mock 4 agent，验证按序 + State 传递）。"""
from unittest.mock import patch

from graph.workflow import run_pipeline
from agents.evidence import BugTimeline
from agents.reproduction import ReproductionResult
from agents.code_investigator import TopFiles
from agents.regression import Issue


def test_run_pipeline_invokes_all_agents_in_order_and_threads_state():
    actions = [{"type": "fill", "target": "qty-input", "value": "2", "timestamp": 1.0}]
    timeline = BugTimeline(events=[], expected="160", actual="80")
    repro = ReproductionResult(success=True, spec_code="import {test}...", stable_rate="3/3")
    top = TopFiles(files=[])
    issue = Issue(title="t", expected="160", actual="80", body="body")
    order = []
    with patch("graph.workflow.build_timeline", side_effect=lambda *a, **k: (order.append("e"), timeline)[1]), \
         patch("graph.workflow.reproduce", side_effect=lambda *a, **k: (order.append("r"), repro)[1]), \
         patch("graph.workflow.investigate", side_effect=lambda *a, **k: (order.append("i"), top)[1]), \
         patch("graph.workflow.review", side_effect=lambda *a, **k: (order.append("g"), issue)[1]):
        state = run_pipeline(actions, [], repo_path="C:/repo", project_dir="C:/demo")
    assert order == ["e", "r", "i", "g"]          # 严格按序
    assert state["timeline"] is timeline
    assert state["repro_result"] is repro
    assert state["top_files"] is top
    assert state["issue"] is issue


def test_run_pipeline_passes_project_dir_to_reproduce():
    actions = [{"type": "click", "target": "apply-btn", "timestamp": 1.0}]
    timeline = BugTimeline(events=[], expected="160", actual="80")
    repro = ReproductionResult(success=False, reason="unstable")
    with patch("graph.workflow.build_timeline", return_value=timeline), \
         patch("graph.workflow.reproduce", return_value=repro) as pr, \
         patch("graph.workflow.investigate", return_value=TopFiles(files=[])), \
         patch("graph.workflow.review", return_value=Issue(body="x")):
        run_pipeline(actions, [], repo_path="C:/repo", project_dir="C:/demo")
    _, kwargs = pr.call_args
    assert kwargs.get("project_dir") == "C:/demo"
