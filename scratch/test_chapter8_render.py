"""
Test script for Chapter 8 Production Video Rendering & Export.
Validates Timeline Compilation, Preflight Checks, Visual Compositing, Audio Ducking, and FFmpeg Encoding.
"""
import sys
import json
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PageRecord, PanelRecord
from engine.render.compiler import timeline_compiler
from engine.render.models.profiles import RenderProfile
from engine.render.engine import RenderEngine

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ID = "68711176-90f5-4a68-8520-78d6e183bf65"

def run_test():
    print("=========================================================")
    print(" PANELFLOW STUDIO — CHAPTER 8 RENDER PIPELINE TEST")
    print("=========================================================")

    with SessionLocal() as db:
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == PROJECT_ID).first()
        assert proj, "Project not found"
        workspace = Path(proj.workspace_path)
        pages = db.query(PageRecord).filter(PageRecord.project_id == PROJECT_ID).order_by(PageRecord.sequence).all()
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID).all()

        print(f"Project: {proj.title} ({proj.id})")
        print(f"Workspace: {workspace}")
        print(f"Available Pages: {len(pages)} | Available Panels: {len(panels)}")

        # Construct realistic 6-scene Story Editor state (24 seconds)
        scenes = []
        running_time = 0.0
        seed_panels = panels[:6]

        for idx, pnl in enumerate(seed_panels):
            dur = 4.0
            motion_preset = "slow_zoom_in" if idx % 2 == 0 else "pan_right"
            trans = "fade_from_black" if idx == 0 else ("cross_dissolve" if idx == 3 else "none")

            layer = {
                "id": f"layer_{pnl.id}",
                "source_page_id": pnl.page_id,
                "source_panel_id": pnl.id,
                "image_url": f"/api/projects/{PROJECT_ID}/panels/{pnl.id}/crop",
                "page_sequence": pnl.page_sequence,
                "crop": {"x": pnl.x, "y": pnl.y, "width": pnl.width, "height": pnl.height},
                "transform": {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "opacity": 1.0, "z_index": 0},
                "motion_preset": motion_preset,
                "motion_easing": "ease_in_out",
                "start_offset_sec": 0.0,
                "duration_sec": dur,
                "visible": True,
            }

            scenes.append({
                "id": f"scene_{idx + 1}",
                "sequence": idx + 1,
                "title": f"Scene {idx + 1} — Panel #{idx + 1}",
                "start_time_sec": running_time,
                "duration_sec": dur,
                "transition_in": trans,
                "transition_duration_sec": 0.5,
                "layers": [layer],
                "camera_motion": {
                    "preset": "slow_zoom_in" if idx == 1 else "static",
                    "zoom_start": 1.0,
                    "zoom_end": 1.15,
                    "pan_x_start": 0.0,
                    "pan_x_end": 0.0,
                    "pan_y_start": 0.0,
                    "pan_y_end": 0.0,
                    "easing": "ease_in_out",
                    "duration_sec": dur,
                }
            })
            running_time += dur

        # Real synthesized audio files from Chapter 7
        dialogue_wavs = list((workspace / "audio" / "dialogue").glob("*.wav"))
        print(f"Discovered {len(dialogue_wavs)} synthesized dialogue WAVs in project")

        narration_clips = []
        if len(dialogue_wavs) >= 2:
            narration_clips.append({
                "id": "narr_01",
                "scene_id": "scene_1",
                "speaker": "The Narrator",
                "text": "The ancient citadel stood silent beneath ominous storm clouds.",
                "emotion": "Mysterious",
                "status": "READY",
                "review_status": "APPROVED",
                "start_time_sec": 0.5,
                "duration_sec": 3.89,
                "audio_url": str(dialogue_wavs[0]),
            })
            narration_clips.append({
                "id": "narr_02",
                "scene_id": "scene_3",
                "speaker": "Marcus",
                "text": "Stand firm! We do not surrender this ground!",
                "emotion": "Determined",
                "status": "READY",
                "review_status": "APPROVED",
                "start_time_sec": 8.5,
                "duration_sec": 3.5,
                "audio_url": str(dialogue_wavs[1]),
            })

        # BGM & SFX
        bgm_tracks = [
            {
                "id": "bgm_01",
                "title": "Ambient Discovery (D-Minor)",
                "file_url": "/assets/demo/crystal_resonance_bgm.mp3",
                "volume": 0.6,
                "start_time_sec": 0.0,
                "duration_sec": 24.0,
                "loop": True,
                "ducking_enabled": True,
                "ducking_amount_db": -12.0,
            }
        ]

        sfx_cues = [
            {
                "id": "sfx_01",
                "name": "Blade Shimmer",
                "file_url": "/assets/demo/blade_shimmer_sfx.mp3",
                "start_time_sec": 1.0,
                "duration_sec": 2.2,
                "volume": 0.8,
            },
            {
                "id": "sfx_02",
                "name": "Impact Whoosh",
                "file_url": "/assets/demo/blade_shimmer_sfx.mp3",
                "start_time_sec": 12.5,
                "duration_sec": 2.2,
                "volume": 0.85,
            }
        ]

        story_editor_state = {
            "schema_version": 2,
            "project_id": PROJECT_ID,
            "aspect_ratio": "16:9",
            "scenes": scenes,
            "narration_clips": narration_clips,
            "bgm_tracks": bgm_tracks,
            "sfx_cues": sfx_cues,
        }

        # Step 1: Preflight Validation
        print("\n--- 1. Testing Preflight Validation ---")
        preflight = timeline_compiler.preflight_validate(story_editor_state, PROJECT_ID, workspace)
        print(f"Preflight Valid: {preflight['valid']}")
        print(f"Stats: {preflight['stats']}")
        if preflight["warnings"]:
            print(f"Warnings ({len(preflight['warnings'])}): {preflight['warnings'][:2]}")
        assert preflight["valid"], f"Preflight validation failed: {preflight['blockers']}"

        # Step 2: Compile RenderPlan
        print("\n--- 2. Compiling RenderPlan ---")
        profile = RenderProfile.standard_1080p()
        plan = timeline_compiler.compile(
            state=story_editor_state,
            project_id=PROJECT_ID,
            workspace_path=workspace,
            profile=profile,
            subtitle_enabled=True,
            bgm_volume_db=-10.0,
            dialogue_gain_db=0.0,
        )
        print(f"Compiled Plan ID: {plan.plan_id}")
        print(f"Total Duration: {plan.total_duration_sec:.2f}s | Total Frames: {plan.total_frames} (at {profile.fps} FPS)")
        print(f"Shots Count: {len(plan.shots)} | Audio Tracks Count: {len(plan.audio_tracks)}")
        for i, shot in enumerate(plan.shots):
            print(f"  Shot {shot.sequence_global} [{shot.start_time:.1f}s - {shot.end_time:.1f}s]: {len(shot.scene_layers)} layers, asset={Path(shot.source_asset_path).name}")
        for i, trk in enumerate(plan.audio_tracks):
            print(f"  Audio Track [{trk.track_type}] {trk.start_time:.1f}s - {trk.end_time:.1f}s | {Path(trk.file_path).name} (gain {trk.gain_db}dB)")

        # Step 3: Execute Render
        print("\n--- 3. Executing Render (1080p H.264 / AAC) ---")
        output_mp4 = workspace / "renders" / f"test_render_chapter8_{int(time.time())}.mp4"
        engine = RenderEngine()

        t0 = time.time()
        def progress_cb(stage, done, total, pct):
            if done % 60 == 0 or done == total:
                print(f"  [{stage.value}] {done}/{total} frames ({pct:.1f}%)")

        audit_report = engine.execute_render(
            plan=plan,
            output_mp4_path=output_mp4,
            progress_cb=progress_cb,
        )
        render_dur = time.time() - t0

        print(f"\nRender completed in {render_dur:.2f}s (Speed: {plan.total_frames / render_dur:.1f} FPS)")
        print(f"Output File: {output_mp4}")
        print(f"File Exists: {output_mp4.exists()} | Size: {output_mp4.stat().st_size / 1024 / 1024:.2f} MB")
        print(f"Validation Report: valid={audit_report.is_valid}")
        print(f"Actual Duration: {audit_report.actual_duration_sec:.2f}s")
        print(f"Quality Flags: {audit_report.quality_flags}")
        assert output_mp4.exists() and output_mp4.stat().st_size > 100000, "Rendered MP4 file missing or empty"
        assert audit_report.is_valid, f"Render audit failed: {audit_report.warnings}"

        print("\nAll Chapter 8 backend rendering checks passed successfully!")

if __name__ == "__main__":
    run_test()
