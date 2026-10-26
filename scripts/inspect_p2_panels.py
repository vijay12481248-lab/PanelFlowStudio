import sys, os
sys.path.insert(0, '.')
from engine.database.session import SessionLocal
from engine.database.models import PanelRecord, TextRegionRecord

db = SessionLocal()
PROJECT_ID_NEW = '682ba959-24e8-41d8-9cda-637a350b75c2'
panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID_NEW).order_by(PanelRecord.sequence.asc()).all()
print(f"Total panels in P2: {len(panels)}")

for p in panels:
    t_regs = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == p.id).all()
    txt = ' // '.join([(t.corrected_text or t.raw_text or '').replace('\n', ' ').strip() for t in t_regs if (t.corrected_text or t.raw_text)])
    aspect = p.width / max(1, p.height)
    print(f"Seq {p.sequence:02d} | page_y={p.y:5d} h={p.height:5d} | {p.width}x{p.height} (aspect: {aspect:.2f}) | {txt[:60]}")

db.close()
