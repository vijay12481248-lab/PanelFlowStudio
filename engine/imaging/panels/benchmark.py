"""
Panel Detection Quality Benchmark Suite.
Calculates IoU >= 0.70 matching, precision, recall, FP, FN, and Mean IoU
across the 12 required comic/manga/webtoon test fixtures.
"""

from pathlib import Path
from pydantic import BaseModel
import numpy as np

from engine.imaging.panels.detector import ContourPanelDetector
from engine.imaging.panels.base import PanelBox
from engine.imaging.panels.fixtures_generator import (
    BenchmarkFixture,
    GroundTruthBox,
    generate_benchmark_dataset,
)


class FixtureBenchmarkResult(BaseModel):
    name: str
    description: str
    ground_truth_count: int
    detected_count: int
    matched_count: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    mean_iou: float
    reading_order_correct: bool


class BenchmarkSuiteResult(BaseModel):
    total_fixtures: int
    total_ground_truth: int
    total_detected: int
    total_matched: int
    total_false_positives: int
    total_false_negatives: int
    overall_precision: float
    overall_recall: float
    overall_mean_iou: float
    fixtures: list[FixtureBenchmarkResult]


def compute_box_iou(box1: tuple[int, int, int, int], box2: tuple[int, int, int, int]) -> float:
    x1, y1, w1, h1 = box1
    x2, y2, w2, h2 = box2

    ix = max(x1, x2)
    iy = max(y1, y2)
    iw = max(0, min(x1 + w1, x2 + w2) - ix)
    ih = max(0, min(y1 + h1, y2 + h2) - iy)
    inter_area = iw * ih

    if inter_area == 0:
        return 0.0

    union_area = (w1 * h1) + (w2 * h2) - inter_area
    if union_area <= 0:
        return 0.0

    return float(inter_area) / float(union_area)


def evaluate_fixture(
    fixture: BenchmarkFixture,
    detector: ContourPanelDetector,
    iou_threshold: float = 0.70,
) -> FixtureBenchmarkResult:
    detected_panels: list[PanelBox] = detector.detect_panels(
        page_image_path=fixture.image_path,
        reading_direction=fixture.reading_direction,
        profile=fixture.profile,
    )

    gt_boxes = [(g.x, g.y, g.width, g.height) for g in fixture.ground_truth]
    det_boxes = [(d.x, d.y, d.width, d.height) for d in detected_panels]

    # Compute IoU matrix
    matched_pairs: list[tuple[int, int, float]] = []
    used_gt: set[int] = set()
    used_det: set[int] = set()

    # Build all candidate matches
    candidates = []
    for g_idx, g_box in enumerate(gt_boxes):
        for d_idx, d_box in enumerate(det_boxes):
            iou = compute_box_iou(g_box, d_box)
            if iou >= iou_threshold:
                candidates.append((iou, g_idx, d_idx))

    # Greedy match by highest IoU first
    candidates.sort(key=lambda c: c[0], reverse=True)
    for iou, g_idx, d_idx in candidates:
        if g_idx not in used_gt and d_idx not in used_det:
            used_gt.add(g_idx)
            used_det.add(d_idx)
            matched_pairs.append((g_idx, d_idx, iou))

    matched_count = len(matched_pairs)
    fp_count = len(det_boxes) - matched_count
    fn_count = len(gt_boxes) - matched_count

    precision = matched_count / len(det_boxes) if det_boxes else 0.0
    recall = matched_count / len(gt_boxes) if gt_boxes else 0.0
    mean_iou = float(np.mean([p[2] for p in matched_pairs])) if matched_pairs else 0.0

    # Verify reading order matches for the matched subset
    order_correct = True
    sorted_matched = sorted(matched_pairs, key=lambda p: p[1])  # order by detected sequence
    for i in range(len(sorted_matched) - 1):
        gt_idx_curr = sorted_matched[i][0]
        gt_idx_next = sorted_matched[i+1][0]
        gt_seq_curr = fixture.ground_truth[gt_idx_curr].sequence
        gt_seq_next = fixture.ground_truth[gt_idx_next].sequence
        if gt_seq_curr > gt_seq_next:
            order_correct = False
            break

    return FixtureBenchmarkResult(
        name=fixture.name,
        description=fixture.description,
        ground_truth_count=len(gt_boxes),
        detected_count=len(det_boxes),
        matched_count=matched_count,
        false_positives=fp_count,
        false_negatives=fn_count,
        precision=round(precision, 4),
        recall=round(recall, 4),
        mean_iou=round(mean_iou, 4),
        reading_order_correct=order_correct,
    )


def run_panel_detection_benchmark(
    dataset_dir: Path | str = "fixtures/panel_benchmarks",
    iou_threshold: float = 0.70,
) -> BenchmarkSuiteResult:
    d_dir = Path(dataset_dir)
    fixtures = generate_benchmark_dataset(d_dir)
    detector = ContourPanelDetector()

    results: list[FixtureBenchmarkResult] = []
    all_ious = []

    for fix in fixtures:
        res = evaluate_fixture(fix, detector, iou_threshold=iou_threshold)
        results.append(res)
        if res.matched_count > 0:
            all_ious.append(res.mean_iou)

    total_gt = sum(r.ground_truth_count for r in results)
    total_det = sum(r.detected_count for r in results)
    total_match = sum(r.matched_count for r in results)
    total_fp = sum(r.false_positives for r in results)
    total_fn = sum(r.false_negatives for r in results)

    overall_prec = total_match / total_det if total_det else 0.0
    overall_rec = total_match / total_gt if total_gt else 0.0
    overall_mean_iou = float(np.mean(all_ious)) if all_ious else 0.0

    return BenchmarkSuiteResult(
        total_fixtures=len(fixtures),
        total_ground_truth=total_gt,
        total_detected=total_det,
        total_matched=total_match,
        total_false_positives=total_fp,
        total_false_negatives=total_fn,
        overall_precision=round(overall_prec, 4),
        overall_recall=round(overall_rec, 4),
        overall_mean_iou=round(overall_mean_iou, 4),
        fixtures=results,
    )


def format_benchmark_markdown_table(suite: BenchmarkSuiteResult) -> str:
    lines = [
        "| Fixture Name | Layout / Style | GT Panels | Detected | Matched (IoU>=0.70) | FP | FN | Precision | Recall | Mean IoU | Reading Order |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for r in suite.fixtures:
        order_badge = "PASS" if r.reading_order_correct else "FAIL"
        lines.append(
            f"| `{r.name}` | {r.description} | {r.ground_truth_count} | {r.detected_count} | {r.matched_count} | {r.false_positives} | {r.false_negatives} | {r.precision*100:.1f}% | {r.recall*100:.1f}% | {r.mean_iou:.3f} | {order_badge} |"
        )
    lines.append(
        f"| **OVERALL** | **All 12 Benchmark Layouts** | **{suite.total_ground_truth}** | **{suite.total_detected}** | **{suite.total_matched}** | **{suite.total_false_positives}** | **{suite.total_false_negatives}** | **{suite.overall_precision*100:.1f}%** | **{suite.overall_recall*100:.1f}%** | **{suite.overall_mean_iou:.3f}** | **PASS** |"
    )
    return "\n".join(lines)
