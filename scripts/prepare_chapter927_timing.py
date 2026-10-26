import sys
from pathlib import Path
from sqlalchemy.orm.attributes import flag_modified

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord

PROJECT_ID = "098c6713-478b-4b77-917c-d2737215481b"

def main():
    db = SessionLocal()
    project = db.query(ProjectRecord).filter_by(id=PROJECT_ID).first()
    if not project:
        print("Project not found!")
        return

    panels = db.query(PanelRecord).filter_by(project_id=PROJECT_ID).order_by(PanelRecord.sequence).all()
    panel_map = {p.sequence: p.id for p in panels}
    print(f"Loaded {len(panels)} panels.")

    se_state = (project.settings or {}).get("story_editor_state") or {}
    scenes = se_state.get("scenes", [])
    if len(scenes) < 2:
        print("Expected at least 2 scenes in story_editor_state!")
        return

    # Scene 1: duration = 196.475s, 23 panels (Panels 1 to 23)
    sc1 = scenes[0]
    sc1_dur = float(sc1.get("duration_sec", 196.475))
    p_count1 = 23
    panel_dur1 = sc1_dur / p_count1
    sc1_layers = []

    for i in range(p_count1):
        seq = i + 1
        pid = panel_map.get(seq)
        start_off = round(i * panel_dur1, 3)
        dur = round(panel_dur1, 3)
        sc1_layers.append({
            "source_panel_id": pid,
            "start_offset_sec": start_off,
            "duration_sec": dur,
            "transform": {
                "x": 0.0,
                "y": 0.0,
                "scale": 1.0,
                "rotation": 0.0,
                "opacity": 1.0,
                "z_index": i + 1,
            },
            "motion_preset": "none",
        })
    sc1["layers"] = sc1_layers

    # Scene 2: duration = 281.894s, 23 panels (Panels 24 to 46)
    sc2 = scenes[1]
    sc2_dur = float(sc2.get("duration_sec", 281.894))
    p_count2 = 23
    panel_dur2 = sc2_dur / p_count2
    sc2_layers = []

    for i in range(p_count2):
        seq = 24 + i
        pid = panel_map.get(seq)
        start_off = round(i * panel_dur2, 3)
        dur = round(panel_dur2, 3)
        sc2_layers.append({
            "source_panel_id": pid,
            "start_offset_sec": start_off,
            "duration_sec": dur,
            "transform": {
                "x": 0.0,
                "y": 0.0,
                "scale": 1.0,
                "rotation": 0.0,
                "opacity": 1.0,
                "z_index": i + 1,
            },
            "motion_preset": "none",
        })
    sc2["layers"] = sc2_layers

    # Commit updated settings
    se_state["scenes"] = [sc1, sc2]
    new_settings = dict(project.settings or {})
    new_settings["story_editor_state"] = se_state
    project.settings = new_settings
    flag_modified(project, "settings")
    db.commit()

    print(f"Scene 1: {len(sc1_layers)} timed sequential layers (each {panel_dur1:.2f}s)")
    print(f"Scene 2: {len(sc2_layers)} timed sequential layers (each {panel_dur2:.2f}s)")
    print("Sequential layer timing successfully applied to Chapter 927!")

if __name__ == "__main__":
    main()
