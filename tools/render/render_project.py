"""
PanelFlow Studio CLI: Render Project Tool.
Compiles and renders a VisualTimeline and MasterAudioTimeline into a broadcast-quality MP4.

Usage:
  python tools/render/render_project.py --timeline path/to/timeline.json --audio path/to/audio.json --assets-dir path/to/panels --output output/movie.mp4
"""
import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from engine.render.engine import RenderEngine
from engine.render.models.profiles import RenderProfile
from engine.render.models.enums import MusicDurationPolicy, RenderStage
from engine.motion.models.timeline import VisualTimeline
from engine.motion.models.input_contract import MasterAudioTimeline


def parse_args():
    parser = argparse.ArgumentParser(description="PanelFlow Production Renderer CLI")
    parser.add_argument("--timeline", required=True, help="Path to visual_timeline.json")
    parser.add_argument("--audio", required=True, help="Path to master_audio_timeline.json")
    parser.add_argument("--assets-dir", default=None, help="Directory containing visual panel images")
    parser.add_argument("--assets-map", default=None, help="JSON file mapping asset_id to image path")
    parser.add_argument("--bgm", default=None, help="Path to background music WAV/OGG")
    parser.add_argument("--output", default="output/rendered_video.mp4", help="Output MP4 file path")
    parser.add_argument("--profile", default="standard_1080p", choices=["standard_1080p", "vertical_shorts", "square_feed", "draft_720p"])
    parser.add_argument("--music-policy", default="LOOP", choices=["LOOP", "EXTEND_OR_PAD", "FIT_TO_TIMELINE"])
    return parser.parse_args()


def main():
    args = parse_args()
    timeline_path = Path(args.timeline)
    audio_path = Path(args.audio)
    output_path = Path(args.output)

    if not timeline_path.exists():
        print(f"Error: Visual timeline file not found: {timeline_path}")
        sys.exit(1)
    if not audio_path.exists():
        print(f"Error: Master audio timeline file not found: {audio_path}")
        sys.exit(1)

    # 1. Load timelines
    print(f"Loading visual timeline: {timeline_path}")
    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline = VisualTimeline.model_validate_json(f.read())

    print(f"Loading master audio timeline: {audio_path}")
    with open(audio_path, "r", encoding="utf-8") as f:
        master_audio = MasterAudioTimeline.model_validate_json(f.read())

    # 2. Build assets map
    assets_map = {}
    if args.assets_map and Path(args.assets_map).exists():
        with open(args.assets_map, "r", encoding="utf-8") as f:
            assets_map = json.load(f)
    elif args.assets_dir and Path(args.assets_dir).exists():
        assets_dir = Path(args.assets_dir)
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            for p in assets_dir.glob(ext):
                assets_map[p.stem] = str(p)

    # 3. Configure profile
    profile_factories = {
        "standard_1080p": RenderProfile.standard_1080p,
        "vertical_shorts": RenderProfile.vertical_shorts,
        "square_feed": RenderProfile.square_feed,
        "draft_720p": RenderProfile.draft_720p,
    }
    profile = profile_factories[args.profile]()
    music_policy = MusicDurationPolicy[args.music_policy]

    engine = RenderEngine()

    # Preflight runtime check
    rt = engine.encoder.check_runtime()
    if not rt["available"]:
        print(f"FFmpeg Runtime Error: {rt.get('error')}")
        sys.exit(2)

    print(f"FFmpeg verified: {rt.get('version')}")

    # 4. Compile RenderPlan
    print("Compiling RenderPlan...")
    plan = engine.compile_render_plan(
        timeline=timeline,
        master_audio=master_audio,
        source_assets_map=assets_map,
        bgm_path=args.bgm,
        profile=profile,
        music_policy=music_policy,
    )
    print(f"RenderPlan compiled: {plan.total_frames} frames ({plan.total_duration_sec:.2f}s) across {len(plan.shots)} shots.")

    def progress_callback(stage: RenderStage, current: int, total: int, pct: float):
        sys.stdout.write(f"\r[{stage.value:<10}] {current}/{total} ({pct:.1f}%)")
        sys.stdout.flush()

    # 5. Execute Render
    print("\nStarting video execution...")
    audit_report = engine.execute_render(
        plan=plan,
        output_mp4_path=output_path,
        progress_cb=progress_callback,
    )
    print()

    # 6. Report results
    print("\n" + "=" * 60)
    print("RENDER SUMMARY:")
    print(f"  Valid:            {audit_report.is_valid}")
    print(f"  Output MP4:       {audit_report.output_mp4_path}")
    print(f"  File Size:        {audit_report.file_size_bytes / (1024*1024):.2f} MB")
    print(f"  Planned Duration: {audit_report.planned_duration_sec:.2f}s")
    print(f"  Actual Duration:  {audit_report.actual_duration_sec:.2f}s")
    print(f"  Black Frames:     {audit_report.quality_flags.get('black_frames')}")
    print(f"  Contact Sheet:    {audit_report.contact_sheet_path}")
    print("=" * 60)

    if not audit_report.is_valid:
        print("Render validation failed with warnings:")
        for w in audit_report.warnings:
            print(f"  - {w}")
        sys.exit(3)

    print("Render succeeded.")


if __name__ == "__main__":
    main()
