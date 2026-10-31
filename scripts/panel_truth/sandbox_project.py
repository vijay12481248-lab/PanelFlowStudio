"""Copy one project (DB rows + workspace) into an isolated app-data folder for end-to-end trials.

Usage: python scripts/panel_truth/sandbox_project.py <project_id> <sandbox_dir> [model_dir]
Then run engine code with PANELFLOW_APP_DATA=<sandbox_dir>; the real app data is never written.
"""
import shutil
import sqlite3
import sys
from pathlib import Path

REAL = Path.home() / "AppData/Local/PanelFlow Studio"


def main(project_id, sandbox, model=None):
    sandbox = Path(sandbox)
    if sandbox.resolve() == REAL.resolve():
        raise SystemExit("Refusing to use the real app data folder as a sandbox.")
    (sandbox / "database").mkdir(parents=True, exist_ok=True)
    db_path = sandbox / "database" / "panelflow.db"
    src = sqlite3.connect(f"file:{(REAL / 'database/panelflow.db').as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(db_path)
    src.backup(dst)
    src.close()
    (ws,) = dst.execute("select workspace_path from projects where id=?", (project_id,)).fetchone()
    new_ws = sandbox / "projects" / project_id
    if new_ws.exists():
        shutil.rmtree(new_ws)
    shutil.copytree(ws, new_ws)
    dst.execute("update projects set workspace_path=? where id=?", (str(new_ws), project_id))
    # Behave like a fresh chapter: an existing timeline protects its pages from re-detection.
    import json
    (raw,) = dst.execute("select settings from projects where id=?", (project_id,)).fetchone()
    data = json.loads(raw or "{}")
    for key in ("story_editor_state", "content_cleanup_report", "detected_promos"):
        data.pop(key, None)
    dst.execute("update projects set settings=? where id=?", (json.dumps(data), project_id))
    dst.execute("update panels set manually_modified=0, status='DETECTED' where project_id=? and status in "
                "('MANUAL','CONFIRMED')", (project_id,))
    dst.commit()
    for name in ("content-cleanup.json",):
        if (REAL / name).exists():
            shutil.copy2(REAL / name, sandbox / name)
    if model:
        target = sandbox / "models" / "panel_detector"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(model, target)
    print("sandbox ready:", sandbox, "workspace:", new_ws)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2] if len(a) > 2 else None)
