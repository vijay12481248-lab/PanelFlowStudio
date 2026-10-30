"""
CLI Tool: Smart Manga Series Scraper & Batch Video Producer for PanelFlow Studio.

Examples:
  # 1. Inspect a series or chapter URL:
  python scripts/run_smart_batch_manga.py --url "https://manhuaplus.com/manga/demon-magic-emperor01/chapter-927/" --dry-run

  # 2. Dry-run 25-minute compilation plan for Chapters 920 to 930:
  python scripts/run_smart_batch_manga.py --url "https://manhuaplus.com/manga/demon-magic-emperor01/" --start 920 --end 930 --mode compiled --duration 25 --dry-run

  # 3. Produce individual chapter videos for Chapters 925, 926, 927:
  python scripts/run_smart_batch_manga.py --url "https://manhuaplus.com/manga/demon-magic-emperor01/" --start 925 --end 927 --mode individual

  # 4. Produce a 25-minute movie cut for Chapters 921 to 927:
  python scripts/run_smart_batch_manga.py --url "https://manhuaplus.com/manga/demon-magic-emperor01/" --start 921 --end 927 --mode compiled --duration 25
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

from engine.acquisition.web.series.models import (
    BatchVideoConfig,
    CompilationMode,
    BatchJobStatus,
    SeriesChapter,
)
from engine.acquisition.web.series.discovery import SmartSeriesDiscoveryEngine
from engine.acquisition.web.series.grouper import SmartChapterGrouper
from engine.pipeline.batch_producer import SmartBatchVideoProducer


async def main():
    parser = argparse.ArgumentParser(
        description="Smart Manga Series Scraper & Batch Video Producer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", required=True, help="Series index URL or single chapter URL")
    parser.add_argument("--start", type=float, default=None, help="Starting chapter number (e.g. 921)")
    parser.add_argument("--end", type=float, default=None, help="Ending chapter number (e.g. 927)")
    parser.add_argument(
        "--mode",
        choices=["individual", "compiled"],
        default="individual",
        help="Production mode: 'individual' (1 video per chapter) or 'compiled' (multi-chapter compilation cuts)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=25.0,
        help="Target compilation duration in minutes (default: 25.0 min)",
    )
    parser.add_argument("--max-chapters", type=int, default=None, help="Maximum number of chapters to process")
    parser.add_argument("--voice", default="am_michael", help="Kokoro-82M voice profile (default: am_michael)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and display chapter plan without rendering")
    parser.add_argument("--output-dir", default=None, help="Custom output root directory")

    args = parser.parse_args()

    print("=" * 80)
    print("PANELFLOW STUDIO: SMART MANGA SERIES SCRAPER & BATCH VIDEO PRODUCER")
    print("=" * 80)
    print(f"Target URL:        {args.url}")
    print(f"Production Mode:   {args.mode.upper()}")
    if args.mode == "compiled":
        print(f"Target Duration:   {args.duration:.1f} minutes")
    print(f"Neural TTS Voice:  {args.voice}")
    print(f"Dry Run Only:      {args.dry_run}")
    print("-" * 80)

    discovery_engine = SmartSeriesDiscoveryEngine()
    grouper = SmartChapterGrouper()

    print("\n[Step 1/3] Discovering series catalog and chapters...", flush=True)
    meta = await discovery_engine.discover_series(args.url)

    print(f"\nSeries Title:        {meta.title}")
    print(f"Source Domain:       {meta.source_domain}")
    print(f"Total Discovered:    {meta.total_chapters_detected} chapters")
    print(f"Detected Range:      Chapter {meta.detected_range[0]:g} to {meta.detected_range[1]:g}")
    print(f"Discovery Strategy:  {meta.discovery_strategy}")
    if meta.url_pattern:
        print(f"Inferred URL Pattern: {meta.url_pattern}")

    # Filter chapters
    c_start = args.start if args.start is not None else meta.detected_range[0]
    c_end = args.end if args.end is not None else meta.detected_range[1]

    filtered_chapters = [
        c for c in meta.chapters if c_start - 1e-4 <= c.sequence <= c_end + 1e-4
    ]
    if not filtered_chapters and meta.url_pattern and c_start is not None and c_end is not None:
        for seq in range(int(c_start), int(c_end) + 1):
            ch_url = meta.url_pattern.replace("{chapter_number}", str(seq))
            filtered_chapters.append(SeriesChapter(
                sequence=float(seq),
                title=f"Chapter {seq}",
                url=ch_url,
            ))
    if args.max_chapters and len(filtered_chapters) > args.max_chapters:
        filtered_chapters = filtered_chapters[:args.max_chapters]

    print(f"\nSelected Range:      Chapter {c_start:g} to {c_end:g} ({len(filtered_chapters)} chapters selected)")

    if not filtered_chapters:
        print("ERROR: No chapters found matching the specified range!")
        return

    # Compute grouping bundles
    comp_mode = CompilationMode.COMPILED if args.mode == "compiled" else CompilationMode.INDIVIDUAL
    bundles = grouper.partition_chapters(
        chapters=filtered_chapters,
        series_title=meta.title,
        compilation_mode=comp_mode,
        target_duration_minutes=args.duration,
    )

    print("\n[Step 2/3] Production Bundle Plan:")
    print("-" * 80)
    for b_idx, b in enumerate(bundles, 1):
        dur_mins = b.estimated_duration_sec / 60.0
        print(f"Bundle #{b_idx}: {b.title}")
        print(f"  Chapters ({len(b.chapters)}): {b.chapters[0].sequence:g} -> {b.chapters[-1].sequence:g}")
        print(f"  Est. Duration: {dur_mins:.1f} minutes ({b.estimated_duration_sec:.0f} seconds)")
        print(f"  Output File:   {b.output_filename}")
        if len(b.chapters) > 1:
            print("  Chapter Timestamps:")
            for m in b.chapter_markers:
                print(f"    {m['timestamp_str']} - {m['title']}")
        print()

    if args.dry_run:
        print("-" * 80)
        print("Dry run completed. To execute the video production pipeline, re-run without --dry-run.")
        print("=" * 80)
        return

    # Execute batch production
    print("\n[Step 3/3] Executing Production Pipeline...", flush=True)
    config = BatchVideoConfig(
        source_url=args.url,
        compilation_mode=comp_mode,
        target_duration_minutes=args.duration,
        chapter_start=args.start,
        chapter_end=args.end,
        max_chapters=args.max_chapters,
        tts_voice=args.voice,
        output_dir=args.output_dir,
    )

    producer = SmartBatchVideoProducer()

    def on_progress(st: BatchJobStatus):
        pct = int(st.progress * 100)
        print(f"[Batch Progress] {pct}% - {st.current_step}", flush=True)

    result = await producer.run_batch(config, progress_cb=on_progress)

    print("\n" + "=" * 80)
    print("BATCH PRODUCTION FINISHED!")
    print("=" * 80)
    print(f"Status:              {result.status}")
    print(f"Chapters Completed:  {result.completed_chapters} / {result.total_chapters}")
    if result.generated_videos:
        print("\nGenerated Individual Episode Videos:")
        for v in result.generated_videos:
            print(f"  - {v}")
    if result.compilation_videos:
        print("\nGenerated Compilation Cut Videos:")
        for v in result.compilation_videos:
            print(f"  - {v}")
    if result.errors:
        print("\nErrors / Warnings:")
        for e in result.errors:
            print(f"  ! {e}")


if __name__ == "__main__":
    asyncio.run(main())
