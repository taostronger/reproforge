"""Task 0.3 Spike: faster-whisper 转写 + 关键词/数字提取
闸门2(语音理解): 能从口述提取预期¥160、实际¥80
用法: python spike/transcribe_spike.py [音频路径]
"""
import sys
import re
from pathlib import Path
from faster_whisper import WhisperModel

_model = None


def get_model():
    global _model
    if _model is None:
        print("加载 whisper small 模型（首次会下载约480MB，请等待）...")
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


def transcribe(audio_path):
    model = get_model()
    segments, _info = model.transcribe(audio_path, language="zh", vad_filter=True)
    texts = []
    for seg in segments:
        t = seg.text.strip()
        if t:
            texts.append({"text": t, "start": round(seg.start, 2), "end": round(seg.end, 2)})
            print(f"  [{seg.start:.1f}-{seg.end:.1f}] {t}")
    return texts


def extract(texts):
    full = "".join(t["text"] for t in texts)
    nums = re.findall(r"\d+", full)
    int_nums = [int(n) for n in nums]
    print("=== 闸门2: 语音理解 ===")
    print(f"  全文: {full}")
    print(f"  数字: {nums}")
    print(f"  含期望值160: {160 in int_nums}")
    print(f"  含实际值80: {80 in int_nums}")
    return full


if __name__ == "__main__":
    audio = sys.argv[1] if len(sys.argv) > 1 else "spike/sample.wav"
    if not Path(audio).exists():
        print(f"音频不存在: {audio}")
        sys.exit(1)
    texts = transcribe(audio)
    if not texts:
        print("未转写出内容")
        sys.exit(1)
    extract(texts)
