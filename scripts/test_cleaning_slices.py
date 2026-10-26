import os, sys
from PIL import Image
import numpy as np

# Let's test border margin fill on the watermark boxes
ws = r"C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\projects\67e096cc-2e4f-4f40-9bb9-b6f99c297a9e\panels"
out_dir = r"scratch\crop_inspection\cleaned_test"
os.makedirs(out_dir, exist_ok=True)

# Test Seq 06
im6 = Image.open(os.path.join(ws, "panel_b4e0ec58-b0b3-47ae-a489-42f161c599a3.jpg"))
# Watermark is at x=1310..1920, y=5835..5985
# Sample the background color above y=5835 (e.g. y=5820..5830, x=1310..1920)
bg6 = np.array(im6.crop((1310, 5810, 1920, 5830))).mean(axis=(0,1)).astype(int)
print("Seq 06 sampled bg:", bg6)
# Paste a clean rectangle with bg6
im6_clean = im6.copy()
from PIL import ImageDraw
draw = ImageDraw.Draw(im6_clean)
draw.rectangle([1300, 5830, 1920, 6000], fill=tuple(bg6))
im6_clean.crop((1200, 5700, 1920, 6100)).save(os.path.join(out_dir, "seq06_cleaned_slice.jpg"))

# Test Seq 18
im18 = Image.open(os.path.join(ws, "panel_8642660b-7bfb-4e8d-93f3-230d82c61631.jpg"))
bg18 = np.array(im18.crop((1240, 730, 1845, 750))).mean(axis=(0,1)).astype(int)
print("Seq 18 sampled bg:", bg18)
im18_clean = im18.copy()
draw = ImageDraw.Draw(im18_clean)
draw.rectangle([1230, 750, 1847, 900], fill=tuple(bg18))
im18_clean.crop((1150, 700, 1847, 950)).save(os.path.join(out_dir, "seq18_cleaned_slice.jpg"))

# Test Seq 29
im29 = Image.open(os.path.join(ws, "panel_384386ed-ec18-4c48-80d4-25279a69e1b3.jpg"))
bg29 = np.array(im29.crop((1010, 3440, 1615, 3460))).mean(axis=(0,1)).astype(int)
print("Seq 29 sampled bg:", bg29)
im29_clean = im29.copy()
draw = ImageDraw.Draw(im29_clean)
draw.rectangle([1000, 3460, 1615, 3620], fill=tuple(bg29))
im29_clean.crop((950, 3400, 1615, 3650)).save(os.path.join(out_dir, "seq29_cleaned_slice.jpg"))

# Test Seq 05 at 7349
im5 = Image.open(os.path.join(ws, "panel_01bec5a7-d7c6-45c6-af40-0c46c64223f9.jpg"))
bg5 = np.array(im5.crop((0, 7330, 605, 7345))).mean(axis=(0,1)).astype(int)
print("Seq 05 sampled bg:", bg5)
im5_clean = im5.copy()
draw = ImageDraw.Draw(im5_clean)
draw.rectangle([0, 7345, 605, 7410], fill=tuple(bg5))
im5_clean.crop((0, 7300, 700, 7450)).save(os.path.join(out_dir, "seq05_cleaned_slice.jpg"))

print("Saved all cleaned test slices.")
