import sys, os, json
sys.path.insert(0, '.')
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
db = SessionLocal()
proj = db.query(ProjectRecord).filter(ProjectRecord.id == PROJECT_ID).first()
state = (proj.settings or {}).get('story_editor_state', {})
scenes = state.get('scenes', [])
print(f"Total scenes: {len(scenes)}")

# Map panel_id to seq
panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID).all()
p_map = {p.id: p.sequence for p in panels}

for i, s in enumerate(scenes):
    s_id = s.get('id')
    title = s.get('title')
    dur = s.get('duration_sec')
    layers = s.get('layers', [])
    print(f"\nScene {i+1} [{s_id}] '{title}' duration: {dur}s | layers: {len(layers)}")
    for l_idx, l in enumerate(layers):
        p_id = l.get('source_panel_id')
        seq = p_map.get(p_id, '?')
        start = l.get('start_offset_sec')
        ldur = l.get('duration_sec')
        print(f"   Layer {l_idx+1}: Seq {seq} ({p_id[:8]}) start={start}s dur={ldur}s")

db.close()
