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


# 注入到被测页面的 JS：监听用户 click/change（fill），记到 window.__actions；
# 并在右上角挂一个「✓ 完成录制」按钮，用户点它把 window.__done 置 true（循环据此退出）。
_INJECT_JS = """
window.__actions = [];
window.__t0 = Date.now();
window.__done = false;
function __rf_record(type, el) {
  var testid = (el.dataset && el.dataset.testid) ? el.dataset.testid
               : (el.id || el.getAttribute('name') || el.getAttribute('placeholder') || '');
  var value = (el.value !== undefined && el.value !== '') ? el.value : '';
  window.__actions.push({type: type, target: testid, value: value,
                         timestamp: (Date.now() - window.__t0) / 1000, text: testid});
}
document.addEventListener('click', function(e){ if(e.target && e.target.id !== '__rf_done') __rf_record('click', e.target); }, true);
document.addEventListener('change', function(e){ __rf_record('fill', e.target); }, true);
var __rf_btn = document.createElement('button');
__rf_btn.id = '__rf_done';
__rf_btn.textContent = '完成录制';
__rf_btn.style.cssText = 'position:fixed;top:12px;right:12px;z-index:99999;background:#10b981;color:#fff;padding:9px 18px;border:0;border-radius:9px;font-size:14px;font-weight:700;cursor:pointer;box-shadow:0 3px 10px rgba(0,0,0,.25);';
__rf_btn.onclick = function(){ window.__done = true; __rf_btn.textContent='已结束，可关闭'; __rf_btn.disabled=true; };
function __rf_mount(){ if(document.body && !document.getElementById('__rf_done')) document.body.appendChild(__rf_btn); }
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', __rf_mount);
else __rf_mount();
"""


def record_user_session(url, timeout=90):
    """真实操作采集：启动 headed 浏览器 → 注入 JS 监听用户 click/fill → actions 列表。

    用户在浏览器操作商城（点/填），JS 把每步操作（含 data-testid）记到 window.__actions。
    用户操作完点页面右上角「完成录制」按钮（或超时自动结束），取出 actions。
    替代预填 JSON，让 demo 真实"边操作边采集"。
    返回 [{type, target, value, timestamp, text}, ...]（与 run_pipeline 期望的 actions 同构）。
    """
    import time
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.add_init_script(_INJECT_JS)
        page.goto(url)
        start = time.time()
        while (time.time() - start) < timeout:
            try:
                if page.evaluate("window.__done === true"):
                    break
            except Exception:
                break  # 页面被关掉
            page.wait_for_timeout(500)
        try:
            actions = page.evaluate("window.__actions || []")
        except Exception:
            actions = []
        browser.close()
    return actions
