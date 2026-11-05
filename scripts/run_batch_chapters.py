"""
Run AutoPilot stages 1-7 (Pages, Panels, OCR, Story, Script, Audio, Motion)
for Chapters 3, 4, and 5 using the 100% generic engine.
"""
import asyncio
import sys
import time
sys.path.insert(0, ".")
from engine.pipeline.autopilot import AutoPilotRunner
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord

CHAPTERS = [
    (3, "e373b06f-eee7-451f-8de7-6e480fcb4113"),
    (4, "1ba86afb-0164-4357-9ab3-9f73d0ef1e17"),
    (5, "0eefbfc6-47ac-49cf-be74-6d039ea05617"),
]

async def process_chapter(ch_num: int, project_id: str):
    print(f"\n=======================================================", flush=True)
    print(f"=== Starting AutoPilot for Chapter {ch_num} ({project_id}) ===", flush=True)
    print(f"=======================================================", flush=True)
    t0 = time.time()
    
    runner = AutoPilotRunner(
        project_id=project_id,
        options={"skip_existing_stages": False, "target_profile": "standard_1080p", "video_only": True}
    )
    
    # 1. Pages
    print(f"[Ch {ch_num}] Stage 1: Pages...", flush=True)
    await runner._execute_stage("pages", lambda: runner._run_stage_pages(False))
    print(f"[Ch {ch_num}] Pages: {runner.get_stage('pages').status} - {runner.get_stage('pages').message}", flush=True)
    
    # 2. Panels
    print(f"[Ch {ch_num}] Stage 2: Panels...", flush=True)
    await runner._execute_stage("panels", lambda: runner._run_stage_panels(False))
    print(f"[Ch {ch_num}] Panels: {runner.get_stage('panels').status} - {runner.get_stage('panels').message}", flush=True)
    
    # 3. OCR
    print(f"[Ch {ch_num}] Stage 3: OCR...", flush=True)
    await runner._execute_stage("ocr", lambda: runner._run_stage_ocr(False))
    print(f"[Ch {ch_num}] OCR: {runner.get_stage('ocr').status} - {runner.get_stage('ocr').message}", flush=True)
    
    # Clean promotions after OCR has extracted text
    with SessionLocal() as db:
        p_rec = db.get(ProjectRecord, project_id)
        runner._resolve_promotional_cleanup(db, p_rec)
        from engine.database.models import PanelRecord
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).all()
        ignored = [p for p in panels if p.status == "IGNORED"]
        print(f"[Ch {ch_num}] Promo Filter: {len(ignored)} non-story panels excluded ({len(panels)-len(ignored)} active story panels)", flush=True)
    
    # 4. Story
    print(f"[Ch {ch_num}] Stage 4: Story...", flush=True)
    await runner._execute_stage("story", lambda: runner._run_stage_story(False))
    print(f"[Ch {ch_num}] Story: {runner.get_stage('story').status} - {runner.get_stage('story').message}", flush=True)
    
    # 5. Script
    print(f"[Ch {ch_num}] Stage 5: Script...", flush=True)
    await runner._execute_stage("script", lambda: runner._run_stage_script(False))
    print(f"[Ch {ch_num}] Script: {runner.get_stage('script').status} - {runner.get_stage('script').message}", flush=True)
    
    # 6. Audio
    print(f"[Ch {ch_num}] Stage 6: Audio...", flush=True)
    await runner._execute_stage("audio", lambda: runner._run_stage_audio(False))
    print(f"[Ch {ch_num}] Audio: {runner.get_stage('audio').status} - {runner.get_stage('audio').message}", flush=True)
    
    # 7. Motion
    print(f"[Ch {ch_num}] Stage 7: Motion...", flush=True)
    await runner._execute_stage("motion", lambda: runner._run_stage_motion(False))
    print(f"[Ch {ch_num}] Motion: {runner.get_stage('motion').status} - {runner.get_stage('motion').message}", flush=True)
    
    # Print summary of timeline
    with SessionLocal() as db:
        p_rec = db.get(ProjectRecord, project_id)
        se = (p_rec.settings or {}).get("story_editor_state") or {}
        scenes = se.get("scenes", [])
        clips = se.get("narration_clips", [])
        tot_dur = sum(float(sc.get("duration_sec", 0)) for sc in scenes)
        print(f"\n[Ch {ch_num} READY] Total Scenes: {len(scenes)}, Clips: {len(clips)}, Duration: {tot_dur:.1f}s ({tot_dur/60:.2f}m) in {time.time()-t0:.1f}s", flush=True)
        for idx, sc in enumerate(scenes):
            sc_layers = sc.get("layers", [])
            sc_d = float(sc.get("duration_sec", 0))
            avg_p = sc_d / max(1, len(sc_layers))
            print(f"  Scene {idx+1}: {len(sc_layers)} panels, duration={sc_d:.1f}s (avg {avg_p:.2f}s/panel)", flush=True)

async def main():
    for ch_num, pid in CHAPTERS:
        await process_chapter(ch_num, pid)

if __name__ == "__main__":
    asyncio.run(main())
