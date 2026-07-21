"""capture/video_parser.py — 视频输入：视频 → segments + actions + screenshot

上传测试员录的视频（边操作边口述）→ 提音频 ASR + LLM 从口述提 actions + 抽帧截图。
任意一步失败都不阻塞（返回空/None），由上层 UI 提示。
"""
import os
import tempfile
import subprocess
from pathlib import Path

import imageio_ffmpeg

from asr.transcribe import Segment
from llm.client import chat_json


_MODEL = None


def _get_whisper():
    """faster-whisper small（CPU int8），单例。首次下载复用 HF 镜像环境变量。"""
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel("small", device="cpu", compute_type="int8")
    return _MODEL


def video_to_segments(video_path):
    """视频 → 提音频(wav 16k mono) → faster-whisper → Segment 列表。

    失败（无音轨/转写错）→ 返回 []。
    """
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    try:
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", "-y", wav],
            capture_output=True, timeout=120,
        )
        if not os.path.exists(wav) or os.path.getsize(wav) == 0:
            return []
        model = _get_whisper()
        segs, _info = model.transcribe(wav, language="zh", vad_filter=True)
        return [Segment(text=s.text.strip(), start=round(s.start, 2), end=round(s.end, 2))
                for s in segs if s.text.strip()]
    except Exception:
        return []
    finally:
        try:
            os.unlink(wav)
        except OSError:
            pass


_PROMPT = """你是测试工程师。测试员口述了他在网页上的操作：{narration}
请把它提取成操作步骤，用于 Playwright 复现。只输出 JSON：
{{"actions": [{{"type": "fill 或 click", "target": "元素的 data-testid", "value": "输入值(click 为空)", "text": "该步中文描述"}}, ...]}}

已知该商城的 data-testid 有：coupon-input（优惠码输入框）、apply-btn（应用按钮）、qty-input（数量输入框）、total-price（总价）、remove-btn（删除）。请把口述里的操作映射到这些 testid。
只输出 JSON，不要解释。操作不明确就尽量推断。"""


def segments_to_actions(segments):
    """segments（口述）→ LLM 提 actions 列表。口述空/失败 → []。"""
    narration = " ".join(s.text for s in segments).strip()
    if not narration:
        return []
    try:
        result = chat_json([{"role": "user", "content": _PROMPT.format(narration=narration)}]) or {}
    except Exception:
        return []
    actions = result.get("actions") or []
    out = []
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            continue
        a.setdefault("timestamp", float(i + 1))
        a.setdefault("text", a.get("target", ""))
        out.append(a)
    return out


def video_to_screenshot(video_path, at_ratio=0.7):
    """视频 → 抽中间偏后帧 → png 路径。失败 → None。"""
    try:
        import cv2
        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * at_ratio))
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return None
        png = tempfile.NamedTemporaryFile(suffix=".png", delete=False).name
        cv2.imwrite(png, frame)
        return png
    except Exception:
        return None


def parse_video(video_path):
    """视频 → (actions, narration_text, screenshot_path)。UI 调这个。

    任意子步骤失败都不抛（返回空/None），由 UI 提示。
    """
    segments = video_to_segments(video_path)
    narration = " ".join(s.text for s in segments).strip()
    actions = segments_to_actions(segments)
    screenshot = video_to_screenshot(video_path)
    return actions, narration, screenshot
