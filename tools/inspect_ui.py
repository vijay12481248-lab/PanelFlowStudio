from playwright.sync_api import sync_playwright

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=EDGE_PATH, headless=True)
    page = browser.new_page()
    page.goto("http://localhost:5173")
    page.click("text=Lumina: Chapter 1")
    page.wait_for_timeout(500)
    page.locator("button:has-text('Motion')").first.click()
    page.wait_for_selector("text=Motion Director & Shot Planning")
    print("Buttons on Motion Screen:", [b.inner_text().strip() for b in page.query_selector_all("button")], flush=True)
    browser.close()
