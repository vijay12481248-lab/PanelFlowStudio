import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
TARGET_URL = "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-923/"
OUT_DIR = Path("output/demon_cycle")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run():
    print("=" * 70, flush=True)
    print("PANELFLOW STUDIO — AUTONOMOUS PIPELINE DISPATCHER", flush=True)
    print(f"Target URL: {TARGET_URL}", flush=True)
    print("=" * 70, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=EDGE_PATH,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: print(f"[BROWSER {msg.type}] {msg.text}", flush=True))
        page.on("pageerror", lambda err: print(f"[BROWSER ERROR] {err}", flush=True))
        page.on("dialog", lambda d: (print(f"[DIALOG] {d.message}", flush=True), d.accept()))

        print("\nNavigating to PanelFlow Studio UI...", flush=True)
        page.goto("http://localhost:5173", timeout=15000)
        page.wait_for_selector("text=PanelFlow Studio", timeout=10000)
        time.sleep(1)

        start_time = time.time()
        max_duration = 3600  # 60 minutes max for full end-to-end cycle
        last_state = ""

        while time.time() - start_time < max_duration:
            time.sleep(2)
            h1s = " ".join(page.locator("h1").all_inner_texts())
            h2s = " ".join(page.locator("h2").all_inner_texts())
            headings = f"{h1s} {h2s}"
            content = page.content()

            # -------------------------------------------------------------
            # Stage: Production Renderer
            # -------------------------------------------------------------
            if "Production Renderer" in headings:
                if last_state != "Render":
                    print("\n[State: RenderScreen] On Production Renderer Screen...", flush=True)
                    last_state = "Render"
                page.screenshot(path=str(OUT_DIR / "stage_render.png"))

                # Check for success
                if page.locator("text=RENDER VERIFIED").count() > 0 or (page.locator("video").count() > 0 and page.locator("video").first.is_visible()):
                    print("\n" + "=" * 70, flush=True)
                    print("RENDER COMPLETE! VIDEO GENERATED SUCCESSFULLY!", flush=True)
                    print("=" * 70, flush=True)
                    time.sleep(2)
                    page.screenshot(path=str(OUT_DIR / "final_render_success.png"))
                    break

                # Check if currently rendering
                cancel_btn = page.locator("button:has-text('Cancel Render')")
                if cancel_btn.count() > 0 and cancel_btn.first.is_visible():
                    frames_el = page.locator("div.font-mono:has-text('frames')")
                    if frames_el.count() > 0:
                        print(f"  Rendering in progress: {frames_el.first.inner_text()}", flush=True)
                    time.sleep(8)
                    continue

                error_box = page.locator("div.bg-red-950, div.text-red-400")
                if error_box.count() > 0 and error_box.first.is_visible():
                    err_txt = error_box.first.inner_text().strip()
                    if err_txt:
                        print(f"  [RENDER NOTICE/ERROR]: {err_txt}", flush=True)

                start_render_btn = page.locator("button:has-text('Start Render')")
                if start_render_btn.count() > 0 and start_render_btn.first.is_visible() and not start_render_btn.first.is_disabled():
                    print("  Triggering 'Start Render'...", flush=True)
                    start_render_btn.first.click()
                time.sleep(4)
                continue

            # -------------------------------------------------------------
            # Stage: Motion Director & Shot Planning
            # -------------------------------------------------------------
            elif "Motion Director & Shot Planning" in headings:
                if last_state != "Motion":
                    print("\n[State: MotionScreen] On Motion Screen...", flush=True)
                    last_state = "Motion"
                page.screenshot(path=str(OUT_DIR / "stage_motion.png"))

                proceed_render = page.locator("button:has-text('Proceed to Render')")
                if proceed_render.count() > 0 and proceed_render.first.is_visible():
                    print("  Clicking 'Proceed to Render'...", flush=True)
                    proceed_render.first.click()
                    time.sleep(2)
                    continue

                appr_motion = page.locator("button:has-text('Approve Motion')")
                if appr_motion.count() > 0 and appr_motion.first.is_visible() and not appr_motion.first.is_disabled():
                    print("  Clicking 'Approve Motion'...", flush=True)
                    appr_motion.first.click()
                    time.sleep(2)
                    continue

                plan_btn = page.locator("button:has-text('Plan Shots'), button:has-text('Re-Plan Motion')")
                if plan_btn.count() > 0 and plan_btn.first.is_visible() and not plan_btn.first.is_disabled():
                    print(f"  Clicking '{plan_btn.first.inner_text()}'...", flush=True)
                    plan_btn.first.click()
                time.sleep(3)
                continue

            # -------------------------------------------------------------
            # Stage: Audio Director & Voice Review
            # -------------------------------------------------------------
            elif "Audio Director & Voice Review" in headings:
                if last_state != "Audio":
                    print("\n[State: AudioScreen] On Audio Screen...", flush=True)
                    last_state = "Audio"
                page.screenshot(path=str(OUT_DIR / "stage_audio.png"))

                proceed_motion = page.locator("button:has-text('Proceed to Motion')")
                if proceed_motion.count() > 0 and proceed_motion.first.is_visible():
                    print("  Clicking 'Proceed to Motion'...", flush=True)
                    proceed_motion.first.click()
                    time.sleep(2)
                    continue

                appr_audio = page.locator("button:has-text('Approve Audio')")
                if appr_audio.count() > 0 and appr_audio.first.is_visible() and not appr_audio.first.is_disabled():
                    print("  Clicking 'Approve Audio'...", flush=True)
                    appr_audio.first.click()
                    time.sleep(2)
                    continue

                gen_audio = page.locator("button:has-text('Generate Master Audio'), button:has-text('Regenerate All Audio')")
                if gen_audio.count() > 0 and gen_audio.first.is_visible() and not gen_audio.first.is_disabled():
                    print(f"  Clicking '{gen_audio.first.inner_text()}'...", flush=True)
                    gen_audio.first.click()
                time.sleep(3)
                continue

            # -------------------------------------------------------------
            # Stage: Video Script Adaptation & Review
            # -------------------------------------------------------------
            elif "Video Script Adaptation & Review" in headings:
                if last_state != "Script":
                    print("\n[State: ScriptScreen] On Script Review Screen...", flush=True)
                    last_state = "Script"
                page.screenshot(path=str(OUT_DIR / "stage_script.png"))

                proceed_audio = page.locator("button:has-text('Proceed to Audio')")
                if proceed_audio.count() > 0 and proceed_audio.first.is_visible():
                    print("  Clicking 'Proceed to Audio'...", flush=True)
                    proceed_audio.first.click()
                    time.sleep(2)
                    continue

                appr_script = page.locator("button:has-text('Approve Script')")
                if appr_script.count() > 0 and appr_script.first.is_visible() and not appr_script.first.is_disabled():
                    print("  Clicking 'Approve Script'...", flush=True)
                    appr_script.first.click()
                    time.sleep(2)
                    continue

                gen_script = page.locator("button:has-text('Generate Script'), button:has-text('Re-Adapt Script')")
                if gen_script.count() > 0 and gen_script.first.is_visible() and not gen_script.first.is_disabled():
                    print(f"  Clicking '{gen_script.first.inner_text()}'...", flush=True)
                    gen_script.first.click()
                time.sleep(3)
                continue

            # -------------------------------------------------------------
            # Stage: Story Understanding & Narrative IR
            # -------------------------------------------------------------
            elif "Story Understanding & Narrative IR" in headings:
                if last_state != "Story":
                    print("\n[State: StoryScreen] On Story Review Screen...", flush=True)
                    last_state = "Story"
                page.screenshot(path=str(OUT_DIR / "stage_story.png"))

                proceed_script = page.locator("button:has-text('Proceed to Script')")
                if proceed_script.count() > 0 and proceed_script.first.is_visible():
                    print("  Clicking 'Proceed to Script'...", flush=True)
                    proceed_script.first.click()
                    time.sleep(2)
                    continue

                appr_story = page.locator("button:has-text('Approve Narrative IR')")
                if appr_story.count() > 0 and appr_story.first.is_visible() and not appr_story.first.is_disabled():
                    print("  Clicking 'Approve Narrative IR'...", flush=True)
                    appr_story.first.click()
                    time.sleep(2)
                    continue

                run_story = page.locator("button:has-text('Run Story Analysis'), button:has-text('Re-Analyze Story')")
                if run_story.count() > 0 and run_story.first.is_visible() and not run_story.first.is_disabled():
                    print(f"  Clicking '{run_story.first.inner_text()}'...", flush=True)
                    run_story.first.click()
                time.sleep(3)
                continue

            # -------------------------------------------------------------
            # Stage: Text Region Detection & OCR Review
            # -------------------------------------------------------------
            elif "Text Region Detection & OCR Review" in headings:
                if last_state != "OCR":
                    print("\n[State: OCRScreen] On OCR Review Screen...", flush=True)
                    last_state = "OCR"
                page.screenshot(path=str(OUT_DIR / "stage_ocr.png"))

                proceed_story = page.locator("button:has-text('Proceed to Story')")
                if proceed_story.count() > 0 and proceed_story.first.is_visible():
                    print("  Clicking 'Proceed to Story'...", flush=True)
                    proceed_story.first.click()
                    time.sleep(2)
                    continue

                confirm_all = page.locator("button:has-text('Confirm All')")
                if confirm_all.count() > 0 and confirm_all.first.is_visible() and not confirm_all.first.is_disabled():
                    print(f"  Clicking '{confirm_all.first.inner_text()}'...", flush=True)
                    confirm_all.first.click()
                    time.sleep(2)

                appr_ocr = page.locator("button:has-text('Approve OCR')")
                if appr_ocr.count() > 0 and appr_ocr.first.is_visible() and not appr_ocr.first.is_disabled():
                    print(f"  Clicking '{appr_ocr.first.inner_text()}'...", flush=True)
                    appr_ocr.first.click()
                    time.sleep(2)
                    continue

                detect_bubbles = page.locator("button:has-text('Detect Bubbles')")
                if detect_bubbles.count() > 0 and detect_bubbles.first.is_visible() and not detect_bubbles.first.is_disabled():
                    print("  Clicking 'Detect Bubbles'...", flush=True)
                    detect_bubbles.first.click()
                    time.sleep(3)
                    continue

                ocr_all = page.locator("button:has-text('OCR All Panels')")
                if ocr_all.count() > 0 and ocr_all.first.is_visible() and not ocr_all.first.is_disabled():
                    print("  Clicking 'OCR All Panels'...", flush=True)
                    ocr_all.first.click()
                time.sleep(3)
                continue

            # -------------------------------------------------------------
            # Stage: Panel Review & Sequence Studio
            # -------------------------------------------------------------
            elif "Panel Review & Sequence Studio" in headings:
                if last_state != "Panels":
                    print("\n[State: PanelScreen] On Panel Review Screen...", flush=True)
                    last_state = "Panels"
                page.screenshot(path=str(OUT_DIR / "stage_panels.png"))

                proceed_ocr = page.locator("button:has-text('Proceed to OCR')")
                if proceed_ocr.count() > 0 and proceed_ocr.first.is_visible():
                    print("  Clicking 'Proceed to OCR'...", flush=True)
                    proceed_ocr.first.click()
                    time.sleep(2)
                    continue

                appr_panels = page.locator("button:has-text('Approve Panels')")
                if appr_panels.count() > 0 and appr_panels.first.is_visible() and "(0)" not in appr_panels.first.inner_text() and not appr_panels.first.is_disabled():
                    print(f"  Clicking '{appr_panels.first.inner_text()}'...", flush=True)
                    appr_panels.first.click()
                    time.sleep(2)
                    continue

                auto_detect = page.locator("button:has-text('Auto-Detect All')")
                if auto_detect.count() > 0 and auto_detect.first.is_visible() and not auto_detect.first.is_disabled():
                    print("  Clicking 'Auto-Detect All'...", flush=True)
                    auto_detect.first.click()
                time.sleep(3)
                continue

            # -------------------------------------------------------------
            # Stage: Page Review
            # -------------------------------------------------------------
            elif "Confirm Acquisition" in content or "Page Review" in headings:
                if last_state != "PageReview":
                    print("\n[State: PageReview] On Page Review Screen...", flush=True)
                    last_state = "PageReview"
                confirm_btn = page.locator("button:has-text('Confirm Acquisition')")
                if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                    print("  Clicking 'Confirm Acquisition'...", flush=True)
                    confirm_btn.first.click()
                time.sleep(2)
                continue

            # -------------------------------------------------------------
            # Stage: Acquisition Pipeline
            # -------------------------------------------------------------
            elif "Acquisition Pipeline" in content:
                if last_state != "Acquisition":
                    print("\n[State: Acquisition] On Acquisition Screen...", flush=True)
                    last_state = "Acquisition"
                review_btn = page.locator("button:has-text('Review Pages'), button:has-text('Proceed to Page Review')")
                if review_btn.count() > 0 and review_btn.first.is_visible():
                    print("  Clicking 'Review Pages'...", flush=True)
                    review_btn.first.click()
                    time.sleep(2)
                    continue

                start_acq = page.locator("button:has-text('Start Acquisition')")
                if start_acq.count() > 0 and start_acq.first.is_visible() and not start_acq.first.is_disabled():
                    print("  Clicking 'Start Acquisition'...", flush=True)
                    start_acq.first.click()
                time.sleep(3)
                continue

            # -------------------------------------------------------------
            # Stage: Projects List (Home)
            # -------------------------------------------------------------
            else:
                existing_proj = page.locator("h3:has-text('Magic Emperor'), h3:has-text('Demon Magic Emperor')")
                if existing_proj.count() > 0:
                    if last_state != "Home":
                        print("[State: Home] Found existing project. Opening...", flush=True)
                        last_state = "Home"
                    existing_proj.first.click()
                    time.sleep(2)
                    continue

                print("[State: Home] Creating New Project...", flush=True)
                page.locator("button:has-text('New Project')").first.click()
                page.wait_for_selector("text=Create New Project", timeout=10000)
                page.locator("button:has-text('Authorized URL')").click()
                page.locator("input[placeholder*='https://']").fill(TARGET_URL)
                page.locator("button:has-text('Inspect Source')").click()
                page.wait_for_selector("text=Source verified successfully", timeout=25000)

                rights_select = page.locator("select").first
                rights_select.select_option(value="EXPLICIT_PERMISSION")
                title_input = page.locator("input[value*='Manhua'], input[placeholder*='Captain Freedom']").first
                if not title_input.input_value():
                    title_input.fill("Demon Magic Emperor - Chapter 923")

                page.locator("button:has-text('Create & Proceed to Acquisition')").click()
                time.sleep(2)
                continue

        browser.close()

if __name__ == "__main__":
    run()
