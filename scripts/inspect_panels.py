import sys
sys.path.insert(0, '.')
from engine.database.session import SessionLocal
from engine.database.models import PanelRecord, TextRegionRecord

db = SessionLocal()
PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
panels = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID).order_by(PanelRecord.sequence.asc()).all()
print(f"Total panels in DB: {len(panels)}")

for p in panels:
    t_regs = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == p.id).all()
    texts = [(t.corrected_text or t.raw_text or "").strip() for t in t_regs if (t.corrected_text or t.raw_text)]
    print(f"Seq: {p.sequence:02d} | ID: {p.id} | Crop: {p.crop_filename} | Type: {p.panel_type}")
    if texts:
        print(f"   Texts: {' // '.join(texts[:3])}")
db.close()
