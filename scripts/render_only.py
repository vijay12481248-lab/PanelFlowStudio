"""Re-run only the motion and render stages for a project (keeps its narration and timeline).

Usage: python scripts/render_only.py <project_id>
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.pipeline.autopilot import AutoPilotRunner  # noqa: E402


async def main(project_id):
    runner = AutoPilotRunner(project_id, {"skip_existing_stages": True, "force_render": True, "video_only": True})
    for stage, fn in (("motion", lambda: runner._run_stage_motion(True)),
                      ("render", lambda: runner._run_stage_render("standard_1080p", False))):
        ok = await runner._execute_stage(stage, fn)
        for line in runner.logs:
            print(line)
        runner.logs.clear()
        if not ok:
            raise SystemExit(f"{stage} failed: {runner.error}")
    print("VIDEO", runner.result.get("output_mp4_path"))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
