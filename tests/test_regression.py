"""Task 2.7 测试：Agent4 回归审查（mock chat，不真调 LLM）。"""
from unittest.mock import patch, MagicMock

from agents.regression import review, Issue
from agents.evidence import BugTimeline, TimelineEvent
from agents.code_investigator import TopFiles, FileScore
from agents.reproduction import ReproductionResult


def _timeline():
    return BugTimeline(
        events=[TimelineEvent(event_id=0, action="fill", target="qty-input",
                              value="2", user_narration="数量改2")],
        expected="160", actual="80",
    )


def test_review_produces_issue_with_required_sections():
    tl = _timeline()
    top = TopFiles(files=[FileScore(path="App.tsx", score=0.9, reason="总价逻辑")])
    repro = ReproductionResult(
        success=True, stable_rate="3/3",
        minimized=MagicMock(steps=[{"type": "fill", "target": "qty-input", "value": "2"}]),
    )
    with patch("agents.regression.chat") as m:
        m.return_value = "# Bug: 总价不随数量更新\n## 预期\n¥160\n## 实际\n¥80"
        issue = review("test spec code", tl, top, repro)
    assert isinstance(issue, Issue)
    assert issue.expected == "160"
    assert issue.actual == "80"
    assert issue.minimal_steps and len(issue.minimal_steps) >= 1
    assert issue.stable_rate == "3/3"
    assert issue.suspected_files and "App.tsx" in issue.suspected_files[0]
    assert "160" in issue.body and "80" in issue.body


def test_review_minimal_steps_human_readable():
    tl = _timeline()
    top = TopFiles(files=[])
    repro = ReproductionResult(
        success=True, stable_rate="3/3",
        minimized=MagicMock(steps=[
            {"type": "fill", "target": "coupon-input", "value": "SALE20"},
            {"type": "click", "target": "apply-btn"},
        ]),
    )
    with patch("agents.regression.chat", return_value="body"):
        issue = review("spec", tl, top, repro)
    joined = " ".join(issue.minimal_steps)
    assert "coupon-input" in joined or "apply-btn" in joined


def test_review_fallback_when_llm_fails():
    tl = _timeline()
    top = TopFiles(files=[FileScore(path="App.tsx", score=0.9, reason="")])
    repro = ReproductionResult(
        success=True, stable_rate="3/3",
        minimized=MagicMock(steps=[{"type": "fill", "target": "qty-input"}]),
    )
    with patch("agents.regression.chat", side_effect=RuntimeError("api down")):
        issue = review("spec", tl, top, repro)
    assert isinstance(issue, Issue)
    assert "160" in issue.body and "80" in issue.body  # 降级 body 仍含 expected/actual


def test_review_extracts_stability_class_and_rate():
    """review 从 repro_result 提取 classification + reproduction_rate 填入 Issue（review 二.3）。"""
    tl = _timeline()
    top = TopFiles(files=[])
    repro = ReproductionResult(
        success=True, stable_rate="10/10",
        classification="deterministic", reproduction_rate=1.0,
        minimized=MagicMock(steps=[{"type": "fill", "target": "qty-input"}]),
    )
    with patch("agents.regression.chat", return_value="body"):
        issue = review("spec", tl, top, repro)
    assert issue.stability_class == "deterministic"
    assert issue.reproduction_rate == 1.0
