"""VL 冒烟：验证 step-3.7-flash 图像理解能力（VL 可行性前提，spec §10 step1）。

用法：python spike/smoke_vl.py [截图路径]  （默认用 提交.png）
看 VisualFinding.used=True 即 step-3.7 支持图像输入 → VL 可行。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents.vision import analyze_screenshot

screenshot = sys.argv[1] if len(sys.argv) > 1 else r"C:\计算机项目\hackthon0625\提交要求\提交.png"
narration = "这是一张关于黑客松项目提交要求的截图，请识别图里的文字要点"

print("=== VL 冒烟：验证 step-3.7-flash 图像能力 ===")
print(f"截图: {screenshot}")
vf = analyze_screenshot(screenshot, narration)
print(f"used={vf.used}  confidence={vf.confidence:.2f}  needs_confirm={vf.needs_confirm}")
print(f"page_description={vf.page_description!r}")
if vf.used:
    print("[OK] step-3.7 支持图像输入 -> VL 可行")
else:
    print("[WARN] step-3.7 未返回有效图像理解（不支持图/图不清/调用失败）-> VL 将降级")
