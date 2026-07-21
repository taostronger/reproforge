"""graph/workflow.py — LangGraph 编排

StateGraph 串联 vision → evidence → reproduction → recall → investigator → regression。
- vision（VL，可选）：看截图提 expected/actual，无图/REPROFORGE_VL=off/调用失败 → 返回空（降级）
- recall（RAG，可选）：检索历史相似 Bug 给 investigator 参考；空库/REPROFORGE_MEMORY=off/失败 → 降级
编排层接受已解析的 actions/segments（解耦采集层 trace_parser，后者未实现）。
"""
import os
from typing import Any, Optional, TypedDict

from langgraph.graph import START, END, StateGraph

from agents.vision import analyze_screenshot, VisualFinding
from agents.evidence import build_timeline
from agents.reproduction import reproduce
from agents.recall import recall
from agents.code_investigator import investigate
from agents.regression import review
from memory.store import get_memory_store


class State(TypedDict, total=False):
    actions: list
    segments: list
    console_log: list
    repo_path: str
    project_dir: Optional[str]
    screenshot: Optional[str]        # VL：Bug 截图路径/URL（UI 上传，可空）
    visual_finding: Any              # vision 输出（VisualFinding）
    timeline: Any
    repro_result: Any
    top_files: Any
    issue: Any
    historical_ref: Any               # RAG：recall 输出（HistoricalRef）


def vision_node(state):
    """VL 视觉：看截图提 expected/actual。REPROFORGE_VL=off 或无图 → 返回空（降级，evidence 照旧）。"""
    if os.getenv("REPROFORGE_VL", "on").lower() == "off":
        return {"visual_finding": VisualFinding()}
    narration = " ".join(getattr(s, "text", "") for s in state.get("segments", []))
    vf = analyze_screenshot(state.get("screenshot"), narration)
    return {"visual_finding": vf}


def evidence_node(state):
    tl = build_timeline(state["actions"], state["segments"], state["console_log"],
                        visual_finding=state.get("visual_finding"))
    return {"timeline": tl}


def reproduction_node(state):
    repro = reproduce(state["timeline"], project_dir=state.get("project_dir"))
    return {"repro_result": repro}


def recall_node(state):
    """RAG：检索历史相似 Bug。无库/失败 → 空 HistoricalRef（investigator 照旧）。"""
    store = get_memory_store()
    ref = recall(state["timeline"], state["actions"], store=store)
    return {"historical_ref": ref}


def investigator_node(state):
    top = investigate(state["timeline"], state["console_log"], state["repo_path"],
                      historical_ref=state.get("historical_ref"))
    return {"top_files": top}


def regression_node(state):
    repro = state.get("repro_result")
    spec = repro.spec_code if repro else ""
    issue = review(spec, state["timeline"], state["top_files"], repro)
    return {"issue": issue}


def build_graph():
    g = StateGraph(State)
    g.add_node("vision", vision_node)
    g.add_node("evidence", evidence_node)
    g.add_node("reproduction", reproduction_node)
    g.add_node("recall", recall_node)
    g.add_node("investigator", investigator_node)
    g.add_node("regression", regression_node)
    g.add_edge(START, "vision")
    g.add_edge("vision", "evidence")
    g.add_edge("evidence", "reproduction")
    g.add_edge("reproduction", "recall")
    g.add_edge("recall", "investigator")
    g.add_edge("investigator", "regression")
    g.add_edge("regression", END)
    return g.compile()


def run_pipeline(actions, segments, console_log=None, repo_path=".", project_dir=None, screenshot=None):
    """端到端编排：截图(可选) + actions + segments → vision → 时间线 → 复现 → 检索历史 → 代码调查 → 回归 Issue。

    结束后把 Issue ingest 进记忆库（失败不影响输出）。
    """
    graph = build_graph()
    initial = {
        "actions": actions,
        "segments": segments,
        "console_log": console_log or [],
        "repo_path": repo_path,
        "project_dir": project_dir,
        "screenshot": screenshot,
    }
    state = graph.invoke(initial)
    _ingest_to_memory(state)
    return state


def _ingest_to_memory(state):
    """Issue 入记忆库；REPROFORGE_MEMORY=off / 无 issue / 失败 → 静默跳过。"""
    if os.getenv("REPROFORGE_MEMORY", "on").lower() == "off":
        return
    issue = state.get("issue")
    timeline = state.get("timeline")
    top_files = state.get("top_files")
    if issue is None or timeline is None:
        return
    try:
        store = get_memory_store()
        if store is not None:
            store.ingest_issue(issue, timeline, top_files)
    except Exception:
        pass
