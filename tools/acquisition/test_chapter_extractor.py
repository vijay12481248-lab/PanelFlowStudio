"""
CLI Development Utility for testing the Adaptive Resilient Chapter Extraction Engine.

Usage:
    python tools/acquisition/test_chapter_extractor.py <URL> [OPTIONS]

Options:
    --download              Actually download discovered page images into output directory
    --out-dir PATH          Custom output directory (default: ./tmp_chapter_download)
    --allow-loopback        Permit local loopback URLs for testing synthetic HTTP servers
"""
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.acquisition.web.chapter_extractor import AdaptiveChapterExtractor


async def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    url = sys.argv[1]
    should_download = "--download" in sys.argv
    allow_loopback = "--allow-loopback" in sys.argv

    out_dir = Path("./tmp_chapter_download")
    for idx, arg in enumerate(sys.argv):
        if arg == "--out-dir" and idx + 1 < len(sys.argv):
            out_dir = Path(sys.argv[idx + 1])

    extractor = AdaptiveChapterExtractor()

    print("=" * 70)
    print(">>> PANELFLOW ADAPTIVE CHAPTER EXTRACTOR CLI")
    print(f"Target URL:     {url}")
    print(f"Mode:           {'DOWNLOAD ASSETS' if should_download else 'INSPECT DRY-RUN'}")
    print(f"Loopback Permitted: {allow_loopback}")
    print("=" * 70)

    context = {"allow_loopback_for_testing": allow_loopback}
    result = await extractor.extract(url, context=context)

    print(f"\nFinal State:             {result.state.value}")
    print(f"Overall Confidence:      {result.overall_confidence*100:.1f}%")
    print(f"Completeness Score:      {result.completeness_score*100:.1f}%")
    print(f"Final Strategy:          {result.final_strategy or 'None'}")

    if result.site_fingerprint:
        print(f"Site Architecture:       {result.site_fingerprint.content_architecture}")
        print(f"Reader Container:        {result.site_fingerprint.reader_container_signature}")

    print("\nExtraction Strategy Attempts:")
    for att in result.attempts:
        status_sym = "[OK]" if att.status == "SUCCESS" else f"[{att.status}]"
        print(f"  {status_sym:<10} {att.strategy_id:<22} | Candidates: {att.candidate_count:<3} | Conf: {att.confidence*100:5.1f}% | Time: {att.elapsed_ms:.1f}ms")

    if result.manifest:
        print(f"\nDiscovered Pages:        {len(result.manifest.pages)}")
        print(f"Content Layout:          {result.manifest.content_layout.value}")
        print("\nFirst 5 Sample Pages:")
        for p in result.manifest.pages[:5]:
            dim_str = f"({p.width}x{p.height})" if p.width and p.height else ""
            print(f"  Page {p.sequence:02d}: {p.suggested_filename:<15} {dim_str:<12} -> {p.resolved_url}")

        if should_download:
            print(f"\nInitiating resumable download to {out_dir}...")
            dl_res = await extractor.download(
                manifest=result.manifest,
                output_dir=out_dir,
                progress_cb=lambda pct, msg: print(f"  [{pct*100:5.1f}%] {msg}"),
                allow_loopback_for_testing=allow_loopback,
            )
            print(f"\nDownload Finished:")
            print(f"  Status:     {dl_res['status']}")
            print(f"  Downloaded: {dl_res['downloaded']}")
            print(f"  Resumed:    {dl_res['resumed']}")
            print(f"  Failed:     {dl_res['failed']}")
    elif result.error:
        print(f"\nExtraction Error Reason: {result.error}")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
