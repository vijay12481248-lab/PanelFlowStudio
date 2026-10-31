"""Edit flagged lines of a narration run held for review, approve it, voice it, then render the project.

Same path as the desktop review queue (engine.narration.review), followed by the autopilot motion + render stages.
Usage: python scripts/finish_narration_review.py <project_id> <run_id> <line_id>=<text> [<line_id>=<text> ...]
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.database.session import SessionLocal  # noqa: E402
from engine.narration import review  # noqa: E402
from engine.narration.bible.store import BibleStore  # noqa: E402
from engine.pipeline.autopilot import AutoPilotRunner  # noqa: E402


async def main(project_id, run_id, edits):
    with SessionLocal() as db:
        run_dir = review.resolve_run_dir(db, project_id, run_id)
    for line_id, text in edits.items():
        review.edit_line(run_dir, line_id, text, BibleStore())
        print("edited", line_id, "->", text)
    approval = review.approve(run_dir, BibleStore())
    print("approved; bible v", approval.bible.version)
    if approval.needs_continue:
        print("voiced and applied, script", await review.continue_after_approval(project_id, run_id))
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
    edits = dict(arg.split("=", 1) for arg in sys.argv[3:])
    asyncio.run(main(sys.argv[1], sys.argv[2], edits))
