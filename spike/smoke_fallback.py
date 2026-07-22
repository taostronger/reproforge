"""fallback 冒烟：故意把 LOCAL_VL_BASE_URL 指向无人监听的端口，
确认 chat_vision 自动降级到远程 step-3.7 并成功返回。

用法：python spike/smoke_fallback.py [截图路径]
看 used=True 即 fallback 链路通（本地挂 → 远程兜底成功）。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 故意指向无人端口，逼本地 VL 失败 → 触发远程 fallback
os.environ["LOCAL_VL_BASE_URL"] = "http://localhost:9999/v1"
os.environ["LOCAL_VL_MODEL"] = "none"

from agents.vision import analyze_screenshot

screenshot = sys.argv[1] if len(sys.argv) > 1 else r"C:\计算机项目\hackthon0625\提交要求\提交.png"
narration = "这是黑客松提交要求截图，请识别要点"

print("=== fallback 冒烟：本地 VL 故意失败 → 远程兜底 ===")
print(f"LOCAL_VL_BASE_URL={os.environ['LOCAL_VL_BASE_URL']}（应连不上）")
vf = analyze_screenshot(screenshot, narration)
print(f"used={vf.used}  confidence={vf.confidence:.2f}")
if vf.used:
    print("[OK] 本地 VL 挂了，远程 fallback 成功 → 加固链路通")
else:
    print("[WARN] fallback 也失败（远程 step-3.7 也连不上/不支持图）")
