import sys
import traceback

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.ocr.benchmark import run_ocr_benchmark

try:
    report = run_ocr_benchmark()
    print(f"Engine ID: {report.engine_id}")
    print(f"Total fixtures: {report.total_fixtures}")
    print(f"Mean CER: {report.mean_cer:.4f}, Mean WER: {report.mean_wer:.4f}, Mean Confidence: {report.mean_confidence:.3f}")
    for r in report.results:
        print(f"  [{r.fixture_name}] GT: {r.ground_truth} | OCR: {r.recognized_text} | CER: {r.cer:.4f} | WER: {r.wer:.4f} | Conf: {r.confidence}")
except Exception:
    traceback.print_exc()
    sys.exit(1)
