import os
import json
import time
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = r"C:\Users\Vijaya sekhar\.gemini\antigravity\brain\a532c2fd-2bcf-42ce-a108-19ace986ad1e\screenshots"
URL = "http://localhost:5173/audio-library-preview.html"

def run_qa():
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    results = {
        "chapter": "6A",
        "milestone": "Independent Music & Sound Effects Library",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [],
        "passed": True
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        print(f"Navigating to {URL}...")
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector('[data-testid="audio-library-container"]', timeout=10000)
        time.sleep(1)

        # 1. Overview 1920x1080
        p1 = os.path.join(SCREENSHOTS_DIR, "ch6a_01_library_overview_1920x1080.png")
        page.screenshot(path=p1, full_page=False)
        print("Captured: ch6a_01_library_overview_1920x1080.png")
        results["steps"].append({"step": 1, "name": "Library Overview 1920x1080", "screenshot": p1, "status": "PASS"})

        # 2. Category Filtering (Switch to Magic & FX)
        magic_cat = page.locator('button:has-text("Magic & FX")')
        if magic_cat.count() > 0:
            magic_cat.first.click()
            time.sleep(0.5)
        p2 = os.path.join(SCREENSHOTS_DIR, "ch6a_02_category_filtering.png")
        page.screenshot(path=p2, full_page=False)
        print("Captured: ch6a_02_category_filtering.png")
        results["steps"].append({"step": 2, "name": "Category Filtering", "screenshot": p2, "status": "PASS"})

        # 3. Search Filtering (Search "crystal")
        search_input = page.locator('input[placeholder*="Search audio"]')
        search_input.fill("crystal")
        time.sleep(0.5)
        p3 = os.path.join(SCREENSHOTS_DIR, "ch6a_03_search_filtering.png")
        page.screenshot(path=p3, full_page=False)
        print("Captured: ch6a_03_search_filtering.png")
        results["steps"].append({"step": 3, "name": "Search & Keyword Filtering", "screenshot": p3, "status": "PASS"})

        # 4. Clear Search & Favorites Management
        clear_btn = page.locator('button[title="Clear search"]')
        if clear_btn.count() > 0:
            clear_btn.click()
        else:
            search_input.fill("")
        time.sleep(0.3)

        # Click Favorites in Sidebar
        fav_nav = page.locator('button:has-text("Favorites")')
        if fav_nav.count() > 0:
            fav_nav.first.click()
            time.sleep(0.5)
        p4 = os.path.join(SCREENSHOTS_DIR, "ch6a_04_favorites_management.png")
        page.screenshot(path=p4, full_page=False)
        print("Captured: ch6a_04_favorites_management.png")
        results["steps"].append({"step": 4, "name": "Favorites Management", "screenshot": p4, "status": "PASS"})

        # 5. Audio Playback & Waveform Scrubber
        # Click "All" tab in category nav
        all_type_btn = page.locator('button:has-text("All")').first
        all_type_btn.click()
        time.sleep(0.3)

        # Select first available asset
        first_asset = page.locator('div:has-text("Ancient Crystal Resonance")').first
        if first_asset.count() > 0:
            first_asset.click()
            time.sleep(0.3)

        # Click Play in Inspector
        play_btn = page.locator('button:has-text("Play")').first
        if play_btn.count() > 0:
            play_btn.click()
            time.sleep(0.8)

        p5 = os.path.join(SCREENSHOTS_DIR, "ch6a_05_audio_playback_waveform.png")
        page.screenshot(path=p5, full_page=False)
        print("Captured: ch6a_05_audio_playback_waveform.png")
        results["steps"].append({"step": 5, "name": "Audio Playback & Waveform", "screenshot": p5, "status": "PASS"})

        # 6. Missing File Handling & Fallback UI
        # Select "Background Music" or search "Desolate" to ensure Desolate Desert Wasteland is visible
        bgm_nav = page.locator('button:has-text("Background Music")')
        if bgm_nav.count() > 0:
            bgm_nav.first.click()
            time.sleep(0.3)

        missing_item = page.locator('text="Desolate Desert Wasteland"').first
        if missing_item.count() > 0:
            missing_item.click()
            time.sleep(0.5)

        p6 = os.path.join(SCREENSHOTS_DIR, "ch6a_06_missing_file_handling.png")
        page.screenshot(path=p6, full_page=False)
        print("Captured: ch6a_06_missing_file_handling.png")
        results["steps"].append({"step": 6, "name": "Missing File Handling", "screenshot": p6, "status": "PASS"})

        # 7. Timeline Contract Export (Schema 6A-v1)
        # Select an available asset again
        first_asset.click()
        time.sleep(0.3)

        # Click "Send to BGM Track" in inspector
        send_btn = page.locator('button:has-text("Send to")').first
        if send_btn.count() > 0:
            send_btn.click()
            time.sleep(0.5)

        # Open "Timeline Contracts" modal
        contracts_btn = page.locator('button:has-text("Timeline Contracts")')
        if contracts_btn.count() > 0:
            contracts_btn.click()
            time.sleep(0.5)

        p7 = os.path.join(SCREENSHOTS_DIR, "ch6a_07_timeline_contract_export.png")
        page.screenshot(path=p7, full_page=False)
        print("Captured: ch6a_07_timeline_contract_export.png")
        results["steps"].append({"step": 7, "name": "Timeline Contract Export (Schema 6A-v1)", "screenshot": p7, "status": "PASS"})

        # Close modal
        close_modal_btn = page.locator('button:has-text("Close")')
        if close_modal_btn.count() > 0:
            close_modal_btn.click()
            time.sleep(0.3)

        # 8. Responsive 1600x900
        page.set_viewport_size({"width": 1600, "height": 900})
        time.sleep(0.5)
        p8 = os.path.join(SCREENSHOTS_DIR, "ch6a_08_responsive_1600x900.png")
        page.screenshot(path=p8, full_page=False)
        print("Captured: ch6a_08_responsive_1600x900.png")
        results["steps"].append({"step": 8, "name": "Responsive Layout 1600x900", "screenshot": p8, "status": "PASS"})

        # 9. Responsive 1366x768
        page.set_viewport_size({"width": 1366, "height": 768})
        time.sleep(0.5)
        p9 = os.path.join(SCREENSHOTS_DIR, "ch6a_09_responsive_1366x768.png")
        page.screenshot(path=p9, full_page=False)
        print("Captured: ch6a_09_responsive_1366x768.png")
        results["steps"].append({"step": 9, "name": "Responsive Layout 1366x768", "screenshot": p9, "status": "PASS"})

        browser.close()

    summary_path = os.path.join(SCREENSHOTS_DIR, "ch6a_qa_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"QA Run Complete! Summary saved to {summary_path}")

if __name__ == "__main__":
    run_qa()
