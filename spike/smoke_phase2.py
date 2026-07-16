"""Phase 2 冒烟：真实调 Stepfun 验证底层 agent（不 mock）。
运行： python spike/smoke_phase2.py
阶段 A=Stepfun 连通  B=evidence(chat_json)  C/D 在 demo 环境就绪后另跑。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from llm.client import chat
from asr.transcribe import Segment
from agents.evidence import build_timeline


def step_a():
    print("=== A. Stepfun 连通性（chat）===")
    r = chat([{"role": "user", "content": "只回复两个字：你好"}])
    print("  返回:", repr(r[:120]))
    assert r and len(r) > 0, "chat 无返回"
    print("  ✅ chat 正常")


def step_b():
    print("\n=== B. evidence 真调 chat_json 提取 expected/actual ===")
    actions = [
        {"type": "fill", "target": "coupon-input", "value": "SALE20", "timestamp": 1.0, "text": "优惠码"},
        {"type": "click", "target": "apply-btn", "timestamp": 2.0, "text": "应用"},
        {"type": "fill", "target": "qty-input", "value": "2", "timestamp": 3.0, "text": "数量"},
    ]
    segments = [Segment(text="我用了一张八折优惠券，然后把数量改成2，结果总价还是80，应该是160才对",
                        start=0.5, end=6.0)]
    tl = build_timeline(actions, segments, [])
    print(f"  expected={tl.expected!r}  actual={tl.actual!r}  needs_confirm={tl.needs_confirm}")
    print(f"  events[0].narration={tl.events[0].user_narration!r}")
    print(f"  suspected_anomaly 事件={[e.event_id for e in tl.events if e.suspected_anomaly]}")
    ok = not tl.needs_confirm and tl.expected and tl.actual
    print("  ✅ evidence 真调完成" + ("（提取成功）" if ok else "（⚠️ 置信度低或未提取，需确认）"))


def step_c():
    print("\n=== C. generate_test 真调 LLM 生成 Playwright spec（命门）===")
    from agents.reproduction import generate_test
    steps = [
        {"type": "fill", "target": "coupon-input", "value": "SALE20", "text": "优惠码"},
        {"type": "click", "target": "apply-btn", "text": "应用"},
        {"type": "fill", "target": "qty-input", "value": "2", "text": "数量"},
    ]
    spec = generate_test(steps, expected="160", actual="80")
    print("  --- 生成的 spec（前 700 字）---")
    print("    " + spec[:700].replace("\n", "\n    "))
    has_test = "test(" in spec or "test (" in spec
    has_expect = "expect" in spec
    has_testid = "getByTestId" in spec or "data-testid" in spec.lower()
    has_160 = "160" in spec
    has_fence = "```" in spec
    print(f"\n  质量检查: test块={has_test}  expect断言={has_expect}  testid定位={has_testid}  含预期160={has_160}  含markdown围栏={has_fence}")
    out = Path(__file__).resolve().parent / "smoke_generated.spec.ts"
    out.write_text(spec, encoding="utf-8")
    print(f"  已保存原始输出: {out}")
    if has_fence:
        print("  ⚠️ 注意：输出含 ``` 围栏，真跑前需剥离（generate_test 当前未剥离）")


if __name__ == "__main__":
    step_a()
    step_b()
    step_c()
    print("\n冒烟阶段 A+B+C 完成")
