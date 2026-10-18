"""
Capture high-resolution screenshots of the PanelFlow Studio Narration Studio (Chapter 5A)
using Playwright against the isolated Vite preview harness.
"""

import os
import sys
import time
import subprocess
import urllib.request
from playwright.sync_api import sync_playwright

OUTPUT_DIR = os.path.abspath("docs/screenshots/narration-studio")
PREVIEW_URL = "http://localhost:5173/preview-narration.html"

def wait_for_server(url, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    server_process = None

    # Check if server is already running
    if not wait_for_server(PREVIEW_URL, timeout=1):
        print(f"Starting Vite dev server on port 5173...")
        desktop_dir = os.path.abspath("apps/desktop")
        server_process = subprocess.Popen(
            ["npx.cmd", "vite", "--port", "5173", "--strictPort"],
            cwd=desktop_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if not wait_for_server(PREVIEW_URL, timeout=15):
            print("Failed to start Vite dev server!")
            if server_process:
                server_process.kill()
            sys.exit(1)
        print("Vite dev server is ready.")
    else:
        print("Vite dev server is already running.")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 960})
            
            print(f"Navigating to {PREVIEW_URL}...")
            page.goto(PREVIEW_URL, wait_until="networkidle")
            page.wait_for_timeout(1000)

            # 1. Main 3-Column Workspace Screenshot
            path1 = os.path.join(OUTPUT_DIR, "01_three_column_workspace.png")
            page.screenshot(path=path1)
            print(f"Saved: {path1}")

            # 2. Quality Review Matrix Screenshot
            print("Switching to Quality Matrix...")
            matrix_btn = page.locator("button:has-text('Quality Matrix')")
            if matrix_btn.count() > 0:
                matrix_btn.first.click()
                page.wait_for_timeout(500)
                path2 = os.path.join(OUTPUT_DIR, "02_quality_review_matrix.png")
                page.screenshot(path=path2)
                print(f"Saved: {path2}")

            # 3. Character Voice Manager Modal Screenshot
            print("Opening Character Voice Casting...")
            casting_btn = page.locator("button:has-text('Character Casting')")
            if casting_btn.count() > 0:
                casting_btn.first.click()
                page.wait_for_timeout(500)
                path3 = os.path.join(OUTPUT_DIR, "03_character_voice_manager.png")
                page.screenshot(path=path3)
                print(f"Saved: {path3}")
                # Close modal
                page.locator("button:has-text('✕')").first.click()
                page.wait_for_timeout(300)

            # 4. Advanced Directing Controls Screenshot
            print("Expanding Advanced Directing...")
            adv_btn = page.locator("button:has-text('Show Advanced Directing')")
            if adv_btn.count() > 0:
                adv_btn.first.click()
                page.wait_for_timeout(400)
                path4 = os.path.join(OUTPUT_DIR, "04_advanced_directing_controls.png")
                page.screenshot(path=path4)
                print(f"Saved: {path4}")

            # 5. Simulated Job Queue Screenshot (Click Segment 5 and Regenerate Audio)
            print("Testing Simulated Job Queue on Outdated Segment...")
            # Click segment 5 in the left story panel
            seg5 = page.locator("div[role='button']:has-text('#5')").first
            if seg5.count() > 0:
                seg5.click()
                page.wait_for_timeout(400)
            
            # Click "View Chapter Queue" to expand queue
            chapter_queue_btn = page.locator("button:has-text('View Chapter Queue')")
            if chapter_queue_btn.count() > 0:
                chapter_queue_btn.first.click()
                page.wait_for_timeout(300)

            # Click Regenerate or Queue Generation button
            action_btn = page.locator("button:has-text('Regenerate Audio'), button:has-text('Queue Generation')").first
            if action_btn.count() > 0:
                action_btn.click()
                page.wait_for_timeout(800) # Capture during processing/progress
            
            path5 = os.path.join(OUTPUT_DIR, "05_simulated_job_queue.png")
            page.screenshot(path=path5)
            print(f"Saved: {path5}")

            # 6. Timeline Contract Export Modal Screenshot
            print("Opening Timeline Contract Export...")
            export_btn = page.locator("button:has-text('Export Contract')")
            if export_btn.count() > 0:
                export_btn.first.click()
                page.wait_for_timeout(500)
                path6 = os.path.join(OUTPUT_DIR, "06_timeline_contract_export.png")
                page.screenshot(path=path6)
                print(f"Saved: {path6}")

            browser.close()
            print("Screenshot capture complete!")

    finally:
        if server_process:
            print("Stopping Vite dev server...")
            server_process.kill()

if __name__ == "__main__":
    main()
