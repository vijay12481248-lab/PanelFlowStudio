import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        headless=True
    )
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto('http://localhost:5173')
    page.wait_for_selector('text=PanelFlow Studio', timeout=10000)
    time.sleep(2)

    # Dismiss any old system alerts if visible
    dismiss_all = page.locator("button:has-text('Dismiss All'), span:has-text('Dismiss All')")
    if dismiss_all.count() > 0 and dismiss_all.first.is_visible():
        dismiss_all.first.click()
        time.sleep(1)

    # Click project card
    cards = page.locator("h3:has-text('Magic Emperor'), h3:has-text('Demon Magic Emperor')").all()
    if cards:
        cards[0].click()
    
    # Wait for Production Renderer
    page.wait_for_selector('text=Production Renderer', timeout=10000)
    time.sleep(3)

    # Check if Dismiss All is still visible and click it to clear notifications from view
    dismiss_all = page.locator("button:has-text('Dismiss All'), span:has-text('Dismiss All')")
    if dismiss_all.count() > 0 and dismiss_all.first.is_visible():
        dismiss_all.first.click()
        time.sleep(1)

    out_path = r'C:\Users\Vijaya sekhar\.gemini\antigravity\brain\63f8b524-24e2-4543-9fca-92aa1e44252e\final_render_ui_fixed.png'
    page.screenshot(path=out_path)
    print("Screenshot saved to:", out_path)
    
    browser.close()
