"""Re-run panel detection + promotion cleanup for a project (use inside a sandbox: PANELFLOW_APP_DATA).

Usage: python scripts/panel_truth/redetect.py <project_id>
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from engine.config.settings import settings  # noqa: E402

REAL = Path.home() / "AppData/Local/PanelFlow Studio"
if settings.app_data_dir.resolve() == REAL.resolve() and "--real" not in sys.argv:
    raise SystemExit("Set PANELFLOW_APP_DATA to a sandbox folder first (see sandbox_project.py), or pass --real "
                     "after backing up the project.")

from engine.database.session import SessionLocal  # noqa: E402
from engine.projects.service import project_service  # noqa: E402


def main(project_id):
    with SessionLocal() as db:
        op = project_service.detect_panels_project(db, project_id, operation_only=True)
        result = asyncio.run(op(SimpleNamespace(is_cancelled=False), lambda f, m: print(f"{f:.0%} {m}")))
    print(result)


if __name__ == "__main__":
    main(sys.argv[1])
