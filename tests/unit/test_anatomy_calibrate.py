import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("anatomy_calibrate", ROOT / "tools" / "anatomy" / "calibrate.py")
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)


def row(expected, confirmed=(), suspected=(), status="clean"):
    return {"id": "x", "expected": list(expected), "confirmed": list(confirmed), "suspected": list(suspected), "status": status}


def test_metrics_recall_false_alarms_and_unverified():
    rows = [row(["extra_arms"], confirmed=["extra_arms"], status="defects"),
            row(["duplicate_object", "pose_missing|two_hands"], confirmed=["duplicate_object"], suspected=["pose_missing|two_hands"], status="defects"),
            row([], confirmed=["stray_text"], status="defects"), row([]), row([], status="unverified"), row([])]
    m = cal.metrics(rows)
    assert m["recall_confirmed"] == round(2 / 3, 3) and m["recall_confirmed_or_suspected"] == 1.0
    assert m["clean_pictures"] == 4 and m["false_alarm_pictures"] == 1 and m["false_alarms_per_10_clean"] == 2.5
    assert m["unverified_share"] == round(1 / 6, 3)


def test_the_committed_labels_are_well_formed_and_mark_their_source():
    labels = json.loads((ROOT / "tests" / "data" / "anatomy_labels.json").read_text(encoding="utf-8"))
    assert len(labels) >= 64 and all({"id", "file", "model", "prompt", "people", "expected", "source"} <= set(e) for e in labels)
    assert any(e["expected"] for e in labels) and any(e["expected"] == [] for e in labels) and any(e["expected"] is None for e in labels)
    assert all(e["source"].startswith(("agent-", "owner-")) for e in labels)


def test_metrics_break_recall_down_by_defect_kind():
    rows = [row(["extra_hands"], confirmed=["extra_hands"], status="defects"), row(["extra_hands"], suspected=["extra_hands"]),
            row(["pose_missing|hands_on_knees"]), row(["pose_missing|two_hands"], suspected=["pose_missing|two_hands"])]
    k = cal.metrics(rows)["by_kind"]
    assert k["extra_hands"] == {"expected": 2, "confirmed": 1, "suspected": 1}
    assert k["pose_missing"] == {"expected": 2, "confirmed": 0, "suspected": 1}
