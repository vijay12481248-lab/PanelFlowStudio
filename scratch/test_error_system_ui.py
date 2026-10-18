import os
import time
from playwright.sync_api import sync_playwright

output_dir = r"C:\Users\Vijaya sekhar\.gemini\antigravity\brain\a532c2fd-2bcf-42ce-a108-19ace986ad1e\screenshots"
os.makedirs(output_dir, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1366, "height": 768})

    print("Navigating to http://localhost:5173...")
    page.goto("http://localhost:5173", wait_until="networkidle")
    time.sleep(2)

    page.screenshot(path=os.path.join(output_dir, "dashboard_with_error_bell.png"))
    print("Captured dashboard_with_error_bell.png")

    # Dispatch unhandled rejection event to verify automatic error reporting & alert toast
    page.evaluate("""() => {
        const ev = new Event("unhandledrejection");
        ev.reason = new Error("Unsupported speech provider: f5_tts. Use 'chatterbox_turbo' (MIT).");
        window.dispatchEvent(ev);
    }""")
    time.sleep(1)

    page.screenshot(path=os.path.join(output_dir, "error_alert_toast.png"))
    print("Captured error_alert_toast.png")

    # Locate and click 'View Error Details' button
    view_btn = page.locator("button:has-text('View Error Details')").first
    if view_btn.is_visible():
        print("Clicking View Error Details button...")
        view_btn.click()
        time.sleep(1)
        page.screenshot(path=os.path.join(output_dir, "error_details_modal.png"))
        print("Captured error_details_modal.png")

        # Click 'Copy Error Details' button to test copy action
        copy_btn = page.locator("button:has-text('Copy Error Details')").first
        if copy_btn.is_visible():
            copy_btn.click()
            time.sleep(0.5)
            page.screenshot(path=os.path.join(output_dir, "error_modal_copied.png"))
            print("Captured error_modal_copied.png")

        # Close modal
        close_btn = page.locator("button:has-text('Close')").first
        if close_btn.is_visible():
            close_btn.click()
            time.sleep(0.5)

    # Now click the Error Notification Bell to inspect the popover
    bell_btn = page.locator("button[title*='active error alert'], button[title*='System Alerts']").first
    if bell_btn.is_visible():
        print("Clicking Error Notification Bell...")
        bell_btn.click()
        time.sleep(1)
        page.screenshot(path=os.path.join(output_dir, "error_bell_history_popover.png"))
        print("Captured error_bell_history_popover.png")

    browser.close()
    print("All UI screenshots captured successfully!")
