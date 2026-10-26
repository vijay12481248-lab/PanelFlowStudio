import sys, os
from PIL import Image
import numpy as np

d = r"scratch\crop_inspection\isolated_watermarks"

files_and_boxes = [
    ("seq05_at_7349.jpg", (6, 149, 602, 200)),
    ("seq06_at_5835.jpg", (1318, 48, 1914, 179)),
    ("seq18_at_800.jpg", (1249, 106, 1845, 230)),
    ("seq29_at_3500.jpg", (1018, 105, 1614, 235)),
]

for fname, box in files_and_boxes:
    im = Image.open(os.path.join(d, fname))
    crop = im.crop(box)
    arr = np.array(crop)
    # Check pixels immediately bordering this box (top, bottom, left, right)
    print(f"\n{fname}: box={box}")
    print(f"  mean color: {arr.mean(axis=(0,1))}")
    print(f"  median color: {np.median(arr, axis=(0,1))}")
