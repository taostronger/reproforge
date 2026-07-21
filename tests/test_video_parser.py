"""video_parser 测试：mock ffmpeg/whisper/LLM/cv2，不真跑视频处理。"""
from pathlib import Path
from unittest.mock import patch, MagicMock

from capture.video_parser import (
    segments_to_actions, video_to_screenshot, video_to_segments, parse_video,
)
from asr.transcribe import Segment


# ---- segments_to_actions ----

def test_segments_to_actions_extracts_with_testid_mapping():
    """mock chat_json → actions（target 用 testid）。"""
    fake = {"actions": [
        {"type": "fill", "target": "coupon-input", "value": "SALE20", "text": "优惠码"},
        {"type": "click", "target": "apply-btn", "text": "应用"},
    ]}
    segs = [Segment(text="我填了优惠码SALE20点了应用", start=0, end=5)]
    with patch("capture.video_parser.chat_json", return_value=fake):
        actions = segments_to_actions(segs)
    assert len(actions) == 2
    assert actions[0]["target"] == "coupon-input" and actions[0]["value"] == "SALE20"
    assert actions[1]["target"] == "apply-btn"
    assert "timestamp" in actions[0]            # 自动补 timestamp


def test_segments_to_actions_empty_narration_returns_empty():
    assert segments_to_actions([]) == []
    assert segments_to_actions([Segment(text="   ", start=0, end=1)]) == []


def test_segments_to_actions_llm_failure_returns_empty():
    segs = [Segment(text="操作描述", start=0, end=1)]
    with patch("capture.video_parser.chat_json", side_effect=Exception("LLM fail")):
        assert segments_to_actions(segs) == []


# ---- video_to_screenshot ----

def test_video_to_screenshot_returns_png():
    """mock cv2（sys.modules）→ png 路径。"""
    mock_cv2 = MagicMock()
    mock_cap = MagicMock()
    mock_cv2.VideoCapture.return_value = mock_cap
    mock_cap.get.return_value = 100
    mock_cap.read.return_value = (True, "frame")
    with patch.dict("sys.modules", {"cv2": mock_cv2}):
        out = video_to_screenshot("video.mp4")
    assert out is not None and out.endswith(".png")


def test_video_to_screenshot_failure_returns_none():
    mock_cv2 = MagicMock()
    mock_cv2.VideoCapture.side_effect = Exception("cv2 boom")
    with patch.dict("sys.modules", {"cv2": mock_cv2}):
        assert video_to_screenshot("video.mp4") is None


# ---- video_to_segments ----

def test_video_to_segments_runs_ffmpeg_and_whisper(monkeypatch):
    """mock subprocess（提音频，touch wav）+ whisper.transcribe → segments。"""
    fake_seg = MagicMock(text="我填了SALE20", start=0.0, end=2.0)
    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_seg], MagicMock())
    monkeypatch.setattr("capture.video_parser._get_whisper", lambda: fake_model)

    def fake_run(cmd, *a, **kw):
        Path(cmd[-1]).write_bytes(b"fake wav bytes")    # touch 输出 wav
    monkeypatch.setattr("capture.video_parser.subprocess.run", fake_run)

    segs = video_to_segments("video.mp4")
    assert len(segs) == 1
    assert "SALE20" in segs[0].text


def test_video_to_segments_no_audio_returns_empty(monkeypatch):
    """无音轨（wav 没生成）→ []。"""
    monkeypatch.setattr("capture.video_parser.subprocess.run", lambda *a, **kw: None)  # 不 touch wav
    assert video_to_segments("video.mp4") == []


# ---- parse_video ----

def test_parse_video_combines_three_steps(monkeypatch):
    monkeypatch.setattr("capture.video_parser.video_to_segments",
                        lambda p: [Segment(text="x", start=0, end=1)])
    monkeypatch.setattr("capture.video_parser.segments_to_actions", lambda s: [{"type": "click"}])
    monkeypatch.setattr("capture.video_parser.video_to_screenshot", lambda p, **k: "/tmp/x.png")
    actions, narration, screenshot = parse_video("v.mp4")
    assert actions == [{"type": "click"}]
    assert narration == "x"
    assert screenshot == "/tmp/x.png"
