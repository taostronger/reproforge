"""VL vision agent 测试：_to_data_uri + analyze_screenshot（无图降级 / 正常解析 / 异常降级）。

全部 mock chat_vision 与 _to_data_uri，不依赖真实 API/图片文件。
"""
from unittest.mock import patch

from agents.vision import analyze_screenshot, VisualFinding, _to_data_uri


def test_analyze_screenshot_no_screenshot_returns_empty():
    """无图 → 空 VisualFinding（used=False，降级）。"""
    vf = analyze_screenshot(None, "数量改2总价还是80")
    assert vf.used is False
    assert vf.expected == ""
    assert vf.actual == ""


def test_analyze_screenshot_parses_vision_response():
    """有图 + chat_vision 返回 JSON → VisualFinding（used=True，高置信不确认）。"""
    fake = {"expected": "160", "actual": "80", "page_description": "总价显示80", "confidence": 0.9}
    with patch("agents.vision.chat_vision", return_value=fake), \
         patch("agents.vision._to_data_uri", return_value="data:image/png;base64,xxx"):
        vf = analyze_screenshot("/bug.png", "数量改2总价还是80")
    assert vf.used is True
    assert vf.expected == "160"
    assert vf.actual == "80"
    assert vf.confidence == 0.9
    assert vf.needs_confirm is False      # 0.9 >= 0.6


def test_analyze_screenshot_low_confidence_needs_confirm():
    """低置信 → needs_confirm=True（沿用 evidence 的确认语义）。"""
    fake = {"expected": "?", "actual": "?", "page_description": "看不清", "confidence": 0.2}
    with patch("agents.vision.chat_vision", return_value=fake), \
         patch("agents.vision._to_data_uri", return_value="data:image/png;base64,xxx"):
        vf = analyze_screenshot("/bug.png", "口述")
    assert vf.used is True
    assert vf.needs_confirm is True       # 0.2 < 0.6


def test_analyze_screenshot_vision_failure_degrades():
    """chat_vision 抛异常 → 空 VisualFinding（used=False，降级，evidence 照旧）。"""
    with patch("agents.vision.chat_vision", side_effect=Exception("API timeout")), \
         patch("agents.vision._to_data_uri", return_value="data:image/png;base64,xxx"):
        vf = analyze_screenshot("/bug.png", "口述")
    assert vf.used is False


def test_to_data_uri_url_passthrough():
    """http/https/data 直接返回，不读文件。"""
    assert _to_data_uri("https://example.com/x.png") == "https://example.com/x.png"
    assert _to_data_uri("data:image/png;base64,abc") == "data:image/png;base64,abc"


def test_to_data_uri_local_file(tmp_path):
    """本地文件 → base64 data URI。"""
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n")   # PNG header
    uri = _to_data_uri(str(p))
    assert uri.startswith("data:image/png;base64,")
