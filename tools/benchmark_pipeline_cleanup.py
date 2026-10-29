"""Measure repeated per-box I/O versus a single batch, using a lossless fixture."""
import json
import statistics
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw
from engine.imaging.redaction import blur_image_box, blur_image_boxes


def main():
    out = Path("output/pipeline-performance")
    out.mkdir(parents=True, exist_ok=True)
    boxes = [(100 + (i % 4) * 400, 100 + (i // 4) * 240, 300, 100) for i in range(12)]
    times = {"sequential": [], "batched": []}
    with TemporaryDirectory() as temporary:
        directory = Path(temporary) / "panels"
        directory.mkdir()
        original = Image.new("RGB", (1920, 1080), "white")
        draw = ImageDraw.Draw(original)
        for x, y, w, h in boxes:
            draw.rectangle((x, y, x+w, y+h), fill="black")
            draw.text((x+5, y+5), "Read at example.com", fill="white")
        for repeat in range(3):
            images = {}
            for mode in ("sequential", "batched"):
                path = directory / f"{mode}-{repeat}.png"
                original.save(path)
                start = time.perf_counter()
                if mode == "sequential":
                    for box in boxes:
                        blur_image_box(path, *box, feather=0)
                else:
                    blur_image_boxes(path, boxes, feather=0)
                times[mode].append(time.perf_counter()-start)
                with Image.open(path) as image:
                    images[mode] = image.tobytes()
            assert images["sequential"] == images["batched"]
    before, after = (statistics.median(times[mode]) for mode in ("sequential", "batched"))
    report = {"scope": "12 blur regions on a 1920x1080 PNG; includes backup and disk I/O, excludes OCR",
              "before_sec": before, "after_sec": after, "speedup": before/after,
              "pixel_bytes_identical": True, "runs": times}
    (out / "cleanup-benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
