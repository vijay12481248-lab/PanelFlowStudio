import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

import asyncio
import json
import time
from pathlib import Path
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, RenderJobRecord
from engine.render.compiler import timeline_compiler
from engine.render.service import render_service

async def main():
    project_id = "a4e8115d-1e24-4a23-88b5-ecc72941bc8f"
    ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\a4e8115d-1e24-4a23-88b5-ecc72941bc8f")
    
    with open("scratch/magic_emperor_synthesized_narration.json", "r", encoding="utf-8") as f:
        synthesized_clips = json.load(f)
        
    print(f"Loaded {len(synthesized_clips)} synthesized narration clips.")
    
    with SessionLocal() as db:
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        settings = dict(project.settings or {})
        state = dict(settings.get("story_editor_state", {}))
        
        # 1. Update narration_clips in state
        formatted_clips = []
        for c in synthesized_clips:
            formatted_clips.append({
                "id": c["id"],
                "scene_id": c["scene_id"],
                "speaker": c["speaker"],
                "text": c["text"],
                "emotion": c["emotion"],
                "speed": 1.0,
                "status": "APPROVED",
                "review_status": "APPROVED",
                "start_time_sec": c["start_time_sec"],
                "duration_sec": c["duration_sec"],
                "audio_url": c["audio_url"],
                "linked_to_scene": True,
            })
        state["narration_clips"] = formatted_clips
        
        # 2. Add BGM track spanning full 172 seconds
        bgm_track = {
            "id": "bgm_magic_emperor_theme",
            "title": "Crystal Resonance Theme",
            "name": "Crystal Resonance Theme",
            "file_url": "/assets/demo/crystal_resonance_bgm.mp3",
            "volume": 0.40,
            "start_time_sec": 0.0,
            "duration_sec": 172.0,
            "loop": True,
            "ducking_enabled": True,
            "ducking_amount_db": -12.0,
        }
        state["bgm_tracks"] = [bgm_track]
        
        settings["story_editor_state"] = state
        project.settings = settings
        db.commit()
        print("Updated project settings with 8 narration clips and BGM track.")
        
    # 3. Preflight validate timeline compiler
    report = timeline_compiler.preflight_validate(state, project_id, ws)
    print("Preflight validation:", report["valid"])
    print("Stats:", json.dumps(report["stats"], indent=2))
    
    # 4. Trigger render job
    print("\nStarting video render with integrated speech and music...")
    with SessionLocal() as db:
        job_info = render_service.create_and_start_render_job(
            db,
            project_id,
            profile_name="standard_1080p",
            subtitle_enabled=False,
            timeline_data=state,
        )
        job_id = job_info["render_id"]
    print("Render job started:", job_id)
    
    while True:
        await asyncio.sleep(2.0)
        with SessionLocal() as db:
            info = render_service.get_render_job(db, job_id)
        prog = info.get("progress", 0.0)
        status = info.get("status")
        frames_done = info.get("frames_done", 0)
        frames_total = info.get("frames_total", 0)
        print(f"[{status}] Progress: {int(prog * 100)}% ({frames_done}/{frames_total} frames)")
        if status == "COMPLETE":
            with SessionLocal() as db:
                rec = db.query(RenderJobRecord).filter(RenderJobRecord.id == job_id).first()
                out_p = rec.output_path if rec else None
            print(f"\nRender completed successfully! Output: {out_p}")
            break
        elif status in ("FAILED", "CANCELLED"):
            print("Render failed:", info.get("error_message"))
            break

if __name__ == "__main__":
    asyncio.run(main())
