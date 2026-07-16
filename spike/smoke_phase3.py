"""Phase 3 端到端冒烟：run_pipeline 真调 4 agent，验证串联 + Bug1 复现 + Issue 生成。
前提：demo_project npm run dev 在 http://localhost:5173。
运行： python spike/smoke_phase3.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from asr.transcribe import Segment
from graph.workflow import run_pipeline

DEMO = Path(__file__).resolve().parent.parent / "demo_project"


def main():
    print("=== Phase 3 端到端 run_pipeline（真调 4 agent）===")
    actions = [
        {"type": "fill", "target": "coupon-input", "value": "SALE20", "timestamp": 1.0, "text": "优惠码"},
        {"type": "click", "target": "apply-btn", "timestamp": 2.0, "text": "应用"},
        {"type": "fill", "target": "qty-input", "value": "2", "timestamp": 3.0, "text": "数量"},
    ]
    segments = [Segment(text="我用了一张八折优惠券，然后把数量改成2，结果总价还是80，应该是160才对",
                        start=0.5, end=6.0)]
    state = run_pipeline(actions, segments, console_log=[], repo_path=str(DEMO), project_dir=str(DEMO))
    tl = state["timeline"]
    repro = state["repro_result"]
    top = state["top_files"]
    issue = state["issue"]
    print(f"[evidence]      expected={tl.expected!r} actual={tl.actual!r} needs_confirm={tl.needs_confirm}")
    print(f"[reproduction]  success={repro.success} stable={repro.stable_rate} rounds={repro.rounds} reason={repro.reason}")
    print(f"[investigator]  top_files={[Path(f.path).name for f in top.files]}")
    print(f"[regression]    title={issue.title!r}")
    print("--- issue.body 前600字 ---")
    print(issue.body[:600])


if __name__ == "__main__":
    main()
