"""ui/app.py — Gradio 界面（plan Task 3.2）

MVP：文本输入操作步骤 + 口述（模拟 ASR 转写）→ run_pipeline → 结果展示（Issue + 摘要 + 测试代码）。
真实录制/ASR（capture/recorder + asr 已实现）后续接入（上传音频→asr→segments）。
run_pipeline_ui 为业务函数（不依赖 gradio，可独立测试）；build_app 是薄包装。
"""
import json
from pathlib import Path

from asr.transcribe import Segment
from graph.workflow import run_pipeline
from capture.recorder import record_user_session
from capture.video_parser import parse_video

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PROJECT = str(_REPO_ROOT / "demo_project")
DEMO_URL = "http://localhost:5173"   # 被测商城（录制操作时弹出）


def record_actions_fn():
    """点录制 → 弹出商城浏览器 → 用户操作后点页面右上角「完成录制」→ actions 填回 JSON 框。"""
    actions = record_user_session(DEMO_URL, timeout=90)
    if not actions:
        return "[]  # 未录到操作（没操作 / 浏览器提前关）"
    return json.dumps(actions, ensure_ascii=False, indent=2)


def parse_video_fn(video_path):
    """点「从视频生成」→ 解析视频 → 填回 actions / narration / screenshot。"""
    if not video_path:
        return None, None, None, "⚠️ 请先上传视频"
    actions, narration, screenshot = parse_video(video_path)
    actions_json = (json.dumps(actions, ensure_ascii=False, indent=2)
                    if actions else "[]  # 未提取到操作（检查视频是否有清晰口述）")
    msg = (f"✓ 视频解析完成：{len(actions)} 步操作，口述 {len(narration)} 字"
           + ("，截图已抽帧" if screenshot else ""))
    return actions_json, narration, screenshot, msg

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
    theme = gr.themes.Soft(
        primary_hue="emerald",
        neutral_hue="slate",
    )
    css = """
    .gradio-container { font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif; }
    .rf-header { text-align: center; padding: 10px 0 6px; }
    .rf-title { font-size: 2.3em; font-weight: 900; letter-spacing: -0.03em; line-height: 1.1; }
    .rf-sub { color: #64748b; font-size: 0.95em; margin-top: 4px; }
    .rf-pipeline { color: #10b981; font-family: 'JetBrains Mono', monospace; font-size: 0.82em; margin-top: 8px; letter-spacing: 0.02em; }
    """
    with gr.Blocks(title="ReproForge — Bug 复现与回归智能体", theme=theme, css=css) as app:
        gr.HTML(
            '<div class="rf-header">'
            '<div class="rf-title">🔧 ReproForge</div>'
            '<div class="rf-sub">大模型理解 Bug，Playwright 证明 Bug · 多模态视觉 + 历史记忆</div>'
            '<div class="rf-pipeline">vision → evidence → reproduction → recall → investigator → regression</div>'
            '<div style="margin-top:10px;"><a href="http://localhost:5173" target="_blank" rel="noopener" style="color:#10b981;font-weight:600;text-decoration:none;">→ 打开被测商城（操作发现 Bug 后回来复现）</a></div>'
            '</div>'
        )
        record_btn = gr.Button("🎬 录制操作（弹浏览器操作商城，完事点页面「完成录制」）", size="sm")
        video_in = gr.Video(label="上传操作视频（可选 → 点下方按钮自动生成 actions / 口述 / 截图）")
        parse_btn = gr.Button("🎬 从视频生成（解析操作 + 口述 + 截图）", size="sm")
        parse_msg = gr.Markdown()
        with gr.Row():
            actions_json = gr.Textbox(label="操作步骤 JSON（可点上方按钮真实录制）", value=DEMO_ACTIONS, lines=12, scale=2)
            with gr.Column(scale=1):
                narration = gr.Textbox(label="口述（模拟 ASR 转写）", value=DEMO_NARRATION, lines=3)
                screenshot = gr.Image(label="Bug 截图（可选，VL 视觉）", type="filepath")
        record_btn.click(record_actions_fn, [], [actions_json])
        parse_btn.click(parse_video_fn, [video_in], [actions_json, narration, screenshot, parse_msg])
        with gr.Accordion("高级（项目目录 / 代码检索）", open=False):
            with gr.Row():
                project_dir = gr.Textbox(label="被测项目目录", value=DEMO_PROJECT, scale=2)
                repo_path = gr.Textbox(label="代码检索目录（留空同上）", value="", scale=2)
        btn = gr.Button("▶ 运行复现流水线", variant="primary", size="lg")
        summary = gr.Markdown()
        with gr.Row():
            issue_md = gr.Markdown(label="生成的 Issue", scale=1)
            spec_code = gr.Code(label="生成的 Playwright 测试", language="typescript", scale=1)
        btn.click(run_pipeline_ui, [actions_json, narration, project_dir, repo_path, screenshot],
                  [issue_md, summary, spec_code])
    return app


if __name__ == "__main__":
    build_app().launch()
