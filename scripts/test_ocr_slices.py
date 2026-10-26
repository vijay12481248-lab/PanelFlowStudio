import sys
sys.path.insert(0, '.')
from pathlib import Path
from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine

engine = WindowsMediaOCREngine()
for fname in ['seq_01_cropped_clean.jpg', 'seq_01_bottom_watermarks.jpg', 'seq_05_top_banner.jpg', 'seq_39_top_banner.jpg', 'seq_09_top_banner.jpg']:
    p = Path(r'scratch\crop_inspection') / fname
    res = engine.extract_text(p, 'test')
    print(f"=== {fname} ===")
    for r in res.regions:
        print(f"  bbox={r.bbox}: \"{r.detected_text}\"")
