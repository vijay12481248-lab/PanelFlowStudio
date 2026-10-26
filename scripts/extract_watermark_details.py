import os, sys
sys.path.insert(0, '.')
from PIL import Image

ws = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels"
out_dir = r"scratch\crop_inspection\watermark_details"
os.makedirs(out_dir, exist_ok=True)

from engine.database.session import SessionLocal
from engine.database.models import PanelRecord

db = SessionLocal()

# Watermarks found:
# Seq 01: [1082, 2036, 319, 73] 'MANHUA', [1066, 2371] Patreon, [1066, 2512] Paypal
# Seq 05: global_y=101 banner, global_y=7349 [6, 1349, 596, 51]
# Seq 06: global_y=5835 [1318, 2835, 596, 51]
# Seq 09: [1318, 115, 596, 51]
# Seq 15: [4, 3497, 596, 51]
# Seq 18: [1249, 828, 596, 52]
# Seq 26: [3, 2675, 595, 51]
# Seq 29: [1017, 3539, 596, 51]
# Seq 39: [427, 1018, 994, 98]

panels_info = [
    (1, "panel_582722e5-41f3-4ec6-ad68-7e30f8424f09.jpg", [(1066, 2000, 800, 600)]),
    (5, "panel_01bec5a7-d7c6-45c6-af40-0c46c64223f9.jpg", [(0, 0, 1920, 400), (0, 7250, 800, 250)]),
    (6, "panel_b4e0ec58-b0b3-47ae-a489-42f161c599a3.jpg", [(1200, 5800, 720, 200)]),
    (9, "panel_fa9bae00-90f5-4404-8d27-41c5bb226aff.jpg", [(1200, 0, 720, 250)]),
    (15, "panel_6f279732-0a97-4b38-98db-fab547deea7a.jpg", [(0, 3450, 700, 169)]),
    (18, "panel_8642660b-7bfb-4e8d-93f3-230d82c61631.jpg", [(1200, 750, 647, 200)]),
    (26, "panel_eb4ea1e3-8d4a-4a53-aa51-75db220977c9.jpg", [(0, 2550, 700, 180)]),
    (29, "panel_384386ed-ec18-4c48-80d4-25279a69e1b3.jpg", [(950, 3450, 665, 200)]),
    (39, "panel_b1213445-5e79-4353-b2eb-276a6dad2381.jpg", [(350, 950, 1200, 300)]),
]

for seq, fname, bboxes in panels_info:
    im = Image.open(os.path.join(ws, fname))
    for i, bbox in enumerate(bboxes):
        x, y, w, h = bbox
        crop = im.crop((x, y, x + w, y + h))
        out_p = os.path.join(out_dir, f"seq_{seq:02d}_wm_{i}.jpg")
        crop.save(out_p, quality=90)
        print(f"Saved {out_p} ({w}x{h})")

db.close()
