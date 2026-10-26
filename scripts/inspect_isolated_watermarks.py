import os, sys
from PIL import Image

ws = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels"
out_dir = r"scratch\crop_inspection\isolated_watermarks"
os.makedirs(out_dir, exist_ok=True)

# 1. Seq 05: y=7349, x=6..602
im5 = Image.open(os.path.join(ws, "panel_01bec5a7-d7c6-45c6-af40-0c46c64223f9.jpg"))
im5.crop((0, 7200, 1920, 7500)).save(os.path.join(out_dir, "seq05_at_7349.jpg"))

# 2. Seq 06: y=5835, x=1318..1914
im6 = Image.open(os.path.join(ws, "panel_b4e0ec58-b0b3-47ae-a489-42f161c599a3.jpg"))
im6.crop((0, 5700, 1920, 6000)).save(os.path.join(out_dir, "seq06_at_5835.jpg"))

# 3. Seq 18: y=756..880, x=1249..1845
im18 = Image.open(os.path.join(ws, "panel_8642660b-7bfb-4e8d-93f3-230d82c61631.jpg"))
im18.crop((0, 650, 1920, 950)).save(os.path.join(out_dir, "seq18_at_800.jpg"))

# 4. Seq 29: y=3467..3590, x=1017..1613
im29 = Image.open(os.path.join(ws, "panel_384386ed-ec18-4c48-80d4-25279a69e1b3.jpg"))
im29.crop((0, 3350, 1615, 3650)).save(os.path.join(out_dir, "seq29_at_3500.jpg"))

print("Saved isolated watermark slices.")
