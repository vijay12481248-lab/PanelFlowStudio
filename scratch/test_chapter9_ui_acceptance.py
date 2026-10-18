import os
import sys
import json
import time
from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ARTIFACT_DIR = r"C:\Users\Vijaya sekhar\.gemini\antigravity\brain\a532c2fd-2bcf-42ce-a108-19ace986ad1e"
SCREENSHOTS_DIR = os.path.join(ARTIFACT_DIR, "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

URL = "http://localhost:5173"
PROJECT_ID = "68711176-90f5-4a68-8520-78d6e183bf65"

def run_ui_acceptance():
    print("=================================================================")
    print(" PANELFLOW STUDIO — CHAPTER 9 AI MUSIC STUDIO UI ACCEPTANCE")
    print("=================================================================")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        viewports = [
            ("1920x1080", 1920, 1080, "ch9_ui_01_music_studio_1920x1080.png"),
            ("1600x900", 1600, 900, "ch9_ui_02_music_studio_1600x900.png"),
            ("1366x768", 1366, 768, "ch9_ui_03_music_studio_1366x768.png"),
        ]

        for vp_name, width, height, filename in viewports:
            print(f"\nTesting Viewport: {vp_name} ({width}x{height})...")
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()

            console_errors = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            page.goto(URL, wait_until="networkidle")
            time.sleep(2)

            # Ensure we are on the Story Editor
            story_editor_btn = page.locator("button:has-text('Story Editor')").first
            if story_editor_btn.count() > 0:
                story_editor_btn.click()
                time.sleep(2)
                page.wait_for_load_state("networkidle")

            # Open Audio Library / AI Music Studio
            # Check for "Audio" button in nav or toolbar
            audio_btn = page.locator("button:has-text('Audio')").first
            if audio_btn.count() > 0:
                audio_btn.click()
                time.sleep(1.5)

            # Switch to Story-Aware AI Music tab
            ai_music_tab = page.locator("button:has-text('Story-Aware AI Music')").first
            if ai_music_tab.count() > 0:
                ai_music_tab.click()
                time.sleep(1.5)
                print("Switched to '✨ Story-Aware AI Music' workspace tab.")

            # Capture viewport screenshot
            out_p = os.path.join(SCREENSHOTS_DIR, filename)
            page.screenshot(path=out_p)
            print(f"Captured: {filename}")

            if vp_name == "1920x1080":
                # Test interaction: select Cue 2 (Rising Tension)
                cue2 = page.locator("text=Rising Tension").first
                if cue2.count() > 0:
                    cue2.click()
                    time.sleep(1)
                    p_cue = os.path.join(SCREENSHOTS_DIR, "ch9_ui_04_cue_selection_and_prompt.png")
                    page.screenshot(path=p_cue)
                    print("Captured: ch9_ui_04_cue_selection_and_prompt.png")

                # Audition candidate take (Take 1 of Cue 1 or Cue 2)
                play_btn = page.locator("button:has-text('▶')").first
                if play_btn.count() > 0:
                    play_btn.click()
                    time.sleep(1)
                    p_takes = os.path.join(SCREENSHOTS_DIR, "ch9_ui_05_candidate_takes_audition.png")
                    page.screenshot(path=p_takes)
                    print("Captured: ch9_ui_05_candidate_takes_audition.png")

            context.close()

        browser.close()
        print("\nUI Acceptance QA Complete. All screenshots saved.")

if __name__ == "__main__":
    run_ui_acceptance()
