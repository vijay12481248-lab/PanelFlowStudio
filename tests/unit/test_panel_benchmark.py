from pathlib import Path
from engine.imaging.panels.benchmark import run_panel_detection_benchmark

def test_12_panel_detection_benchmarks(tmp_path: Path):
    benchmark_dir = tmp_path / "panel_benchmarks"
    suite = run_panel_detection_benchmark(dataset_dir=benchmark_dir, iou_threshold=0.70)

    assert suite.total_fixtures == 12
    assert suite.total_ground_truth == 45
    assert suite.total_detected == 45
    assert suite.total_matched == 45
    assert suite.total_false_positives == 0
    assert suite.total_false_negatives == 0
    assert suite.overall_precision >= 0.95
    assert suite.overall_recall >= 0.95
    assert suite.overall_mean_iou >= 0.90

    for fix in suite.fixtures:
        assert fix.matched_count == fix.ground_truth_count, f"Fixture {fix.name} failed match count"
        assert fix.reading_order_correct is True, f"Fixture {fix.name} reading order failed"
