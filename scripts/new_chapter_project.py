"""Create a project from a chapter URL and download its pages.

Usage: python scripts/new_chapter_project.py <chapter_url> "<title>" [series_title] [chapter_sequence]
The rights declaration is EXPLICIT_PERMISSION: only run this for chapters you hold permission to use.
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.acquisition.adapters.registry import get_default_registry  # noqa: E402
from engine.database.models import PageRecord  # noqa: E402
from engine.database.session import SessionLocal  # noqa: E402
from engine.projects.service import project_service  # noqa: E402


async def main(url, title, series, seq):
    meta = {"series_title": series, "chapter_sequence": float(seq)} if series else {}
    with SessionLocal() as db:
        rec = project_service.create_project(db, title, "AUTHORIZED_WEB", "EXPLICIT_PERMISSION", source_url=url,
                                             source_metadata=meta, license_info="Permission held by the user")
        pid = rec.id
        print("PROJECT", pid, flush=True)
        job_id = project_service.start_acquisition_job(db, pid, get_default_registry())
    print("JOB", job_id, flush=True)
    while True:
        await asyncio.sleep(3)
        with SessionLocal() as db:
            rows = db.query(PageRecord).filter(PageRecord.project_id == pid).all()
            if rows:
                print("PAGES", len(rows), {s: sum(r.status == s for r in rows) for s in {r.status for r in rows}}, flush=True)
                break
    with SessionLocal() as db:
        project_service.confirm_acquisition(db, pid)
    print("ACQUIRED", pid, flush=True)


if __name__ == "__main__":
    a = sys.argv
    t0 = time.time()
    asyncio.run(main(a[1], a[2], a[3] if len(a) > 3 else "", a[4] if len(a) > 4 else 0))
    print(f"elapsed {time.time() - t0:.0f}s")
