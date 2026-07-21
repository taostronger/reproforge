"""ui/app.py — Gradio 界面（plan Task 3.2）

MVP：文本输入操作步骤 + 口述（模拟 ASR 转写）→ run_pipeline → 结果展示（Issue + 摘要 + 测试代码）。
真实录制/ASR（capture/recorder + asr 已实现）后续接入（上传音频→asr→segments）。
run_pipeline_ui 为业务函数（不依赖 gradio，可独立测试）；build_app 是薄包装。
"""
import json
from pathlib import Path

from asr.transcribe import Segment
from graph.workflow import run_pipeline

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PROJECT = str(_REPO_ROOT / "demo_project")

DEMO_ACTIONS = json.dumps([
    {"type": "fill", "target": "coupon-input", "value": "SALE20", "timestamp": 1.0, "text": "优惠码"},
    {"type": "click", "target": "apply-btn", "timestamp": 2.0, "text": "应用"},
    {"type": "fill", "target": "qty-input", "value": "2", "timestamp": 3.0, "text": "数量"},
], ensure_ascii=False, indent=2)

DEMO_NARRATION = "我用了一张八折优惠券，然后把数量改成2，结果总价还是80，应该是160才对"


def run_pipeline_ui(actions_json, narration, project_dir, repo_path, screenshot=None):
    """UI 业务函数：解析输入 → run_pipeline → (issue_body, summary_md, spec_code)。可独立测试。"""
    try:
        actions = json.loads(actions_json)
    except Exception as e:
        return f"⚠️ 操作步骤 JSON 解析失败：{e}", "", ""
    segments = [Segment(text=narration, start=0.0, end=10.0)] if narration else []
    proj = (project_dir or "").strip() or None
    rp = (repo_path or "").strip() or proj or DEMO_PROJECT
    state = run_pipeline(actions, segments, console_log=[], repo_path=rp, project_dir=proj,
                         screenshot=screenshot)
    tl = state["timeline"]
    repro = state["repro_result"]
    top = state["top_files"]
    summary = (
        "### 复现结果\n"
        f"- **预期 / 实际**：{tl.expected} / {tl.actual}（needs_confirm={tl.needs_confirm}）\n"
        f"- **复现**：success={repro.success}，稳定率={repro.stable_rate}，"
        f"定位器修复={repro.rounds} 轮，原因={repro.reason}\n"
        f"- **可疑文件 Top3**：{', '.join(Path(f.path).name for f in top.files) or '(无)'}"
    )
    vf = state.get("visual_finding")
    if vf is not None and getattr(vf, "used", False):
        summary += (
            "\n### VL 视觉（看截图）\n"
            f"- 预期/实际：{vf.expected} / {vf.actual}（置信度 {vf.confidence:.2f}）\n"
            f"- 页面描述：{vf.page_description or '(无)'}"
        )
    return state["issue"].body, summary, repro.spec_code


def build_app():
    import gradio as gr
    with gr.Blocks(title="ReproForge") as app:
        gr.Markdown("# ReproForge — Bug 复现与回归智能体\n"
                    "大模型理解 Bug，Playwright 证明 Bug。输入操作步骤 + 口述，自动复现并生成 Issue。")
        with gr.Row():
            actions_json = gr.Textbox(label="操作步骤 JSON", value=DEMO_ACTIONS, lines=10)
            narration = gr.Textbox(label="口述（模拟 ASR 转写）", value=DEMO_NARRATION, lines=4)
        with gr.Row():
            project_dir = gr.Textbox(label="被测项目目录（spec 写入 + playwright cwd）", value=DEMO_PROJECT)
            repo_path = gr.Textbox(label="代码检索目录（留空同上）", value="")
        screenshot = gr.Image(label="Bug 截图（可选，VL 视觉分析）", type="filepath")
        btn = gr.Button("运行复现流水线", variant="primary")
        summary = gr.Markdown()
        issue_md = gr.Markdown(label="生成的 Issue")
        spec_code = gr.Code(label="生成的 Playwright 测试", language="typescript")
        btn.click(run_pipeline_ui, [actions_json, narration, project_dir, repo_path, screenshot],
                  [issue_md, summary, spec_code])
    return app


if __name__ == "__main__":
    build_app().launch()
