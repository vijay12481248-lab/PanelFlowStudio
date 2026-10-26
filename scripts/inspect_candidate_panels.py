import sys, os
sys.path.insert(0, '.')
from engine.database.session import SessionLocal
from engine.database.models import PanelRecord, TextRegionRecord

PROJECT_ID = '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e'
db = SessionLocal()

for seq in [1, 5, 6, 9, 12, 15, 20, 37, 39, 42]:
    p = db.query(PanelRecord).filter(PanelRecord.project_id == PROJECT_ID, PanelRecord.sequence == seq).first()
    if not p:
        continue
    t_regs = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == p.id).all()
    print(f"=== SEQ {seq:02d} ({p.id}) crop={p.crop_filename} dims=({p.width}x{p.height}) ===")
    for t in t_regs:
        txt = (t.corrected_text or t.raw_text or "").replace('\n', ' ')
        print(f"  bbox: [x={t.x}, y={t.y}, w={t.width}, h={t.height}] norm: [y={t.normalized_y:.3f}, h={t.normalized_height:.3f}] | text: \"{txt}\"")
db.close()
