import sys
sys.path.insert(0, '.')
from pathlib import Path
from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine
from engine.database.session import SessionLocal
from engine.database.models import PanelRecord

engine = WindowsMediaOCREngine()
ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels")

db = SessionLocal()
panels = db.query(PanelRecord).filter(PanelRecord.project_id == '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e').order_by(PanelRecord.sequence.asc()).all()

keywords = ['manhuaplus', 'manhua', 'discord', 'faster release', 'paypal', 'patreon', 'read on', 'read first']

for p in panels:
    img_path = ws / p.crop_filename
    res = engine.extract_text(img_path, p.id)
    matches = []
    for r in res.regions:
        for kw in keywords:
            if kw in r.detected_text.lower():
                matches.append((r.bbox, r.detected_text))
                break
    if matches:
        print(f"\nPanel Seq {p.sequence:02d} ({p.id}) size: {p.width}x{p.height}:")
        for bbox, txt in matches:
            print(f"   bbox={bbox}: '{txt}'")

db.close()
