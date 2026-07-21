"""graph/workflow.py — LangGraph 编排

StateGraph 串联 vision → evidence → reproduction → investigator → regression。
- vision（VL，可选）：看截图提 expected/actual，无图/REPROFORGE_VL=off/调用失败 → 返回空（降级）
编排层接受已解析的 actions/segments（解耦采集层 trace_parser，后者未实现）。
"""
import os
from typing import Any, Optional, TypedDict

from langgraph.graph import START, END, StateGraph

from agents.vision import analyze_screenshot, VisualFinding
from agents.evidence import build_timeline
from agents.reproduction import reproduce
from agents.code_investigator import investigate
from agents.regression import review


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


def investigator_node(state):
    top = investigate(state["timeline"], state["console_log"], state["repo_path"])
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
    g.add_node("investigator", investigator_node)
    g.add_node("regression", regression_node)
    g.add_edge(START, "vision")
    g.add_edge("vision", "evidence")
    g.add_edge("evidence", "reproduction")
    g.add_edge("reproduction", "investigator")
    g.add_edge("investigator", "regression")
    g.add_edge("regression", END)
    return g.compile()


def run_pipeline(actions, segments, console_log=None, repo_path=".", project_dir=None, screenshot=None):
    """端到端编排：截图(可选) + actions + segments → vision → 时间线 → 复现 → 代码调查 → 回归 Issue。"""
    graph = build_graph()
    initial = {
        "actions": actions,
        "segments": segments,
        "console_log": console_log or [],
        "repo_path": repo_path,
        "project_dir": project_dir,
        "screenshot": screenshot,
    }
    return graph.invoke(initial)
