import os
import sys
import json
import time
import math
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image
import soundfile as sf

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.render.compiler import timeline_compiler
from engine.render.composer import FrameComposer
from engine.render.service import RenderEngine
from engine.render.models.profiles import RenderProfile
from engine.render.audio import AudioMixer

PROJECT_ID = "68711176-90f5-4a68-8520-78d6e183bf65"
WORKSPACE_PATH = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\68711176-90f5-4a68-8520-78d6e183bf65")
RENDERS_DIR = WORKSPACE_PATH / "renders"
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

def create_base_scenes(count=2, dur=3.0):
    scenes = []
    for i in range(count):
        scenes.append({
            "id": f"sc_{i+1}",
            "title": f"Scene {i+1}",
            "start_time_sec": i * dur,
            "duration_sec": dur,
            "camera_motion": {"preset": "static"},
            "transition": {"type": "fade", "duration_sec": 0.3},
            "layers": [
                {
                    "id": f"ly_{i+1}",
                    "name": f"Panel {i+1}",
                    "source_panel_id": f"panel_{i+1:04d}",
                    "image_url": f"panels/panel_{i+1:04d}.jpg",
                    "transform": {"x": 0, "y": 0, "scale": 1.0, "rotation": 0, "opacity": 1.0, "z_index": 0},
                    "motion_preset": "none",
                    "duration_sec": dur,
                }
            ],
        })
    return scenes

