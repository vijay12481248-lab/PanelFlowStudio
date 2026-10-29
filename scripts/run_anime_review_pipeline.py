"""
CLI Tool: Automated Anime Episode Review & Recap Producer for PanelFlow Studio.

Examples:
  # 1. Inspect and preview scene cuts & review script (Dry run):
  python scripts/run_anime_review_pipeline.py --video "path/to/episode.mp4" --title "Solo Leveling" --episode 1 --dry-run

  # 2. Produce full synchronized 1080p anime review video:
  python scripts/run_anime_review_pipeline.py --video "path/to/episode.mp4" --title "Solo Leveling" --episode 1 --voice "am_michael"
"""
import sys
import argparse
import asyncio
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

from engine.anime.models import AnimeReviewConfig
from engine.anime.pipeline import AnimeReviewPipeline
from engine.anime.scene_detector import AnimeSceneClipper
from engine.anime.story_generator import AnimeReviewStoryEngine


async def main():
    parser = argparse.ArgumentParser(
        description="Automated Anime Review & Recap Video Producer (PanelFlow Studio)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--video", required=True, help="Path to the anime episode video file (MP4/MKV/WebM)")
    parser.add_argument("--title", required=True, help="Series title (e.g. 'Solo Leveling', 'Demon Slayer')")
    parser.add_argument("--episode", type=float, default=1.0, help="Episode number (default: 1.0)")
    parser.add_argument("--episode-title", default=None, help="Optional episode name/subtitle")
    parser.add_argument("--voice", default="am_michael", help="Kokoro-82M voice profile (default: am_michael)")
    parser.add_argument("--duck", type=float, default=-18.0, help="Original anime audio ducking in dB (default: -18.0)")
    parser.add_argument("--max-cut", type=float, default=4.5, help="Max cut duration in seconds (default: 4.5)")
    parser.add_argument("--min-cut", type=float, default=2.0, help="Min cut duration in seconds (default: 2.0)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and display review script without rendering")
    parser.add_argument("--output-dir", default=None, help="Custom output root directory")

    args = parser.parse_args()

    print("=" * 80)
    print("PANELFLOW STUDIO: AUTOMATED ANIME REVIEW & RECAP PRODUCER")
    print("=" * 80)
    print(f"Source Video:      {args.video}")
    print(f"Series Title:      {args.title}")
    print(f"Episode:           {args.episode:g}")
    print(f"Neural TTS Voice:  {args.voice}")
    print(f"Audio Ducking:     {args.duck:.1f} dB")
    print(f"Cut Duration:      {args.min_cut:.1f}s - {args.max_cut:.1f}s")
    print(f"Dry Run Only:      {args.dry_run}")
    print("-" * 80)

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"ERROR: Video file does not exist at: {video_path}")
        return

    clipper = AnimeSceneClipper()
    print("\n[Step 1/4] Inspecting video stream...", flush=True)
    source = clipper.inspect_source(str(video_path), series_title=args.title, episode_num=args.episode)
    source.episode_title = args.episode_title

    print(f"Resolution:        {source.width}x{source.height}")
    print(f"Frame Rate:        {source.fps} fps")
    print(f"Total Duration:    {source.duration_sec:.1f}s ({source.duration_sec/60.0:.2f} minutes)")
    print(f"Audio Track:       {'Yes (' + str(source.audio_sample_rate) + ' Hz)' if source.has_audio else 'No'}")

    print("\n[Step 2/4] Scanning scene transitions & keyframes...", flush=True)
    intervals = clipper.detect_scenes_opencv(
        str(video_path),
        min_cut_sec=args.min_cut,
        max_cut_sec=args.max_cut,
        max_total_cuts=60,
    )
    print(f"Detected Scene Cuts: {len(intervals)} cuts (avg duration: {source.duration_sec/max(1, len(intervals)):.2f}s)")

    print("\n[Step 3/4] Formulating 4-act review & recap story script...", flush=True)
    dummy_cuts = [
        type("Cut", (), {"cut_id": f"cut_{i:03d}", "duration_sec": round(e - s, 2)})()
        for i, (s, e) in enumerate(intervals, 1)
    ]
    story_engine = AnimeReviewStoryEngine()
    beats = story_engine.generate_review_script(source, dummy_cuts)

    print("-" * 80)
    print("STRUCTURED REVIEW STORY BEATS:")
    print("-" * 80)
    for b in beats:
        print(f"[{b.sequence:02d}] {b.act_type.value:20s} ({b.emotion})")
        print(f"     \"{b.voiceover_text}\"")
        print(f"     Target Cuts: {b.assigned_cut_ids[:4]} (total {len(b.assigned_cut_ids)} cuts)")
        print()

    if args.dry_run:
        print("-" * 80)
        print("Dry run complete. To slice cuts and render the synchronized review video, re-run without --dry-run.")
        print("=" * 80)
        return

    # Full execution
    print("\n[Step 4/4] Executing Full Production Pipeline...", flush=True)
    config = AnimeReviewConfig(
        source_video=str(video_path.resolve()),
        series_title=args.title,
        episode_number=args.episode,
        episode_title=args.episode_title,
        max_cut_length_sec=args.max_cut,
        min_cut_length_sec=args.min_cut,
        tts_voice=args.voice,
        original_audio_duck_db=args.duck,
        output_dir=args.output_dir,
    )

    pipeline = AnimeReviewPipeline()

    def on_progress(pct: float, msg: str):
        print(f"[Review Progress] {int(pct * 100)}% - {msg}", flush=True)

    result = await pipeline.produce_review_video(config, progress_cb=on_progress)

    print("\n" + "=" * 80)
    print("ANIME REVIEW VIDEO PRODUCTION COMPLETED!")
    print("=" * 80)
    print(f"Master Video:      {result.output_video_path}")
    print(f"Total Duration:    {result.video_duration_sec:.1f}s ({result.video_duration_sec/60.0:.2f} mins)")
    print(f"Total Scene Cuts:  {result.total_scene_cuts}")
    print(f"Review Story Beats: {result.total_review_beats}")
    print(f"Release Package:   {result.youtube_metadata_path}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
