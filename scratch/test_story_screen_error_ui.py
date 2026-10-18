import os
import time
from playwright.sync_api import sync_playwright

output_dir = r"C:\Users\Vijaya sekhar\.gemini\antigravity\brain\a532c2fd-2bcf-42ce-a108-19ace986ad1e\screenshots"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="msedge")
    page = browser.new_page(viewport={"width": 1366, "height": 768})

    page.goto("http://localhost:5173", wait_until="networkidle")
    time.sleep(2)

    # Click on the first project's OCR or Story button to enter the pipeline
    story_or_ocr = page.locator("button:has-text('OCR')").first
    if story_or_ocr.is_visible():
        story_or_ocr.click()
        time.sleep(2)
        # Navigate to story tab if pipeline navbar is visible
        story_nav = page.locator("button:has-text('Story')").first
        if story_nav.is_visible():
            story_nav.click()
            time.sleep(1)

        page.screenshot(path=os.path.join(output_dir, "story_review_screen.png"))
        print("Captured story_review_screen.png")

    browser.close()