def test_regression_cases():
    print("=================================================================")
    print(" CHAPTER 9.1: COMPLETE RENDERING & MIXER REGRESSION SUITE")
    print("=================================================================")

    dialogue_dir = WORKSPACE_PATH / "audio" / "dialogue"
    speech_clips = sorted(list(dialogue_dir.glob("*.wav")))
    speech_sample = str(speech_clips[0]) if speech_clips else ""
    engine = RenderEngine()

    test_results = {}

    # Case 1: Existing project with ordinary music asset
    print("\n[Case 1/9] Testing Ordinary Music Asset (demo BGM)...")
    state_ord = {
        "schema_version": 2,
        "aspect_ratio": "16:9",
        "scenes": create_base_scenes(2, 3.0),
        "narration_clips": [],
        "bgm_tracks": [{"id": "bgm_1", "title": "Demo BGM", "file_url": "/assets/demo/crystal_resonance_bgm.mp3", "volume": 0.5}],
        "sfx_cues": [],
    }
    plan_ord = timeline_compiler.compile(state_ord, PROJECT_ID, WORKSPACE_PATH, RenderProfile.draft_720p())
    out_ord = RENDERS_DIR / "reg_01_ordinary_music.mp4"
    res_ord = engine.execute_render(plan_ord, out_ord, WORKSPACE_PATH)
    test_results["ordinary_music"] = {"success": res_ord.is_valid and out_ord.exists(), "size_bytes": out_ord.stat().st_size}
    print(f"  -> Result: {test_results['ordinary_music']}")
    assert test_results["ordinary_music"]["success"]

    # Case 2: Project with NO music
    print("\n[Case 2/9] Testing Project with NO music...")
    state_nomus = {
        "schema_version": 2,
        "aspect_ratio": "16:9",
        "scenes": create_base_scenes(2, 3.0),
        "narration_clips": [{"id": "n1", "text": "Testing speech only.", "audio_url": speech_sample, "start_time_sec": 0.5, "duration_sec": 2.0}],
        "bgm_tracks": [],
        "sfx_cues": [],
    }
    plan_nomus = timeline_compiler.compile(state_nomus, PROJECT_ID, WORKSPACE_PATH, RenderProfile.draft_720p())
    out_nomus = RENDERS_DIR / "reg_02_no_music.mp4"
    res_nomus = engine.execute_render(plan_nomus, out_nomus, WORKSPACE_PATH)
    test_results["no_music"] = {"success": res_nomus.is_valid and out_nomus.exists(), "size_bytes": out_nomus.stat().st_size}
    print(f"  -> Result: {test_results['no_music']}")
    assert test_results["no_music"]["success"]

    # Case 3: Project with AI music take
    print("\n[Case 3/9] Testing Project with Local AI Music...")
    music_dir = WORKSPACE_PATH / "audio" / "music"
    ai_takes = sorted(list(music_dir.glob("*.wav")))
    ai_sample = str(ai_takes[0]) if ai_takes else ""
    state_aimus = {
        "schema_version": 2,
        "aspect_ratio": "16:9",
        "scenes": create_base_scenes(2, 3.0),
        "narration_clips": [],
        "bgm_tracks": [{"id": "bgm_ai", "title": "AI Score", "file_url": ai_sample, "start_time_sec": 0.0, "duration_sec": 6.0, "volume": 0.6}],
        "sfx_cues": [],
    }
    plan_aimus = timeline_compiler.compile(state_aimus, PROJECT_ID, WORKSPACE_PATH, RenderProfile.draft_720p())
    out_aimus = RENDERS_DIR / "reg_03_ai_music.mp4"
    res_aimus = engine.execute_render(plan_aimus, out_aimus, WORKSPACE_PATH)
    test_results["ai_music"] = {"success": res_aimus.is_valid and out_aimus.exists(), "size_bytes": out_aimus.stat().st_size}
    print(f"  -> Result: {test_results['ai_music']}")
    assert test_results["ai_music"]["success"]

    # Case 4: Multiple BGM cues with start_time offsets
    print("\n[Case 4/9] Testing Multiple Sequential BGM Cues...")
    state_multi_bgm = {
        "schema_version": 2,
        "aspect_ratio": "16:9",
        "scenes": create_base_scenes(2, 4.0),
        "narration_clips": [],
        "bgm_tracks": [
            {"id": "bgm_part1", "title": "Part 1", "file_url": ai_sample, "start_time_sec": 0.0, "duration_sec": 4.0, "volume": 0.6},
            {"id": "bgm_part2", "title": "Part 2", "file_url": ai_sample, "start_time_sec": 4.0, "duration_sec": 4.0, "volume": 0.6},
        ],
        "sfx_cues": [],
    }
    plan_multi = timeline_compiler.compile(state_multi_bgm, PROJECT_ID, WORKSPACE_PATH, RenderProfile.draft_720p())
    out_multi = RENDERS_DIR / "reg_04_multiple_bgm.mp4"
    res_multi = engine.execute_render(plan_multi, out_multi, WORKSPACE_PATH)
    test_results["multiple_bgm"] = {"success": res_multi.is_valid and out_multi.exists(), "size_bytes": out_multi.stat().st_size}
    print(f"  -> Result: {test_results['multiple_bgm']}")
    assert test_results["multiple_bgm"]["success"]

    # Case 5: Narration-only export
    print("\n[Case 5/9] Testing Narration-Only Export...")
    state_narr_only = {
        "schema_version": 2,
        "aspect_ratio": "16:9",
        "scenes": create_base_scenes(1, 3.0),
        "narration_clips": [{"id": "n1", "text": "Speech only line.", "audio_url": speech_sample, "start_time_sec": 0.2, "duration_sec": 2.5}],
        "bgm_tracks": [],
        "sfx_cues": [],
    }
    plan_narr = timeline_compiler.compile(state_narr_only, PROJECT_ID, WORKSPACE_PATH, RenderProfile.draft_720p())
    out_narr = RENDERS_DIR / "reg_05_narration_only.mp4"
    res_narr = engine.execute_render(plan_narr, out_narr, WORKSPACE_PATH)
    test_results["narration_only"] = {"success": res_narr.is_valid and out_narr.exists(), "size_bytes": out_narr.stat().st_size}
    print(f"  -> Result: {test_results['narration_only']}")
    assert test_results["narration_only"]["success"]

    # Case 6: SFX-only export
    print("\n[Case 6/9] Testing SFX-Only Export...")
    state_sfx_only = {
        "schema_version": 2,
        "aspect_ratio": "16:9",
        "scenes": create_base_scenes(1, 3.0),
        "narration_clips": [],
        "bgm_tracks": [],
        "sfx_cues": [{"id": "sfx_1", "title": "Shimmer", "file_url": "/assets/demo/blade_shimmer_sfx.mp3", "start_time_sec": 0.5, "duration_sec": 2.0}],
    }
    plan_sfx = timeline_compiler.compile(state_sfx_only, PROJECT_ID, WORKSPACE_PATH, RenderProfile.draft_720p())
    out_sfx = RENDERS_DIR / "reg_06_sfx_only.mp4"
    res_sfx = engine.execute_render(plan_sfx, out_sfx, WORKSPACE_PATH)
    test_results["sfx_only"] = {"success": res_sfx.is_valid and out_sfx.exists(), "size_bytes": out_sfx.stat().st_size}
    print(f"  -> Result: {test_results['sfx_only']}")
    assert test_results["sfx_only"]["success"]

    # Case 7: Missing music asset (must fallback cleanly without crash)
    print("\n[Case 7/9] Testing Missing Music Asset Graceful Fallback...")
    state_missing = {
        "schema_version": 2,
        "aspect_ratio": "16:9",
        "scenes": create_base_scenes(1, 3.0),
        "narration_clips": [],
        "bgm_tracks": [{"id": "bgm_nonexist", "title": "Ghost Audio", "file_url": "/nonexistent/path/ghost_music.mp3", "volume": 0.5}],
        "sfx_cues": [],
    }
    # Preflight check should catch warning but not block
    val = timeline_compiler.preflight_validate(state_missing, PROJECT_ID, WORKSPACE_PATH)
    print(f"  Preflight validation valid: {val['valid']}, Warnings: {val['warnings']}")
    plan_missing = timeline_compiler.compile(state_missing, PROJECT_ID, WORKSPACE_PATH, RenderProfile.draft_720p())
    out_missing = RENDERS_DIR / "reg_07_missing_music.mp4"
    res_missing = engine.execute_render(plan_missing, out_missing, WORKSPACE_PATH)
    test_results["missing_music"] = {"success": res_missing.is_valid and out_missing.exists(), "warning_caught": len(val["warnings"]) > 0}
    print(f"  -> Result: {test_results['missing_music']}")
    assert test_results["missing_music"]["success"]

    # Case 8: Vertical export 9:16
    print("\n[Case 8/9] Testing Vertical Shorts (9:16) Export...")
    state_vert = {
        "schema_version": 2,
        "aspect_ratio": "9:16",
        "scenes": create_base_scenes(1, 3.0),
        "narration_clips": [],
        "bgm_tracks": [{"id": "bgm_1", "file_url": ai_sample, "volume": 0.5}],
        "sfx_cues": [],
    }
    plan_vert = timeline_compiler.compile(state_vert, PROJECT_ID, WORKSPACE_PATH, RenderProfile.vertical_shorts())
    out_vert = RENDERS_DIR / "reg_08_vertical_shorts.mp4"
    res_vert = engine.execute_render(plan_vert, out_vert, WORKSPACE_PATH)
    test_results["vertical_shorts"] = {"success": res_vert.is_valid and out_vert.exists(), "profile": f"{plan_vert.profile.width}x{plan_vert.profile.height}"}
    print(f"  -> Result: {test_results['vertical_shorts']}")
    assert test_results["vertical_shorts"]["success"]

    # Case 9: Square export 1:1
    print("\n[Case 9/9] Testing Square Feed (1:1) Export...")
    state_sq = {
        "schema_version": 2,
        "aspect_ratio": "1:1",
        "scenes": create_base_scenes(1, 3.0),
        "narration_clips": [],
        "bgm_tracks": [{"id": "bgm_1", "file_url": ai_sample, "volume": 0.5}],
        "sfx_cues": [],
    }
    plan_sq = timeline_compiler.compile(state_sq, PROJECT_ID, WORKSPACE_PATH, RenderProfile.square_feed())
    out_sq = RENDERS_DIR / "reg_09_square_feed.mp4"
    res_sq = engine.execute_render(plan_sq, out_sq, WORKSPACE_PATH)
    test_results["square_feed"] = {"success": res_sq.is_valid and out_sq.exists(), "profile": f"{plan_sq.profile.width}x{plan_sq.profile.height}"}
    print(f"  -> Result: {test_results['square_feed']}")
    assert test_results["square_feed"]["success"]

    # Save summary
    reg_summary_p = RENDERS_DIR / "chapter9_1_regression_summary.json"
    reg_summary_p.write_text(json.dumps(test_results, indent=2), encoding="utf-8")
    print(f"\nSaved regression summary to {reg_summary_p}")

    print("\n=================================================================")
    print(" ALL 9 RENDERING REGRESSION CASES PASSED!")
    print("=================================================================")

if __name__ == "__main__":
    test_regression_cases()
