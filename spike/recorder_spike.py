"""Task 0.2 Spike: Playwright 录制 + Trace + Bug1 复现验证
闸门1(操作采集) + 闸门4(Bug复现) + 闸门5(证据输出 trace.zip)
前提：demo_project 已 npm run dev 在 http://localhost:5173
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "out"
OUT.mkdir(exist_ok=True)
URL = "http://localhost:5173"


def main():
    events = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

        page.goto(URL)
        page.wait_for_selector("[data-testid=total-price]")
        events.append(("goto", "loaded"))

        page.fill("[data-testid=coupon-input]", "SALE20")
        events.append(("fill", "coupon=SALE20"))
        page.click("[data-testid=apply-btn]")
        events.append(("click", "apply-btn"))
        total_after_apply = page.text_content("[data-testid=total-price]")

        page.fill("[data-testid=qty-input]", "2")
        events.append(("fill", "qty=2"))
        page.wait_for_timeout(400)
        total_after_qty = page.text_content("[data-testid=total-price]")

        context.tracing.stop(path=str(OUT / "trace.zip"))
        browser.close()

    print("=== 闸门1: 操作采集 ===")
    for t, d in events:
        print(f"  {t}: {d}")
    zip_path = OUT / "trace.zip"
    print(f"  trace.zip: exists={zip_path.exists()} size={zip_path.stat().st_size if zip_path.exists() else 0}B")

    print("=== 闸门4: Bug1 复现 ===")
    print(f"  apply后总价={total_after_apply}, 改数量2后总价={total_after_qty}")
    reproduced = (total_after_apply == total_after_qty)
    print(f"  BUG1_REPRODUCED={reproduced} (改数量后总价应变而未变)")


if __name__ == "__main__":
    main()
