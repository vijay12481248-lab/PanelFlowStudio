import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord, OCRRecord

db = SessionLocal()
p = db.query(ProjectRecord).filter(ProjectRecord.id == 'a4e8115d-1e24-4a23-88b5-ecc72941bc8f').first()
print("Project title:", p.title)

panels = db.query(PanelRecord).filter(PanelRecord.project_id == p.id).order_by(PanelRecord.sequence).all()
print(f"Total panels in DB: {len(panels)}")

for idx, pnl in enumerate(panels):
    ocr = db.query(OCRRecord).filter(OCRRecord.panel_id == pnl.id).first()
    txt = ocr.full_text.strip() if ocr and ocr.full_text else ""
    print(f"Panel #{pnl.sequence} (Page {pnl.page_sequence}, id={pnl.id}):")
    print(f"  Crop: x={pnl.x}, y={pnl.y}, w={pnl.width}, h={pnl.height}")
    print(f"  OCR: {txt if txt else '(no text)'}")
