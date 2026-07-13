"""Task 1.5 测试：转写预录音频，验证带时间戳段。
前提：spike/sample.wav 存在（Spike 时 edge-tts 生成）；whisper small 模型已缓存。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from asr.transcribe import transcribe


def test_transcribe_returns_segments():
    audio = os.path.join(os.path.dirname(__file__), "..", "spike", "sample.wav")
    if not os.path.exists(audio):
        import pytest
        pytest.skip("无 spike/sample.wav，先用 edge-tts 生成")
    segs = transcribe(audio)
    assert len(segs) > 0
    full = "".join(s.text for s in segs)
    # 口述含预期160/实际80
    assert "160" in full or "80" in full, f"转写未含关键数字: {full}"
