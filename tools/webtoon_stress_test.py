import os
import sys
import time
import tracemalloc
from pathlib import Path
from PIL import Image, ImageDraw

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.imaging.panels.detector import ContourPanelDetector

def run_webtoon_stress_test(width: int = 1440, height: int = 30000, num_panels: int = 12):
    print(f"=== Webtoon Stress Test (Part 22) ===")
    print(f"Resolution: {width} x {height} px (~{(width * height) / 1_000_000:.1f} Megapixels)")
    print(f"Synthesizing {num_panels} vertical panels with gutters...")

    out_dir = Path(__file__).parent.parent / "fixtures" / "stress_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    img_path = out_dir / f"webtoon_stress_{width}x{height}.jpg"

    # Start memory monitoring
    tracemalloc.start()
    t0 = time.perf_counter()

    # Create synthetic webtoon image with white background
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    ground_truth = []
    # Calculate panel heights and gutters
    total_gutter_height = 800 * (num_panels + 1)
    available_panel_height = height - total_gutter_height
    avg_panel_height = available_panel_height // num_panels

    current_y = 400
    for i in range(num_panels):
        p_w = width - 160  # margin of 80px on each side
        p_h = avg_panel_height
        p_x = 80
        p_y = current_y

        # Draw panel border and background
        draw.rectangle([p_x, p_y, p_x + p_w, p_y + p_h], outline=(20, 20, 20), width=6, fill=(240, 240, 245))
        # Draw some internal content so it's not blank
        draw.line([p_x + 20, p_y + 20, p_x + p_w - 20, p_y + p_h - 20], fill=(180, 180, 190), width=3)
        draw.line([p_x + 20, p_y + p_h - 20, p_x + p_w - 20, p_y + 20], fill=(180, 180, 190), width=3)

        ground_truth.append({
            "sequence": i + 1,
            "bbox": [p_x, p_y, p_w, p_h]
        })
        current_y += p_h + 800

    img.save(img_path, "JPEG", quality=85)
    t_synth = time.perf_counter() - t0
    file_size_mb = os.path.getsize(img_path) / (1024 * 1024)
    print(f"Generated synthetic webtoon in {t_synth:.2f}s (File Size: {file_size_mb:.2f} MB)")

    # Run detection
    detector = ContourPanelDetector(min_area_ratio=0.005)
    t_detect_start = time.perf_counter()
    
    detected = detector.detect_panels(img_path, reading_direction="vertical")
    
    t_detect_end = time.perf_counter()
    detect_duration = t_detect_end - t_detect_start
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_ram_mb = peak_mem / (1024 * 1024)
    megapixels = (width * height) / 1_000_000
    throughput_mp_s = megapixels / detect_duration if detect_duration > 0 else 0

    print("\n--- Detection Results ---")
    print(f"Ground Truth Panels : {len(ground_truth)}")
    print(f"Detected Panels     : {len(detected)}")
    print(f"Execution Time      : {detect_duration:.2f} seconds")
    print(f"Throughput          : {throughput_mp_s:.2f} MP/s")
    print(f"Peak RAM Allocated  : {peak_ram_mb:.2f} MB")

    # Match bounding boxes
    matched = 0
    ious = []
    for gt in ground_truth:
        gx, gy, gw, gh = gt["bbox"]
        best_iou = 0.0
        for det in detected:
            dx, dy, dw, dh = det.x, det.y, det.width, det.height
            # Compute IoU
            ix1 = max(gx, dx)
            iy1 = max(gy, dy)
            ix2 = min(gx + gw, dx + dw)
            iy2 = min(gy + gh, dy + dh)
            iw = max(0, ix2 - ix1)
            ih = max(0, iy2 - iy1)
            inter = iw * ih
            union = (gw * gh) + (dw * dh) - inter
            iou = inter / union if union > 0 else 0.0
            if iou > best_iou:
                best_iou = iou
        ious.append(best_iou)
        if best_iou >= 0.70:
            matched += 1

    precision = (matched / len(detected)) * 100 if detected else 0
    recall = (matched / len(ground_truth)) * 100 if ground_truth else 0
    mean_iou = sum(ious) / len(ious) if ious else 0

    print(f"Matched Panels      : {matched}/{len(ground_truth)} ({recall:.1f}%)")
    print(f"Precision           : {precision:.1f}%")
    print(f"Recall              : {recall:.1f}%")
    print(f"Mean IoU            : {mean_iou:.3f}")
    print("-------------------------\n")

    # Clean up test fixture file
    if img_path.exists():
        img_path.unlink()
        try:
            out_dir.rmdir()
        except Exception:
            pass

    return {
        "width": width,
        "height": height,
        "megapixels": megapixels,
        "gt_panels": len(ground_truth),
        "detected_panels": len(detected),
        "matched_panels": matched,
        "precision": precision,
        "recall": recall,
        "mean_iou": mean_iou,
        "detect_duration_s": detect_duration,
        "throughput_mp_s": throughput_mp_s,
        "peak_ram_mb": peak_ram_mb,
    }

if __name__ == "__main__":
    run_webtoon_stress_test(width=1440, height=30000, num_panels=10)
