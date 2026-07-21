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


def test_run_pipeline_vision_node_runs_before_evidence_and_threads_screenshot():
    """VL：vision 节点最先跑（evidence 前），screenshot 透传给 analyze_screenshot。"""
    from agents.vision import VisualFinding
    actions = [{"type": "click", "target": "x", "timestamp": 1.0}]
    timeline = BugTimeline(events=[], expected="160", actual="80")
    repro = ReproductionResult(success=True, spec_code="x", stable_rate="3/3")
    top = TopFiles(files=[])
    issue = Issue(title="t", expected="160", actual="80", body="b")
    order = []
    captured = {}

    def fake_vision(screenshot, narration):
        order.append("v")
        captured["screenshot"] = screenshot
        return VisualFinding(used=True, expected="160", actual="80", confidence=0.9)

    with patch("graph.workflow.analyze_screenshot", side_effect=fake_vision), \
         patch("graph.workflow.build_timeline", side_effect=lambda *a, **k: (order.append("e"), timeline)[1]), \
         patch("graph.workflow.reproduce", side_effect=lambda *a, **k: (order.append("r"), repro)[1]), \
         patch("graph.workflow.investigate", side_effect=lambda *a, **k: (order.append("i"), top)[1]), \
         patch("graph.workflow.review", side_effect=lambda *a, **k: (order.append("g"), issue)[1]):
        state = run_pipeline(actions, [], repo_path="C:/repo", project_dir="C:/demo",
                             screenshot="/bug.png")
    assert order == ["v", "e", "r", "i", "g"]          # vision 最先
    assert captured["screenshot"] == "/bug.png"          # screenshot 透传
    assert state["visual_finding"].used is True


def test_run_pipeline_vision_off_env_disables_vision(monkeypatch):
    """REPROFORGE_VL=off → vision 节点不调 analyze_screenshot，返回空（降级）。"""
    actions = [{"type": "click", "target": "x", "timestamp": 1.0}]
    timeline = BugTimeline(events=[], expected="160", actual="80")
    monkeypatch.setenv("REPROFORGE_VL", "off")
    with patch("graph.workflow.analyze_screenshot") as av, \
         patch("graph.workflow.build_timeline", return_value=timeline), \
         patch("graph.workflow.reproduce", return_value=ReproductionResult(success=False)), \
         patch("graph.workflow.investigate", return_value=TopFiles(files=[])), \
         patch("graph.workflow.review", return_value=Issue(body="x")):
        state = run_pipeline(actions, [], repo_path="C:/r", project_dir="C:/d", screenshot="/x.png")
    av.assert_not_called()                               # off → 不调 API
    assert state["visual_finding"].used is False
