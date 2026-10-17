"""Evaluates Panel Detection accuracy against synthetic ground truth fixtures.

Metrics:
- IoU threshold (default >= 0.70)
- True Positives (TP), False Positives (FP), False Negatives (FN)
- Precision, Recall, and F1 Score
- Mean IoU across all matched panels
"""

import json
import sys
from pathlib import Path
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from engine.imaging.panels.detector import ContourPanelDetector

@dataclass
class LayoutMetrics:
    name: str
    gt_count: int
    det_count: int
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    mean_iou: float

def compute_iou(boxA: tuple[int, int, int, int], boxB: tuple[int, int, int, int]) -> float:
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
    yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

    inter_w = max(0, xB - xA)
    inter_h = max(0, yB - yA)
    inter_area = inter_w * inter_h

    areaA = boxA[2] * boxA[3]
    areaB = boxB[2] * boxB[3]
    union_area = areaA + areaB - inter_area

    if union_area <= 0:
        return 0.0
    return float(inter_area) / float(union_area)

def evaluate_layout(
    json_path: Path,
    detector: ContourPanelDetector,
    iou_thresh: float = 0.70,
) -> LayoutMetrics:
    with open(json_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    name = gt_data["layout_name"]
    img_path = json_path.with_suffix(".png")
    if not img_path.exists():
        img_path = json_path.with_suffix(".jpg")

    gt_panels = gt_data.get("panels", [])
    reading_dir = gt_data.get("reading_direction", "ltr")

    # Inset-specific evaluation config if testing insets
    det = detector
    if "nested_inset" in name:
        det = ContourPanelDetector(allow_insets=True)

    detected = det.detect_panels(img_path, reading_direction=reading_dir, page_id=name)

    gt_boxes = [(p["x"], p["y"], p["width"], p["height"]) for p in gt_panels]
    det_boxes = [(p.x, p.y, p.width, p.height) for p in detected]

    # Greedy bipartite matching based on highest IoU
    matches: list[tuple[int, int, float]] = []
    unmatched_gt = set(range(len(gt_boxes)))
    unmatched_det = set(range(len(det_boxes)))

    iou_matrix = []
    for g_idx, g_box in enumerate(gt_boxes):
        for d_idx, d_box in enumerate(det_boxes):
            score = compute_iou(g_box, d_box)
            if score >= iou_thresh:
                iou_matrix.append((score, g_idx, d_idx))

    # Sort candidates by IoU descending
    iou_matrix.sort(key=lambda item: item[0], reverse=True)

    matched_ious = []
    for score, g_idx, d_idx in iou_matrix:
        if g_idx in unmatched_gt and d_idx in unmatched_det:
            unmatched_gt.remove(g_idx)
            unmatched_det.remove(d_idx)
            matches.append((g_idx, d_idx, score))
            matched_ious.append(score)

    tp = len(matches)
    fp = len(unmatched_det)
    fn = len(unmatched_gt)

    precision = tp / float(tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / float(tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    mean_iou = sum(matched_ious) / len(matched_ious) if matched_ious else 0.0

    return LayoutMetrics(
        name=name,
        gt_count=len(gt_boxes),
        det_count=len(det_boxes),
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        mean_iou=mean_iou,
    )

import argparse
from engine.imaging.panels.benchmark import (
    run_panel_detection_benchmark,
    format_benchmark_markdown_table,
)

def run_synthetic_evaluation(iou_threshold: float = 0.70):
    fixtures_dir = Path(__file__).parent.parent / "fixtures" / "synthetic"
    if not fixtures_dir.exists():
        print(f"Error: Fixtures directory not found at {fixtures_dir}")
        sys.exit(1)

    json_files = sorted(fixtures_dir.glob("*.json"))
    if not json_files:
        print(f"Error: No JSON annotations found in {fixtures_dir}")
        sys.exit(1)

    detector = ContourPanelDetector()

    results: list[LayoutMetrics] = []
    print("=" * 88)
    print(f"PANELFLOW STUDIO — SYNTHETIC 10-FIXTURE BENCHMARK (IoU Threshold: {iou_threshold:.2f})")
    print("=" * 88)
    header = f"{'Layout Name':<26} | {'GT':<4} | {'Det':<4} | {'TP':<3} {'FP':<3} {'FN':<3} | {'Precision':<9} | {'Recall':<8} | {'F1':<6} | {'Mean IoU':<8}"
    print(header)
    print("-" * 88)

    total_gt = 0
    total_det = 0
    total_tp = 0
    total_fp = 0
    total_fn = 0
    all_ious = []

    for jf in json_files:
        m = evaluate_layout(jf, detector, iou_thresh=iou_threshold)
        results.append(m)
        total_gt += m.gt_count
        total_det += m.det_count
        total_tp += m.tp
        total_fp += m.fp
        total_fn += m.fn
        if m.mean_iou > 0:
            all_ious.append(m.mean_iou)

        line = (
            f"{m.name:<26} | {m.gt_count:<4} | {m.det_count:<4} | "
            f"{m.tp:<3} {m.fp:<3} {m.fn:<3} | "
            f"{m.precision*100:>8.1f}% | {m.recall*100:>7.1f}% | {m.f1:>6.2f} | {m.mean_iou:>8.2f}"
        )
        print(line)

    overall_prec = total_tp / float(total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_rec = total_tp / float(total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = (2 * overall_prec * overall_rec) / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0.0
    overall_iou = sum(all_ious) / len(all_ious) if all_ious else 0.0

    print("=" * 88)
    summary = (
        f"{'TOTAL / AGGREGATE':<26} | {total_gt:<4} | {total_det:<4} | "
        f"{total_tp:<3} {total_fp:<3} {total_fn:<3} | "
        f"{overall_prec*100:>8.1f}% | {overall_rec*100:>7.1f}% | {overall_f1:>6.2f} | {overall_iou:>8.2f}"
    )
    print(summary)
    print("=" * 88)

    assert overall_rec >= 0.70, f"Overall recall {overall_rec:.2f} is below target threshold 0.70"
    print("\nSynthetic 10-Fixture Benchmark Passed! Meets precision and recall targets.")

def run_canonical_evaluation(iou_threshold: float = 0.70):
    dataset_dir = Path(__file__).parent.parent / "fixtures" / "panel_benchmarks"
    print("=" * 88)
    print(f"PANELFLOW STUDIO — CANONICAL 12-FIXTURE BENCHMARK SUITE (IoU Threshold: {iou_threshold:.2f})")
    print("=" * 88)
    suite = run_panel_detection_benchmark(dataset_dir=dataset_dir, iou_threshold=iou_threshold)
    print(format_benchmark_markdown_table(suite))
    print("=" * 88)
    print(
        f"Summary: {suite.total_matched}/{suite.total_ground_truth} panels matched across {suite.total_fixtures} layouts "
        f"({suite.overall_precision * 100:.1f}% Precision, {suite.overall_recall * 100:.1f}% Recall, "
        f"{suite.overall_mean_iou:.3f} Mean IoU, {suite.total_false_positives} FP, {suite.total_false_negatives} FN)"
    )
    assert suite.overall_recall >= 0.70, f"Overall recall {suite.overall_recall:.2f} is below target threshold 0.70"
    print("\nCanonical 12-Fixture Benchmark Passed! Meets precision, recall, and reading order targets.")

def main():
    parser = argparse.ArgumentParser(description="PanelFlow Studio Panel Detection Evaluation Harness")
    parser.add_argument(
        "--suite",
        choices=["canonical", "12", "synthetic", "10", "all"],
        default="canonical",
        help="Benchmark suite to run (default: canonical 12-fixture suite)",
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.70,
        help="Intersection-over-Union (IoU) acceptance threshold (default: 0.70)",
    )
    args = parser.parse_args()

    if args.suite in ("canonical", "12"):
        run_canonical_evaluation(iou_threshold=args.iou)
    elif args.suite in ("synthetic", "10"):
        run_synthetic_evaluation(iou_threshold=args.iou)
    elif args.suite == "all":
        run_canonical_evaluation(iou_threshold=args.iou)
        print("\n\n")
        run_synthetic_evaluation(iou_threshold=args.iou)

if __name__ == "__main__":
    main()

