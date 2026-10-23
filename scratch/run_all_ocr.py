import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.ocr.providers.registry import get_default_ocr_registry
from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord

db = SessionLocal()
p = db.query(ProjectRecord).filter(ProjectRecord.id == 'a4e8115d-1e24-4a23-88b5-ecc72941bc8f').first()
ws = Path(p.workspace_path)
eng = get_default_ocr_registry().get_engine('windows_media')
panels = db.query(PanelRecord).filter(PanelRecord.project_id == p.id).order_by(PanelRecord.sequence).all()

extracted = {}
for pnl in panels:
    crop_p = ws / 'panels' / pnl.crop_filename
    if crop_p.exists():
        try:
            res = eng.extract_text(crop_p, pnl.id)
            txt = res.full_text.strip()
            if txt:
                print(f"Panel #{pnl.sequence}: {txt}")
                extracted[pnl.sequence] = txt
        except Exception as e:
            pass

print(f"Total panels with text: {len(extracted)} / {len(panels)}")
