"""
Production Acceptance Runner for Milestone 7: First Real End-to-End MP4.

Integrates:
- Real visual sources: fixtures/sample_comic/page_01.jpg -> page_05.jpg
- Real neural TTS dialogue: C:\\Tools\\generated_audio\\marcus_male_deep (01_hook.wav -> 05_evaluation.wav)
- Real ACE-Step score: assets/cinematics/intro/audio/someone_stayed_ace_master.ogg
- Real SFX: assets/cinematics/intro/audio/sfx_intro_gauntlet_hum.wav
- Real Motion Director planning: VisualTimeline synthesis
- Real Production Renderer: 1080p 30fps H.264/AAC MP4 encoding + post-render ffprobe audit
"""
import sys
import json
import time
from pathlib import Path
from PIL import Image
import soundfile as sf

# Set up project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.motion.director import MotionDirector
from engine.motion.models.input_contract import (
    MotionDirectorInput,
    VisualSource,
    MasterAudioTimeline,
    AudioInterval,
    MotionStyleProfile,
)
from engine.motion.models.camera import NormalizedRect, TargetResolution
from engine.motion.models.enums import MotionPreset, TimelineSourceType
from engine.story.models import (
    VideoScript,
    ScriptSegment,
    SegmentType,
    EmotionType,
    MotionIntent,
    SceneEntity,
    CharacterEntity,
    CharacterRole,
)
from engine.render.engine import RenderEngine
from engine.render.models.profiles import RenderProfile
from engine.render.models.render_plan import RenderAudioTrack
from engine.render.models.enums import MusicDurationPolicy, RenderStage


def build_real_project():
    # 1. Real Visual Sources
    comic_dir = PROJECT_ROOT / "fixtures" / "sample_comic"
    pages = sorted(list(comic_dir.glob("page_*.jpg")))
    if not pages:
        raise RuntimeError(f"No comic pages found in {comic_dir}")

    visual_sources = []
    assets_map = {}
    for idx, page_path in enumerate(pages, start=1):
        with Image.open(page_path) as im:
            w, h = im.size

        asset_id = f"page_{idx:02d}"
        assets_map[asset_id] = str(page_path)

        # Realistic character and action focus regions
        char_boxes = {
            "char_marcus": NormalizedRect(x=0.20, y=0.15, width=0.35, height=0.45),
            "char_companion": NormalizedRect(x=0.55, y=0.40, width=0.35, height=0.50),
        }

        visual_sources.append(
            VisualSource(
                asset_id=asset_id,
                panel_id=f"panel_{idx:02d}",
                page_id=f"page_{idx:02d}",
                sequence_global=idx,
                file_path=str(page_path),
                width=w,
                height=h,
                character_bounding_boxes=char_boxes,
                reading_direction="ltr",
                panel_type="WIDE_ESTABLISHING" if idx == 1 else "DIALOGUE_TWO_SHOT",
            )
        )

    # 2. Real F5-TTS Dialogue Files
    tts_dir = Path(r"C:\Tools\generated_audio\marcus_male_deep")
    dialogue_specs = [
        ("01_hook.wav", "The ancient ruins lay silent under the subterranean crystal expanse.", "seg_01", "page_01"),
        ("02_scratch.wav", "Marcus paused at the precipice, reading the glowing conduits along the wall.", "seg_02", "page_02"),
        ("03_goal.wav", "Our objective was inside the resonant chamber, beyond the primary vault door.", "seg_03", "page_03"),
        ("04_playable_version.wav", "Every conduit carried harmonic energy, vibrating through the stone.", "seg_04", "page_04"),
        ("05_evaluation.wav", "The resonance frequency confirmed it: the Genesis Core was alive.", "seg_05", "page_05"),
    ]

    intervals = []
    segments = []
    current_time = 0.5  # 0.5s introductory silence before speech

    for wav_name, transcript, seg_id, asset_id in dialogue_specs:
        wav_path = tts_dir / wav_name
        if not wav_path.exists():
            raise RuntimeError(f"Missing real dialogue file: {wav_path}")

        info = sf.info(str(wav_path))
        dur = round(info.duration, 3)
        start_t = round(current_time, 3)
        end_t = round(start_t + dur, 3)

        intervals.append(
            AudioInterval(
                interval_id=f"iv_{seg_id}",
                script_segment_id=seg_id,
                speaker_character_id="char_marcus",
                start_time=start_t,
                end_time=end_t,
                audio_file_uri=str(wav_path),
                text=transcript,
                is_speech=True,
            )
        )

        segments.append(
            ScriptSegment(
                segment_id=seg_id,
                scene_id="scene_01",
                sequence=len(segments) + 1,
                type=SegmentType.CHARACTER_DIALOGUE,
                speaker_character_id="char_marcus",
                text=transcript,
                emotion=EmotionType.DETERMINED,
                intensity=0.7,
                estimated_duration=dur,
                estimated_start=start_t,
                estimated_end=end_t,
                production_intent="Dramatic narrative voiceover",
                motion_intent=MotionIntent.CHARACTER_FOCUS,
            )
        )

        # 0.5s pause between dialogue lines for natural cinematic breathing
        current_time = end_t + 0.5

    total_project_duration = round(current_time + 1.0, 3)  # 1.0s tail hold

    master_audio = MasterAudioTimeline(
        project_id="panelflow_real_01",
        total_duration_sec=total_project_duration,
        timeline_source=TimelineSourceType.REAL_AUDIO_TIMELINE,
        intervals=intervals,
        sample_rate=48000,
        channels=2,
    )

    script = VideoScript(
        script_id="script_real_01",
        project_id="panelflow_real_01",
        adaptation_profile="DRAMATIC_NARRATION",
        segments=segments,
    )

    # 3. Real ACE-Step Music & SFX
    bgm_path = PROJECT_ROOT.parent / "assets" / "cinematics" / "intro" / "audio" / "someone_stayed_ace_master.ogg"
    if not bgm_path.exists():
        # Fallback to chamber wav
        bgm_path = PROJECT_ROOT.parent / "assets" / "cinematics" / "intro" / "audio" / "someone_stayed_chamber.wav"

    sfx_path = PROJECT_ROOT.parent / "assets" / "cinematics" / "intro" / "audio" / "sfx_intro_gauntlet_hum.wav"

    scenes = [
        SceneEntity(
            scene_id="scene_01",
            sequence=1,
            title="The Vault Entrance",
            summary="Marcus enters the ancient conduit chamber.",
            panel_start="panel_01",
            panel_end="panel_05",
            character_ids=["char_marcus"],
        )
    ]

    characters = [
        CharacterEntity(
            character_id="char_marcus",
            display_name="Marcus",
            canonical_name="Marcus",
            role=CharacterRole.PROTAGONIST,
        )
    ]

    motion_input = MotionDirectorInput(
        project_id="panelflow_real_01",
        script=script,
        visual_sources=visual_sources,
        master_audio_timeline=master_audio,
        scenes=scenes,
        characters=characters,
        target_resolution=TargetResolution.standard_1080p(),
        style_profile=MotionStyleProfile.cinematic(),
    )

    return motion_input, assets_map, str(bgm_path), str(sfx_path)


