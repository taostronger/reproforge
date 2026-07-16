"""Task 3.2 测试：UI 业务函数 run_pipeline_ui（mock run_pipeline，不真调 LLM/浏览器）。"""
import json
from unittest.mock import patch

from ui.app import run_pipeline_ui
from agents.evidence import BugTimeline
from agents.reproduction import ReproductionResult
from agents.code_investigator import TopFiles, FileScore
from agents.regression import Issue


def _fake_state():
    return {
        "timeline": BugTimeline(events=[], expected="160", actual="80"),
        "repro_result": ReproductionResult(
            success=True, spec_code="import {test} from '@playwright/test';",
            stable_rate="3/3", rounds=0, reason="stable_repro"),
        "top_files": TopFiles(files=[FileScore(path="App.tsx", score=0.9, reason="总价")]),
        "issue": Issue(title="Bug", expected="160", actual="80", body="# Bug Issue\n## 预期\n160"),
    }


def test_run_pipeline_ui_formats_output(tmp_path):
    actions = json.dumps([{"type": "fill", "target": "qty-input", "value": "2", "timestamp": 1.0}])
    with patch("ui.app.run_pipeline", return_value=_fake_state()):
        body, summary, spec = run_pipeline_ui(actions, "口述", str(tmp_path), "")
    assert "# Bug Issue" in body
    assert "160" in summary and "3/3" in summary
    assert "App.tsx" in summary
    assert "playwright/test" in spec


def test_run_pipeline_ui_bad_json_returns_warning(tmp_path):
    body, summary, spec = run_pipeline_ui("not json", "x", str(tmp_path), "")
    assert "JSON 解析失败" in body
    assert summary == "" and spec == ""
