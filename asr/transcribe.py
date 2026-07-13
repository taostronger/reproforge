"""asr/transcribe.py — faster-whisper 转写（plan Task 1.5）

带时间戳的中文转写。whisper small 模型首次下载需 HF_ENDPOINT=hf-mirror + HF_HUB_DISABLE_XET=1
（Spike 时已下载缓存，后续直接用）。
"""
from dataclasses import dataclass

_model = None


@dataclass
class Segment:
    text: str
    start: float
    end: float


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path):
    """转写音频，返回 Segment 列表（带时间戳，过滤空段）。"""
    model = get_model()
    segments, _info = model.transcribe(audio_path, language="zh", vad_filter=True)
    return [
        Segment(text=s.text.strip(), start=round(s.start, 2), end=round(s.end, 2))
        for s in segments if s.text.strip()
    ]
