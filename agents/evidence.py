"""agents/evidence.py — Agent1 证据分析 → Bug 时间线（plan Task 2.1）

输入：操作 actions + 语音 segments + console 日志。
输出：BugTimeline（事件序列 + expected/actual）。
- 语音 segment 按时间戳关联到最近 action（user_narration）
- chat_json 让 LLM 从口述提取 expected/actual，置信度低 → needs_confirm
- 启发式标注 suspected_anomaly（narration 含异常指示词）
"""
from pydantic import BaseModel, Field

from llm.client import chat_json


class TimelineEvent(BaseModel):
    event_id: int
    time: float = 0.0
    action: str = ""
    target: str = ""
    value: str = ""
    user_narration: str = ""
    page_before: str = ""
    page_after: str = ""
    console_errors: list = Field(default_factory=list)
    suspected_anomaly: bool = False


class BugTimeline(BaseModel):
    events: list = Field(default_factory=list)
    expected: str = ""
    actual: str = ""
    needs_confirm: bool = False


_ANOMALY_WORDS = ("还是", "不对", "没变", "应该", "错误", "不对劲", "为什么", "没反应")
_CONFIDENCE_THRESHOLD = 0.6
_PROMPT = (
    "你是测试工程师。从测试人员口述中提取这个 Bug 的【预期值】和【实际值】。\n"
    "口述：{narration}\n"
    '只输出 JSON：{{"expected": "预期值(数字或简述)", "actual": "实际值", "confidence": 0.0到1.0}}。\n'
    "若口述未明确给出预期或实际，confidence 给低分。"
)


def _nearest_segment(time, segments):
    """按时间戳找最近的语音 segment。"""
    best, best_dt = None, None
    for s in segments:
        mid = (getattr(s, "start", 0) + getattr(s, "end", 0)) / 2
        dt = abs(mid - time)
        if best_dt is None or dt < best_dt:
            best, best_dt = s, dt
    return best


def _looks_anomalous(narration):
    """启发式：narration 含异常指示词 → 可疑。"""
    return bool(narration) and any(w in narration for w in _ANOMALY_WORDS)


def build_timeline(actions, segments, console_log=None, visual_finding=None):
    """构建 Bug 时间线：关联 narration + LLM 提取 expected/actual + 标可疑异常。"""
    console_log = console_log or []
    events = []
    for i, a in enumerate(actions):
        t = float(a.get("timestamp", 0.0))
        seg = _nearest_segment(t, segments)
        narration = getattr(seg, "text", "") if seg else ""
        events.append(TimelineEvent(
            event_id=i,
            time=t,
            action=str(a.get("type", "")),
            target=str(a.get("target", "") or a.get("target_selector", "")),
            value=str(a.get("value", "") or ""),
            user_narration=narration,
            console_errors=list(console_log) if _looks_anomalous(narration) else [],
            suspected_anomaly=_looks_anomalous(narration),
        ))
    full = " ".join(getattr(s, "text", "") for s in segments).strip()
    try:
        result = chat_json([{"role": "user", "content": _PROMPT.format(narration=full)}]) or {}
    except Exception:
        result = {}
    expected = str(result.get("expected", "")).strip()
    actual = str(result.get("actual", "")).strip()
    try:
        conf = float(result.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    # 合并 VL 视觉提取（置信度优先；口述与视觉冲突 → 转人工确认）
    vision_conflict = False
    if visual_finding is not None and getattr(visual_finding, "used", False):
        if visual_finding.confidence >= conf:
            if visual_finding.expected:
                expected = visual_finding.expected
            if visual_finding.actual:
                actual = visual_finding.actual
            conf = visual_finding.confidence
        elif ((visual_finding.expected and expected and visual_finding.expected != expected) or
              (visual_finding.actual and actual and visual_finding.actual != actual)):
            vision_conflict = True
    needs_confirm = vision_conflict or conf < _CONFIDENCE_THRESHOLD or (not expected and not actual)
    return BugTimeline(events=events, expected=expected, actual=actual, needs_confirm=needs_confirm)
