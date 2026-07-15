"""Task 2.1 测试：Agent1 证据分析（mock chat_json，不真调 LLM）。"""
from unittest.mock import patch

from asr.transcribe import Segment
from agents.evidence import build_timeline, BugTimeline


def test_extracts_expected_actual_and_associates_narration():
    actions = [
        {"type": "fill", "target": "coupon-input", "value": "SALE20", "timestamp": 1.0, "text": "优惠码"},
        {"type": "fill", "target": "qty-input", "value": "2", "timestamp": 3.0, "text": "数量"},
    ]
    segments = [Segment(text="我用了八折券，数量改成2，总价还是80，应该是160", start=0.5, end=5.0)]
    with patch("agents.evidence.chat_json") as m:
        m.return_value = {"expected": "160", "actual": "80", "confidence": 0.9}
        tl = build_timeline(actions, segments, [])
    assert isinstance(tl, BugTimeline)
    assert tl.expected == "160" and tl.actual == "80"
    assert tl.needs_confirm is False
    assert any(e.user_narration for e in tl.events)


def test_low_confidence_sets_needs_confirm():
    actions = [{"type": "fill", "target": "qty-input", "value": "2", "timestamp": 1.0, "text": "数量"}]
    segments = [Segment(text="这个好像不太对", start=0.5, end=2.0)]
    with patch("agents.evidence.chat_json") as m:
        m.return_value = {"expected": "", "actual": "", "confidence": 0.2}
        tl = build_timeline(actions, segments, [])
    assert tl.needs_confirm is True


def test_flags_suspected_anomaly():
    actions = [{"type": "fill", "target": "qty-input", "value": "2", "timestamp": 1.0, "text": "数量"}]
    segments = [Segment(text="数量改成2，总价还是80", start=0.5, end=2.0)]
    with patch("agents.evidence.chat_json") as m:
        m.return_value = {"expected": "160", "actual": "80", "confidence": 0.9}
        tl = build_timeline(actions, segments, [])
    assert any(e.suspected_anomaly for e in tl.events)


def test_chat_json_failure_is_safe():
    actions = [{"type": "click", "target": "apply-btn", "timestamp": 1.0, "text": "应用"}]
    segments = [Segment(text="点应用", start=0.5, end=1.5)]
    with patch("agents.evidence.chat_json", side_effect=ValueError("no json")):
        tl = build_timeline(actions, segments, [])
    assert isinstance(tl, BugTimeline)
    assert tl.needs_confirm is True  # 无法提取 → 需人工确认
