import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord

db = SessionLocal()
p = db.query(ProjectRecord).filter(ProjectRecord.id == 'a4e8115d-1e24-4a23-88b5-ecc72941bc8f').first()
scenes = p.settings.get('story_editor_state', {}).get('scenes', [])

for idx, sc in enumerate(scenes):
    layers = sc.get('layers', [])
    panel_id = layers[0].get('source_panel_id') if layers else None
    pnl = db.query(PanelRecord).filter(PanelRecord.id == panel_id).first() if panel_id else None
    seq = pnl.sequence if pnl else 'none'
    start = sc.get('start_time_sec', 0)
    dur = sc.get('duration_sec', 0)
    print(f"Scene {idx+1} (start={start}s, dur={dur}s): Panel #{seq} (id={panel_id})")
