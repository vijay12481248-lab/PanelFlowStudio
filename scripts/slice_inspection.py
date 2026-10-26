import os, sys
from PIL import Image

ws = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels"
out_dir = r"scratch\crop_inspection"

# Let's inspect Seq 01:
im1 = Image.open(os.path.join(ws, "panel_582722e5-41f3-4ec6-ad68-7e30f8424f09.jpg"))
# seq 1 is 1920x2609.
# Let's see slices: top 1800 px, bottom 800 px
im1.crop((0, 0, 1920, 1750)).thumbnail((600, 600))
im1.crop((0, 0, 1920, 1750)).save(os.path.join(out_dir, "seq_01_cropped_clean.jpg"), quality=85)
im1.crop((0, 1750, 1920, 2609)).save(os.path.join(out_dir, "seq_01_bottom_watermarks.jpg"), quality=85)

# Seq 05: 1920x12106
im5 = Image.open(os.path.join(ws, "panel_01bec5a7-d7c6-45c6-af40-0c46c64223f9.jpg"))
# Look at top 800 px:
im5.crop((0, 0, 1920, 600)).save(os.path.join(out_dir, "seq_05_top_banner.jpg"), quality=85)

# Seq 39: 1920x4413
im39 = Image.open(os.path.join(ws, "panel_b1213445-5e79-4353-b2eb-276a6dad2381.jpg"))
im39.crop((0, 0, 1920, 600)).save(os.path.join(out_dir, "seq_39_top_banner.jpg"), quality=85)

# Seq 09: 1920x3940
im9 = Image.open(os.path.join(ws, "panel_fa9bae00-90f5-4404-8d27-41c5bb226aff.jpg"))
im9.crop((0, 0, 1920, 600)).save(os.path.join(out_dir, "seq_09_top_banner.jpg"), quality=85)

print("Saved test slices.")
