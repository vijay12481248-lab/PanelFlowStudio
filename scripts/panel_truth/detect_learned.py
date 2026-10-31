"""Run the strip detector over a ground-truth chapter; write panels/bubbles/promos in strip coordinates.

Usage: python scripts/panel_truth/detect_learned.py <truth.json> <model_dir> <out.json> [panel_thr]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).parent))
from engine.imaging.panels import strip_detector as sd  # noqa: E402
from render_strip_chunks import strip_pages  # noqa: E402


def main(truth_path, model, out_path, panel_thr=0.5):
    import json
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    pages = [sd.StripPage(str(i), path, y0, h) for i, (y0, path, h) in enumerate(strip_pages(truth["project_id"]))]
    sd.THRESHOLDS["panel"] = panel_thr
    t0 = time.time()
    result = sd.StripDetector(Path(model)).detect(pages)
    sd.save_debug(result, Path(out_path))
    print({k: len(getattr(result, k)) for k in ("panels", "bubbles", "promos")}, f"{time.time() - t0:.1f}s")


if __name__ == "__main__":
    a = sys.argv[1:]
    main(a[0], a[1], a[2], float(a[3]) if len(a) > 3 else 0.5)
