import asyncio
import os
import sys
import time
import shutil
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure utf-8 stdout
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from engine.pipeline.autopilot import AutoPilotRunner
from engine.database.session import SessionLocal
from engine.database.models import RenderJobRecord

PROJECT_ID = "098c6713-478b-4b77-917c-d2737215481b"
OUTPUT_DIR = PROJECT_ROOT / "output" / "Chapter_927"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TARGET_MP4 = OUTPUT_DIR / "Demon_Magic_Emperor_Chapter_927_1080p.mp4"

async def progress_reporter(runner):
    last_p = -1
    while True:
        await asyncio.sleep(5.0)
        st = runner.get_stage("render")
        if st and st.status == "RUNNING":
            pct = int(st.progress * 100)
            if pct != last_p:
                print(f"[Render Progress] {pct}% - {st.message}", flush=True)
                last_p = pct
        elif st and st.status in ("COMPLETED", "FAILED"):
            break

async def main():
    print("=== Launching Production Render for Demon Magic Emperor Chapter 927 ===", flush=True)
    runner = AutoPilotRunner(PROJECT_ID, options={
        "skip_existing_stages": False,
        "target_profile": "standard_1080p",
        "subtitles": True,
    })

    rep_task = asyncio.create_task(progress_reporter(runner))
    start_t = time.monotonic()

    try:
        print("Executing Stage 8: Standard 1080p Render...", flush=True)
        await runner._run_stage_render("standard_1080p", skip_existing=False)
        render_stage = runner.get_stage("render")
        elapsed = round(time.monotonic() - start_t, 1)
        print(f"Stage 8 Render status: {render_stage.status} in {elapsed}s", flush=True)

        if render_stage.status != "COMPLETED":
            print(f"ERROR: Render did not complete successfully: {render_stage.message}", flush=True)
            return

        print("\nExecuting Stage 9: Packaging & Release Metadata...", flush=True)
        try:
            await runner._run_stage_packaging("standard_1080p")
            print(f"Stage 9 Packaging status: {runner.get_stage('packaging').status}", flush=True)
        except Exception as e:
            print(f"Warning during packaging stage: {e}", flush=True)

        # Retrieve certified render job
        with SessionLocal() as db:
            last_job = db.query(RenderJobRecord).filter(
                RenderJobRecord.project_id == PROJECT_ID,
                RenderJobRecord.status == "COMPLETE"
            ).order_by(RenderJobRecord.created_at.desc()).first()

            if not last_job or not last_job.output_path:
                print("ERROR: No completed RenderJobRecord found!", flush=True)
                return

            rendered_path = Path(last_job.output_path)
            print(f"\nRendered Master MP4 located at: {rendered_path}", flush=True)
            if not rendered_path.exists():
                print(f"ERROR: Render output file does not exist at {rendered_path}", flush=True)
                return

            file_size_mb = rendered_path.stat().st_size / (1024 * 1024)
            print(f"Rendered file size: {file_size_mb:.2f} MB", flush=True)

            # Copy to target directory
            shutil.copy2(str(rendered_path), str(TARGET_MP4))
            print(f"SUCCESS: Certified MP4 copied to: {TARGET_MP4}", flush=True)

            # Write YouTube release packaging
            yt_title = runner.result.get("youtube_title") or "Demon Magic Emperor Chapter 927 - The Trap of Flying Cloud Manor | Full Motion Manhua"
            yt_desc = runner.result.get("youtube_description") or (
                "Demon Magic Emperor Chapter 927: The Trap of Flying Cloud Manor\n\n"
                "Shangguan Yulin secretly meets Zhuo Fan to hand over the map of Flying Cloud Manor, pledging false devotion. "
                "Meanwhile, Sword King Feiyun and Prime Minister Baili Jingwei prepare an inescapable ambush—until Baili Jingwei discovers an anomaly in the map.\n\n"
                "Produced with PanelFlow Studio."
            )
            yt_tags = runner.result.get("youtube_tags") or ["Demon Magic Emperor", "Zhuo Fan", "Chapter 927", "Flying Cloud Manor", "Manhua Motion Comic"]

            meta_file = OUTPUT_DIR / "Demon_Magic_Emperor_Chapter_927_YouTube_Metadata.txt"
            with open(meta_file, "w", encoding="utf-8") as f:
                f.write(f"TITLE:\n{yt_title}\n\n")
                f.write(f"DESCRIPTION:\n{yt_desc}\n\n")
                f.write(f"TAGS:\n{', '.join(yt_tags) if isinstance(yt_tags, list) else yt_tags}\n")

            print(f"YouTube metadata written to: {meta_file}", flush=True)

    finally:
        rep_task.cancel()

    print("\n=== Chapter 927 Full Production Pipeline Complete! ===", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
