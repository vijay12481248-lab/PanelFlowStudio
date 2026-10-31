"""Run the autopilot for one project from the command line, printing stage progress.

Usage: python scripts/run_autopilot.py <project_id> [--regenerate-story] [--force-render] [--package]
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pipeline.autopilot import AutoPilotRunner  # noqa: E402


async def main(project_id, args):
    runner = AutoPilotRunner(project_id, {
        "skip_existing_stages": True,
        "regenerate_story": "--regenerate-story" in args,
        "force_render": "--force-render" in args,
        "video_only": "--package" not in args,
    })
    task = asyncio.create_task(runner.execute())
    printed = 0
    while not task.done():
        await asyncio.sleep(5)
        for line in runner.logs[printed:]:
            print(line, flush=True)
        printed = len(runner.logs)
    await task
    for line in runner.logs[printed:]:
        print(line, flush=True)
    snap = runner.snapshot()
    print("STATUS", snap.status, snap.error or "", snap.result.get("output_mp4_path", ""), flush=True)
    return 0 if snap.status == "COMPLETED" else 1


if __name__ == "__main__":
    t0 = time.time()
    code = asyncio.run(main(sys.argv[1], sys.argv[2:]))
    print(f"elapsed {time.time() - t0:.0f}s")
    sys.exit(code)