def main():
    print("=" * 80)
    print("PANELFLOW STUDIO: REAL PRODUCTION RENDER ACCEPTANCE RUN (MILESTONE 7)")
    print("=" * 80)

    # Output directory
    output_dir = PROJECT_ROOT / "output" / "milestone7"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = output_dir / "first_real_panelflow.mp4"

    # 1. Assemble Project
    print("[1/5] Assembling real project inputs (comic visuals, F5-TTS audio, ACE-Step music)...")
    motion_input, assets_map, bgm_path, sfx_path = build_real_project()
    print(f"      Visual Sources:   {len(motion_input.visual_sources)} pages")
    print(f"      Dialogue Lines:   {len(motion_input.master_audio_timeline.intervals)} lines")
    print(f"      Total Duration:   {motion_input.master_audio_timeline.total_duration_sec:.2f}s")
    print(f"      BGM Master Track: {Path(bgm_path).name}")

    # 2. Plan Motion with Motion Director
    print("[2/5] Synthesizing VisualTimeline via Motion Director...")
    director = MotionDirector()
    visual_timeline = director.plan_visual_timeline(motion_input)
    print(f"      Timeline Generated: {visual_timeline.timeline_id}")
    print(f"      Total Shots:        {visual_timeline.total_shots}")
    print(f"      Warnings:           {len(visual_timeline.warnings)}")

    # Save visual timeline JSON
    vt_json_path = output_dir / "visual_timeline.json"
    with open(vt_json_path, "w", encoding="utf-8") as f:
        f.write(visual_timeline.model_dump_json(indent=2))

    # 3. Compile RenderPlan
    print("[3/5] Compiling frame-accurate RenderPlan (1080p @ 30fps)...")
    engine = RenderEngine()

    # Create optional SFX track at 1.0s
    sfx_tracks = []
    if Path(sfx_path).exists():
        sfx_tracks.append(
            RenderAudioTrack(
                track_type="sfx",
                file_path=sfx_path,
                start_time=1.0,
                end_time=3.5,
                gain_db=-6.0,
            )
        )

    plan = engine.compile_render_plan(
        timeline=visual_timeline,
        master_audio=motion_input.master_audio_timeline,
        source_assets_map=assets_map,
        bgm_path=bgm_path,
        sfx_tracks=sfx_tracks,
        profile=RenderProfile.standard_1080p(),
        music_policy=MusicDurationPolicy.LOOP,
    )

    print(f"      RenderPlan ID:     {plan.plan_id}")
    print(f"      Total Video Frames: {plan.total_frames} frames ({plan.total_duration_sec:.2f}s)")
    print(f"      Deterministic Hash: {plan.hash}")
    print(f"      Audio Tracks:       {len(plan.audio_tracks)} (Dialogue: 5, Music: 1, SFX: {len(sfx_tracks)})")

    # Save render plan JSON
    plan_json_path = output_dir / "render_plan.json"
    with open(plan_json_path, "w", encoding="utf-8") as f:
        f.write(plan.model_dump_json(indent=2))

    # 4. Execute Render
    print("[4/5] Executing Production Render (Streaming 1080p RGB frames to FFmpeg)...")
    t0 = time.time()

    def progress_callback(stage: RenderStage, current: int, total: int, pct: float):
        sys.stdout.write(f"\r      [{stage.value:<10}] {current}/{total} frames ({pct:5.1f}%)")
        sys.stdout.flush()

    audit_report = engine.execute_render(
        plan=plan,
        output_mp4_path=out_mp4,
        workspace_dir=output_dir / "workspace",
        progress_cb=progress_callback,
    )
    print()
    render_elapsed = time.time() - t0
    fps_render = plan.total_frames / max(0.1, render_elapsed)
    print(f"      Rendering Complete in {render_elapsed:.2f}s ({fps_render:.1f} fps rendering speed)")

    # 5. Audit & Validation
    print("[5/5] Performing Post-Render Inspection and Quality Audit...")
    print(f"      Valid:              {audit_report.is_valid}")
    print(f"      Output MP4:         {audit_report.output_mp4_path}")
    print(f"      File Size:          {audit_report.file_size_bytes / (1024*1024):.2f} MB")
    print(f"      Planned Duration:   {audit_report.planned_duration_sec:.2f}s")
    print(f"      Actual Duration:    {audit_report.actual_duration_sec:.2f}s")
    print(f"      Duration Diff:      {audit_report.duration_diff_sec:.3f}s")
    print(f"      Video Codec:        {audit_report.ffprobe_meta.get('video_codec')} ({audit_report.ffprobe_meta.get('width')}x{audit_report.ffprobe_meta.get('height')})")
    print(f"      Audio Codec:        {audit_report.ffprobe_meta.get('audio_codec')} ({audit_report.ffprobe_meta.get('sample_rate')} Hz, {audit_report.ffprobe_meta.get('channels')} ch)")
    print(f"      Black Frames:       {audit_report.quality_flags.get('black_frames')}")
    print(f"      Contact Sheet:      {audit_report.contact_sheet_path}")

    # Save validation report
    val_json_path = output_dir / "validation_report.json"
    with open(val_json_path, "w", encoding="utf-8") as f:
        f.write(audit_report.model_dump_json(indent=2))

    manifest = {
        "status": "APPROVED" if audit_report.is_valid else "FAILED",
        "output_mp4": str(out_mp4),
        "file_size_bytes": audit_report.file_size_bytes,
        "planned_duration_sec": audit_report.planned_duration_sec,
        "actual_duration_sec": audit_report.actual_duration_sec,
        "video_codec": audit_report.ffprobe_meta.get("video_codec"),
        "audio_codec": audit_report.ffprobe_meta.get("audio_codec"),
        "resolution": f"{audit_report.ffprobe_meta.get('width')}x{audit_report.ffprobe_meta.get('height')}",
        "black_frames": audit_report.quality_flags.get("black_frames"),
        "contact_sheet": audit_report.contact_sheet_path,
        "render_time_sec": round(render_elapsed, 2),
        "fps_rendering_speed": round(fps_render, 2),
        "validation_warnings": audit_report.warnings,
    }

    manifest_path = output_dir / "render_acceptance_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("=" * 80)
    if audit_report.is_valid:
        print("FIRST REAL PANELFLOW VIDEO RENDERED — RENDERER READY")
    else:
        print("PRODUCTION RENDER AUDIT FAILED")
        for w in audit_report.warnings:
            print(f"  - {w}")
        sys.exit(1)
    print("=" * 80)


if __name__ == "__main__":
    main()
