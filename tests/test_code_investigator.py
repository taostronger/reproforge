"""Task 2.6 测试：Agent3 代码调查（真实 demo_project search + mock chat_json）。"""
from pathlib import Path
from unittest.mock import patch

from agents.code_investigator import investigate, TopFiles, _extract_query_terms
from agents.evidence import BugTimeline, TimelineEvent

DEMO = Path(__file__).resolve().parent.parent / "demo_project"


def _bug1_timeline():
    return BugTimeline(
        events=[
            TimelineEvent(event_id=0, action="fill", target="coupon-input", value="SALE20"),
            TimelineEvent(event_id=1, action="click", target="apply-btn"),
            TimelineEvent(event_id=2, action="fill", target="qty-input", value="2"),
        ],
        expected="160", actual="80",
    )


def test_extract_query_terms_from_timeline():
    tl = _bug1_timeline()
    terms = _extract_query_terms(tl, ["Cannot read property of undefined"])
    assert "coupon-input" in terms
    assert "apply-btn" in terms
    assert "qty-input" in terms
    assert "Cannot read property of undefined" in terms


def test_investigate_ranks_app_tsx_top():
    tl = _bug1_timeline()
    with patch("agents.code_investigator.chat_json") as m:
        m.return_value = {"scores": [{"score": 0.95, "reason": "总价计算逻辑在此"}]}
        top = investigate(tl, [], DEMO)
    assert isinstance(top, TopFiles)
    assert top.files, "应返回候选文件"
    paths = [f.path.replace("\\", "/") for f in top.files]
    assert any("App.tsx" in p for p in paths), paths
    assert "App.tsx" in top.files[0].path.replace("\\", "/")
    assert top.files[0].reason


def test_investigate_fallback_when_llm_fails():
    tl = _bug1_timeline()
    with patch("agents.code_investigator.chat_json", side_effect=ValueError("no json")):
        top = investigate(tl, [], DEMO)
    assert top.files
    paths = [f.path.replace("\\", "/") for f in top.files]
    assert any("App.tsx" in p for p in paths)  # 降级用 search 命中数排序
