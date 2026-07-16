"""D2 冒烟：真跑生成的 Playwright spec，验证复现 Bug1。
前提：demo_project 已 npm install + 装 @playwright/test + chromium；且 `npm run dev` 在 http://localhost:5173 跑着。
运行： python spike/smoke_d2.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents.reproduction import generate_test
from test_runner.runner import run_test

DEMO = Path(__file__).resolve().parent.parent / "demo_project"


def step_d():
    print("=== D. 真跑生成的 spec（期望红色失败 = Bug1 复现）===")
    steps = [
        {"type": "fill", "target": "coupon-input", "value": "SALE20", "text": "优惠码"},
        {"type": "click", "target": "apply-btn", "text": "应用"},
        {"type": "fill", "target": "qty-input", "value": "2", "text": "数量"},
    ]
    spec = generate_test(steps, expected="160", actual="80")
    p = DEMO / "smoke_repro.spec.ts"
    p.write_text(spec, encoding="utf-8")
    print(f"  spec 已写: {p.name}")
    r = run_test(str(p), cwd=str(DEMO))
    print(f"  passed={r.passed}  duration={r.duration:.1f}s")
    if not r.passed:
        print("  ✅ 红色失败 = Bug1 成功复现（总价 80 ≠ 预期 160）")
    else:
        print("  ⚠️ 测试通过 = Bug 没复现（意外，需排查）")
    p.unlink(missing_ok=True)
    # 清理 playwright 产物，避免污染 code_search 检索
    for d in ["test-results", "playwright-report"]:
        shutil.rmtree(DEMO / d, ignore_errors=True)


if __name__ == "__main__":
    step_d()
