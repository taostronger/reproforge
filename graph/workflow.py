"""graph/workflow.py — LangGraph 编排（plan Task 3.1）

StateGraph 串联 evidence → reproduction → code_investigator → regression。
编排层接受已解析的 actions/segments（解耦采集层 trace_parser，后者未实现）。
"""
from typing import Any, Optional, TypedDict

from langgraph.graph import START, END, StateGraph

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
    timeline: Any
    repro_result: Any
    top_files: Any
    issue: Any


def evidence_node(state):
    tl = build_timeline(state["actions"], state["segments"], state["console_log"])
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
    g.add_node("evidence", evidence_node)
    g.add_node("reproduction", reproduction_node)
    g.add_node("investigator", investigator_node)
    g.add_node("regression", regression_node)
    g.add_edge(START, "evidence")
    g.add_edge("evidence", "reproduction")
    g.add_edge("reproduction", "investigator")
    g.add_edge("investigator", "regression")
    g.add_edge("regression", END)
    return g.compile()


def run_pipeline(actions, segments, console_log=None, repo_path=".", project_dir=None):
    """端到端编排：actions+segments → 时间线 → 复现 → 代码调查 → 回归 Issue。
    actions/segments 由上层解析（trace_parser 留后），编排层只负责串联。"""
    graph = build_graph()
    initial = {
        "actions": actions,
        "segments": segments,
        "console_log": console_log or [],
        "repo_path": repo_path,
        "project_dir": project_dir,
    }
    return graph.invoke(initial)
