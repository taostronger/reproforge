"""capture/recorder.py — Playwright 录制器（plan Task 1.3）

录操作序列 + trace（含截图/snapshot/source）+ console 日志 + network HAR。
音频单独处理（spark-71 无麦克风，测试人员口述用预录音频上传）。
"""
from pathlib import Path
from dataclasses import dataclass
from playwright.sync_api import sync_playwright


@dataclass
class RecordingArtifact:
    trace_zip: Path
    console_log: Path
    network_har: Path


def record(url, actions, out_dir):
    """录操作序列。

    actions: list of (type, selector, value?)，type ∈ {fill, click, select}
    返回 RecordingArtifact；断言所有产物存在且非空。
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    trace_zip = out / "trace.zip"
    console_log = out / "console.log"
    network_har = out / "network.har"
    console_lines = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(record_har_path=str(network_har))
        page = context.new_page()
        page.on("console", lambda m: console_lines.append(f"[{m.type}] {m.text}"))
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        try:
            page.goto(url)
            page.wait_for_load_state("networkidle")
            for act in actions:
                atype, sel = act[0], act[1]
                val = act[2] if len(act) > 2 else None
                if atype == "fill":
                    page.fill(sel, val or "")
                elif atype == "click":
                    page.click(sel)
                elif atype == "select":
                    page.select_option(sel, val)
                page.wait_for_timeout(200)
            page.wait_for_timeout(500)
        finally:
            context.tracing.stop(path=str(trace_zip))
            context.close()
            browser.close()

    console_log.write_text("\n".join(console_lines), encoding="utf-8")
    for f in [trace_zip, console_log, network_har]:
        assert f.exists() and f.stat().st_size > 0, f"产物缺失: {f}"
    return RecordingArtifact(trace_zip, console_log, network_har)
