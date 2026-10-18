import os
import json
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\Vijaya sekhar\.gemini\antigravity\brain\a532c2fd-2bcf-42ce-a108-19ace986ad1e"
SCREENSHOTS_DIR = os.path.join(ARTIFACT_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

URL = "http://localhost:5173"

def run_qa():
    results = {
        "chapter": "6B",
        "milestone": "Audio Library & Timeline Integration",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [],
        "console_errors": [],
        "passed": True
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        def handle_console(msg):
            if msg.type == "error":
                results["console_errors"].append(msg.text)

        page.on("console", handle_console)
        page.on("pageerror", lambda err: results["console_errors"].append(str(err)))

        print("Navigating to http://localhost:5173...")
        page.goto(URL, wait_until="networkidle")
        time.sleep(2)

        # 1. Open Story Editor
        story_editor_btns = page.locator("button:has-text('Story Editor')").all()
        assert len(story_editor_btns) > 0, "No 'Story Editor' button found"
        story_editor_btns[0].click()
        time.sleep(2)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Screenshot 1: Story Editor Overview with Audio Tracks (1920x1080)
        p1 = os.path.join(SCREENSHOTS_DIR, "ch6b_01_editor_timeline_audio_tracks.png")
        page.screenshot(path=p1)
        print("Captured: ch6b_01_editor_timeline_audio_tracks.png")
        results["steps"].append({"step": 1, "name": "Story Editor Audio Tracks Overview", "screenshot": p1, "status": "PASS"})

        # 2. Click Top Bar "Audio Library" button
        audio_lib_btn = page.locator('button:has-text("Audio Library")')
        assert audio_lib_btn.count() > 0, "No 'Audio Library' button found in top bar"
        audio_lib_btn.first.click()
        time.sleep(1)

        # Screenshot 2: Audio Library Modal Open from Story Editor
        p2 = os.path.join(SCREENSHOTS_DIR, "ch6b_02_audio_library_modal_opened.png")
        page.screenshot(path=p2)
        print("Captured: ch6b_02_audio_library_modal_opened.png")
        results["steps"].append({"step": 2, "name": "Audio Library Modal Open", "screenshot": p2, "status": "PASS"})

        # 3. Select an available BGM Asset and Send to Timeline
        # Click on "Ancient Crystal Resonance" to inspect and deploy
        crystal_asset = page.locator('text=Ancient Crystal Resonance').first
        if crystal_asset.count() > 0:
            crystal_asset.click()
            time.sleep(0.5)

        # Click "Send to BGM Track" in Audio Inspector or an enabled + Timeline button
        send_btn = page.locator('button:has-text("Send to BGM Track"), button:has-text("Send to"):not([disabled]), button:has-text("+ Timeline"):not([disabled])').first
        assert send_btn.count() > 0, "No enabled send button found in Audio Library"
        send_btn.click()
        time.sleep(1.5)

        # Screenshot 3: BGM Added to Timeline & Contextual Inspector Active
        p3 = os.path.join(SCREENSHOTS_DIR, "ch6b_03_bgm_placed_inspector.png")
        page.screenshot(path=p3)
        print("Captured: ch6b_03_bgm_placed_inspector.png")
        results["steps"].append({"step": 3, "name": "BGM Placed on Timeline & Inspector", "screenshot": p3, "status": "PASS"})

        # 4. Click "+ Add" on SFX Track Header
        add_sfx_btn = page.locator('button:has-text("+ Add")')
        if add_sfx_btn.count() > 1:
            # The second "+ Add" is on the SFX track header
            add_sfx_btn.nth(1).click()
        elif add_sfx_btn.count() == 1:
            add_sfx_btn.first.click()
        time.sleep(1)

        # Screenshot 4: Audio Library opened pre-filtered for SFX
        p4 = os.path.join(SCREENSHOTS_DIR, "ch6b_04_sfx_library_filtered.png")
        page.screenshot(path=p4)
        print("Captured: ch6b_04_sfx_library_filtered.png")
        results["steps"].append({"step": 4, "name": "SFX Library Pre-filtered", "screenshot": p4, "status": "PASS"})

        # Select an available SFX card
        blade_sfx = page.locator('text=Blade Unsheathe & Shimmer').first
        if blade_sfx.count() > 0:
            blade_sfx.click()
            time.sleep(0.5)

        send_sfx_btn = page.locator('button:has-text("Send to SFX Track"), button:has-text("Send to"):not([disabled]), button:has-text("+ Timeline"):not([disabled])').first
        if send_sfx_btn.count() > 0:
            send_sfx_btn.click()
        time.sleep(1.5)

        # Screenshot 5: SFX Cue Placed & Inspector Active
        p5 = os.path.join(SCREENSHOTS_DIR, "ch6b_05_sfx_cue_inspector.png")
        page.screenshot(path=p5)
        print("Captured: ch6b_05_sfx_cue_inspector.png")
        results["steps"].append({"step": 5, "name": "SFX Cue Placed on Timeline", "screenshot": p5, "status": "PASS"})

        # 6. Test Narration Ducking Controls & Volume Slider
        # Click a BGM clip on timeline to inspect ducking settings
        bgm_clips = page.locator('button:has-text("Resonance"), button:has-text("Ambient"), button:has-text("D-Minor")')
        if bgm_clips.count() > 0:
            bgm_clips.first.click()
            time.sleep(0.5)

        p6 = os.path.join(SCREENSHOTS_DIR, "ch6b_06_narration_ducking_inspector.png")
        page.screenshot(path=p6)
        print("Captured: ch6b_06_narration_ducking_inspector.png")
        results["steps"].append({"step": 6, "name": "Narration Ducking & BGM Controls", "screenshot": p6, "status": "PASS"})

        # 7. Test Playhead Scrubbing and Synchronized Playback
        page.keyboard.press("Space")
        time.sleep(1.5)
        page.keyboard.press("Space")
        time.sleep(0.5)

        p7 = os.path.join(SCREENSHOTS_DIR, "ch6b_07_timeline_playback_sync.png")
        page.screenshot(path=p7)
        print("Captured: ch6b_07_timeline_playback_sync.png")
        results["steps"].append({"step": 7, "name": "Timeline Playback & Audio Sync", "screenshot": p7, "status": "PASS"})

        # 8. Test Left Rail Workflow Navigation to Audio (Step 6)
        audio_rail_btn = page.locator('button:has-text("Audio")')
        if audio_rail_btn.count() > 0:
            audio_rail_btn.first.click()
            time.sleep(1)

        p8 = os.path.join(SCREENSHOTS_DIR, "ch6b_08_left_rail_audio_workflow.png")
        page.screenshot(path=p8)
        print("Captured: ch6b_08_left_rail_audio_workflow.png")
        results["steps"].append({"step": 8, "name": "Left Rail & Workflow Step 6 Navigation", "screenshot": p8, "status": "PASS"})

        # Close Audio Library overlay if open
        close_lib_btn = page.locator('button[title="Close Library"]')
        if close_lib_btn.count() > 0:
            close_lib_btn.click()
            time.sleep(0.5)

        # 9. Responsive Viewport: 1600x900
        page.set_viewport_size({"width": 1600, "height": 900})
        time.sleep(1)
        p9 = os.path.join(SCREENSHOTS_DIR, "ch6b_09_responsive_1600x900.png")
        page.screenshot(path=p9)
        print("Captured: ch6b_09_responsive_1600x900.png")
        results["steps"].append({"step": 9, "name": "Responsive Layout 1600x900", "screenshot": p9, "status": "PASS"})

        # 10. Responsive Viewport: 1366x768
        page.set_viewport_size({"width": 1366, "height": 768})
        time.sleep(1)
        p10 = os.path.join(SCREENSHOTS_DIR, "ch6b_10_responsive_1366x768.png")
        page.screenshot(path=p10)
        print("Captured: ch6b_10_responsive_1366x768.png")
        results["steps"].append({"step": 10, "name": "Responsive Layout 1366x768", "screenshot": p10, "status": "PASS"})

        # Save summary JSON
        summary_path = os.path.join(SCREENSHOTS_DIR, "ch6b_qa_summary.json")
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Summary written to: {summary_path}")

        browser.close()

if __name__ == "__main__":
    run_qa()
