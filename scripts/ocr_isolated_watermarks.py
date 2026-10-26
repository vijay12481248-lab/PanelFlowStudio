import os, sys
sys.path.insert(0, '.')
from pathlib import Path
from PIL import Image
from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine

d = Path(r"scratch\crop_inspection\isolated_watermarks")
engine = WindowsMediaOCREngine()
for f in sorted(d.glob("*.jpg")):
    res = engine.extract_text(f, f.stem)
    print(f"=== {f.name} ===")
    for r in res.regions:
        print(f"  bbox={r.bbox}: '{r.detected_text}'")
