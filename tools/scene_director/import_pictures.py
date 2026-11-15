"""Load the pictures under output/Original_Scenes (baseline raw + director, earlier runs) into the REAL app database as pending Scene reviews, then run both judges.

  .venv\\Scripts\\python.exe -u tools/scene_director/import_pictures.py [--no-judge] [--limit N]

Needs Ollama (judge A) and ComfyUI started with --disable-dynamic-vram (judge B, the app's own launch flags). Safe to run again: pictures that already have a run are
skipped, and runs whose judging failed are judged again. A copy of the database is made first (<app data>/database/backups/).
"""
import argparse
import asyncio
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.config.settings import settings  # noqa: E402
from engine.database.models import ProjectRecord  # noqa: E402
from engine.database.session import SessionLocal, ensure_scene_fts  # noqa: E402
from engine.llm.registry import llm_registry  # noqa: E402
from engine.original import scene_import, scene_job  # noqa: E402
from engine.projects.service import project_service  # noqa: E402

PROJECT_TITLE = "Scene Director"  # the title the Scene page looks for (apps/desktop/src/features/scene/ScenePage.tsx)


def backup_database() -> Path:
    src = settings.app_data_dir / "database" / "panelflow.db"
    dest_dir = src.parent / "backups"
    dest_dir.mkdir(exist_ok=True)
    dest = dest_dir / f"panelflow_before_scene_import_{time.strftime('%Y%m%d_%H%M%S')}.db"
    with sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True) as a, sqlite3.connect(dest) as b:
        a.backup(b)
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-judge", action="store_true", help="only create the pending runs")
    ap.add_argument("--limit", type=int, default=0, help="only the first N pictures (a trial)")
    args = ap.parse_args()

    provider = llm_registry.get_ollama_provider()
    if not args.no_judge and not asyncio.run(provider.health_check()):
        print("Ollama is not reachable: start it, then run again.")
        return 2
    print("database backup:", backup_database(), flush=True)

    db = SessionLocal()
    ensure_scene_fts(db.get_bind())
    project = db.query(ProjectRecord).filter_by(title=PROJECT_TITLE).first()
    if project is None:
        project = project_service.create_project(db=db, title=PROJECT_TITLE, source_type="CHRONOFLOW_AI", rights_status="USER_OWNED")
        print("created project", PROJECT_TITLE, flush=True)
    items = scene_import.collect(scene_job.SCENE_ROOT, Path(__file__).with_name("baseline_briefs.json"))
    if args.limit:
        items = items[: args.limit]
    print(f"{len(items)} pictures to load into project {project.id}", flush=True)

    def judge(session, run_id, scene_type, image):
        scene_job.analyse(session, run_id, provider, SimpleNamespace(scene_type=scene_type), image)

    t0 = time.time()
    if args.no_judge:
        judge = lambda *a, **k: None  # noqa: E731
    out = scene_import.import_runs(db, project.id, items, scene_job.SCENE_ROOT, judge, progress=lambda m: print(m, flush=True))
    print(f"done in {time.time() - t0:.0f} s: {out}", flush=True)
    return 0 if out["judge_errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
