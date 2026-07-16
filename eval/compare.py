"""eval/compare.py — 远程(Stepfun) vs 本地(qwen35b) 指标对比（plan Task 4.3）

对同一批 test_case 跑两次 run_pipeline（PROFILE=local / 默认远程），收集 metrics。
切 PROFILE 时重置 llm.client._client（否则 _client 缓存旧 base_url，切换不生效）。
"""
import os
from contextlib import contextmanager

import llm.client
from asr.transcribe import Segment
from eval.metrics import metrics_from_state
from graph.workflow import run_pipeline


@contextmanager
def _profile(name):
    """切 PROFILE 并重置 llm client 单例（否则 _client 缓存旧 base_url）。"""
    old = os.environ.get("PROFILE")
    if name == "local":
        os.environ["PROFILE"] = "local"
    else:
        os.environ.pop("PROFILE", None)
    llm.client._client = None
    try:
        yield
    finally:
        if old is not None:
            os.environ["PROFILE"] = old
        else:
            os.environ.pop("PROFILE", None)
        llm.client._client = None


def compare(test_cases, repo_path, project_dir):
    """每个 profile × 每个 test_case 跑 run_pipeline，收集 metrics。
    返回 [{profile, name, metrics}]。"""
    out = []
    for profile in ["local", "remote"]:
        with _profile(profile):
            for name, actions, narration in test_cases:
                segs = [Segment(text=narration, start=0.0, end=10.0)] if narration else []
                state = run_pipeline(actions, segs, console_log=[],
                                     repo_path=repo_path, project_dir=project_dir)
                m = metrics_from_state(state)
                out.append({"profile": profile, "name": name, "metrics": m.__dict__})
    return out
