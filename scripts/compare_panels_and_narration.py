import sys, os
sys.path.insert(0, '.')
from engine.database.session import SessionLocal
from engine.database.models import PanelRecord, TextRegionRecord, ProjectRecord

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
db = SessionLocal()
panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID).order_by(PanelRecord.sequence.asc()).all()

print("=== PANELS AND THEIR TEXT ===")
for p in panels:
    t_regs = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == p.id).all()
    txt = ' // '.join([(t.corrected_text or t.raw_text or '').replace('\n', ' ').strip() for t in t_regs if (t.corrected_text or t.raw_text)])
    print(f"Seq {p.sequence:02d} [{p.id[:8]}]: {txt[:90]}")

proj = db.query(ProjectRecord).filter(ProjectRecord.id == PROJECT_ID).first()
state = (proj.settings or {}).get('story_editor_state', {})
clips = state.get('narration_clips', [])
print("\n=== NARRATION CLIPS ===")
for i, c in enumerate(clips):
    spk = c.get('speaker')
    dur = c.get('duration_sec')
    txt = c.get('text', '').replace('\n', ' ')
    print(f"Clip {i+1:02d} [{spk}] (dur={dur:.2f}s, start={c.get('start_time_sec', 0):.2f}s): {txt[:85]}")

db.close()
