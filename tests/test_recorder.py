"""Task 1.3 集成测试：录一段 demo 操作，验证产物齐备。
前提：demo_project 已 npm run dev 在 http://localhost:5173
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from capture.recorder import record


def test_record_produces_artifacts(tmp_path):
    url = "http://localhost:5173"
    actions = [
        ("fill", "[data-testid=coupon-input]", "SALE20"),
        ("click", "[data-testid=apply-btn]", None),
        ("fill", "[data-testid=qty-input]", "2"),
    ]
    art = record(url, actions, str(tmp_path))
    assert art.trace_zip.exists() and art.trace_zip.stat().st_size > 1000
    assert art.console_log.exists()
    assert art.network_har.exists() and art.network_har.stat().st_size > 0
