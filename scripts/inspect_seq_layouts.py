import os, sys
from PIL import Image

ws = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels"

# Inspect Seq 09:
im9 = Image.open(os.path.join(ws, "panel_fa9bae00-90f5-4404-8d27-41c5bb226aff.jpg"))
print("Seq 09 size:", im9.size)
# Where is the story art in Seq 09?
# In Seq 09, text starts at y=401: "Uncle, here is the treasury..."
# So if we crop from y=170 to 3940, we remove the top watermark completely!

# Inspect Seq 39:
im39 = Image.open(os.path.join(ws, "panel_b1213445-5e79-4353-b2eb-276a6dad2381.jpg"))
print("Seq 39 size:", im39.size)
# What is above y=1018?
# Let's inspect Seq 39 y=0..1000 and y=1190..4413
