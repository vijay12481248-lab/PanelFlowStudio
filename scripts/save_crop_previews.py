import os, sys
sys.path.insert(0, '.')
from PIL import Image

ws = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e"
panels_dir = os.path.join(ws, "panels")
out_dir = r"scratch\crop_inspection"
os.makedirs(out_dir, exist_ok=True)

from engine.database.session import SessionLocal
from engine.database.models import PanelRecord

db = SessionLocal()
for seq in [1, 5, 6, 9, 15, 20, 39, 42]:
    p = db.query(PanelRecord).filter(PanelRecord.project_id == '67e096cc-2e4f-4f40-9bb9-b6f99c297a9e', PanelRecord.sequence == seq).first()
    im = Image.open(os.path.join(panels_dir, p.crop_filename))
    # Save a resized version for inspection
    im_thumb = im.copy()
    im_thumb.thumbnail((800, 800))
    im_thumb.save(os.path.join(out_dir, f"seq_{seq:02d}_thumb.jpg"), quality=80)
    print(f"Saved seq_{seq:02d}_thumb.jpg, original size: {im.size}")
db.close()
