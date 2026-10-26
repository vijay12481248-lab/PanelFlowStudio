import sys
sys.path.insert(0, '.')
from pathlib import Path
from PIL import Image
from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine

engine = WindowsMediaOCREngine()
ws = Path(r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels")
out_dir = Path(r"scratch\crop_inspection")

for seq, fname in [(5, "panel_01bec5a7-d7c6-45c6-af40-0c46c64223f9.jpg"), (6, "panel_b4e0ec58-b0b3-47ae-a489-42f161c599a3.jpg")]:
    im = Image.open(ws / fname)
    w, h = im.size
    print(f"\nChecking Seq {seq} ({w}x{h}):")
    chunk_h = 3000
    for y in range(0, h, chunk_h):
        box = (0, y, w, min(y + chunk_h, h))
        chunk = im.crop(box)
        chunk_p = out_dir / f"chunk_{seq}_{y}.jpg"
        chunk.save(chunk_p, quality=85)
        res = engine.extract_text(chunk_p, f"{seq}_{y}")
        for r in res.regions:
            for kw in ['manhuaplus', 'manhua', 'discord', 'faster', 'paypal', 'patreon', 'read on', 'read first']:
                if kw in r.detected_text.lower():
                    print(f"  y_offset={y} + bbox={r.bbox} (global_y={y + r.bbox[1]}): '{r.detected_text}'")
