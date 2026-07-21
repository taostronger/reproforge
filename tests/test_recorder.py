"""Task 1.3 集成测试：录一段 demo 操作，验证产物齐备。
前提：demo_project 已 npm run dev 在 http://localhost:5173
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 集成测试：需 playwright + demo_project 在 localhost:5173，缺则跳过（不阻塞 pytest 收集）
pytest.importorskip("playwright")

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


def _mock_playwright(monkeypatch, page):
    """构造 mock sync_playwright，返回给定 fake_page。"""
    from unittest.mock import MagicMock
    browser = MagicMock()
    browser.new_page.return_value = page
    ctx = MagicMock()
    ctx.chromium.launch.return_value = browser
    ctx.__enter__.return_value = ctx
    ctx.__exit__.return_value = None
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: ctx)


def test_record_user_session_collects_actions_and_injects_js(monkeypatch):
    """mock 浏览器：验证注入 JS、goto、取出 window.__actions。"""
    from unittest.mock import MagicMock
    import capture.recorder as rec
    fake_actions = [{"type": "click", "target": "apply-btn", "value": "", "timestamp": 1.5, "text": "apply-btn"}]
    fake_page = MagicMock()
    fake_page.evaluate.side_effect = [False, True, fake_actions]   # __done ×2 + actions
    _mock_playwright(monkeypatch, fake_page)

    result = rec.record_user_session("http://localhost:5173", timeout=5)
    assert result == fake_actions
    fake_page.add_init_script.assert_called_once()                 # 注入了监听 JS
    fake_page.goto.assert_called_once_with("http://localhost:5173")


def test_record_user_session_returns_empty_when_page_closed(monkeypatch):
    """浏览器提前关（evaluate 抛异常）→ 返回 []（降级，不崩）。"""
    from unittest.mock import MagicMock
    import capture.recorder as rec
    fake_page = MagicMock()
    fake_page.evaluate.side_effect = Exception("page closed")
    _mock_playwright(monkeypatch, fake_page)

    result = rec.record_user_session("http://x", timeout=3)
    assert result == []
