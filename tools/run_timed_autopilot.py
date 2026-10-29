"""Run the real application pipeline with a fresh video and recorded stage timings."""
import argparse
import asyncio
import json
import logging
import sqlite3
import time
from pathlib import Path

from engine.config.settings import settings
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord
from engine.pipeline.autopilot import AutoPilotRunner


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--regenerate-story", action="store_true")
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.db_file_path) as source, sqlite3.connect(out / "before-run.db") as backup:
        source.backup(backup)
    with SessionLocal() as db:
        project = db.get(ProjectRecord, args.project_id)
        (out / "before-settings.json").write_text(json.dumps(project.settings, indent=2), encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                        handlers=[logging.FileHandler(out / "pipeline.log", encoding="utf-8")])
    runner = AutoPilotRunner(args.project_id, {"skip_existing_stages": True, "force_render": True,
                                              "target_profile": "standard_1080p", "video_only": True,
                                              "regenerate_story": args.regenerate_story})
    start = time.monotonic()
    task = asyncio.create_task(runner.execute())
    runner._task = task
    while not task.done():
        status = runner.snapshot().model_dump()
        status["wall_elapsed_sec"] = round(time.monotonic()-start, 3)
        (out / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        await asyncio.sleep(1)
    await task
    status = runner.snapshot().model_dump()
    status["wall_elapsed_sec"] = round(time.monotonic()-start, 3)
    (out / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
