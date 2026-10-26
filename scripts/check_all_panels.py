import sys, os
sys.path.insert(0, '.')
from engine.database.session import SessionLocal
from engine.database.models import PanelRecord, TextRegionRecord

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
db = SessionLocal()
panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID).order_by(PanelRecord.sequence.asc()).all()

for p in panels:
    t_regs = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == p.id).all()
    txt = " // ".join([(t.corrected_text or t.raw_text or "").replace('\n', ' ').strip() for t in t_regs if (t.corrected_text or t.raw_text)])
    ratio = p.width / max(p.height, 1)
    # Check if banner-like or short height
    print(f"Seq {p.sequence:02d} | ID {p.id[:8]} | {p.width}x{p.height} (aspect: {ratio:.2f}) | {p.crop_filename}")
    if txt:
        print(f"    Text: {txt[:100]}...")
db.close()
