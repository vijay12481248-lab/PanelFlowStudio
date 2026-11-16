"""Measure the anatomy reviewer against the labelled pictures and print the gate verdict (docs/ANATOMY_REVIEW.md).

    .venv\\Scripts\\python.exe tools/anatomy/calibrate.py [--clean-sample 15] [--out output/anatomy_labels/calibration.json]

Needs Ollama (`qwen3.5:9b`) and ComfyUI started with `--disable-dynamic-vram` (the Qwen3-VL judge). Runs every picture with known defects and a fixed random sample of the
clean ones (one picture takes about a minute). Gate: recall on confirmed known defects >= 0.8 and at most 1 false alarm per 10 clean pictures.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.comfyui.edit_prompt import release_local_model  # noqa: E402
from engine.llm.registry import llm_registry  # noqa: E402
from engine.original.anatomy.review import review_picture  # noqa: E402
from engine.original.judges import default_judges  # noqa: E402

LABELS = ROOT / "tests" / "data" / "anatomy_labels.json"
PICTURES = ROOT / "output" / "anatomy_labels"
GATE_RECALL, GATE_FALSE_ALARMS_PER_10 = 0.8, 1.0


def key_of(defect) -> str:
    return f"{defect.kind}|{defect.pose}" if defect.pose else defect.kind


def metrics(rows: list[dict]) -> dict:
    found_c = found_any = expected_n = 0
    clean_rows = [r for r in rows if r["expected"] == []]
    for r in rows:
        for k in r["expected"]:
            expected_n += 1
            found_c += k in r["confirmed"]
            found_any += k in r["confirmed"] or k in r["suspected"]
    false_alarm_pictures = sum(1 for r in clean_rows if r["confirmed"])
    judged = [r for r in rows if r["status"] != "unverified"]
    return {"pictures": len(rows), "expected_defects": expected_n, "recall_confirmed": round(found_c / expected_n, 3) if expected_n else None,
            "recall_confirmed_or_suspected": round(found_any / expected_n, 3) if expected_n else None, "clean_pictures": len(clean_rows),
            "false_alarm_pictures": false_alarm_pictures,
            "false_alarms_per_10_clean": round(10 * false_alarm_pictures / len(clean_rows), 2) if clean_rows else None,
            "unverified_share": round(1 - len(judged) / len(rows), 3) if rows else None}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean-sample", type=int, default=15)
    ap.add_argument("--out", default=str(PICTURES / "calibration.json"))
    ap.add_argument("--only", default="", help="substring of the picture id, to run a few pictures")
    args = ap.parse_args()
    labels = [e for e in json.loads(LABELS.read_text(encoding="utf-8")) if e["expected"] is not None and args.only in e["id"]]
    defective = [e for e in labels if e["expected"]]
    clean = [e for e in labels if e["expected"] == []]
    random.Random(7).shuffle(clean)
    todo = defective + clean[:args.clean_sample]
    provider = llm_registry.get_ollama_provider()
    judges = default_judges(provider)
    print(f"judges: {[j.name for j in judges]}; {len(todo)} pictures ({len(defective)} defective, {min(len(clean), args.clean_sample)} clean)", flush=True)
    rows: list[dict] = []
    for i, e in enumerate(todo, 1):
        t0 = time.monotonic()
        report = asyncio.run(review_picture(judges, (PICTURES / e["file"]).read_bytes(), e["prompt"], between=release_local_model))
        row = {"id": e["id"], "expected": e["expected"], "status": report.status, "people": report.people, "judges": report.judges,
               "confirmed": [key_of(d) for d in report.confirmed], "suspected": [key_of(d) for d in report.suspected],
               "pose_skipped": report.pose_skipped, "seconds": round(time.monotonic() - t0, 1)}
        rows.append(row)
        print(f"[{i}/{len(todo)}] {e['id']}: expected {e['expected']} -> confirmed {row['confirmed']} suspected {row['suspected']} ({row['status']}, {row['seconds']} s)", flush=True)
        Path(args.out).write_text(json.dumps({"rows": rows, "metrics": metrics(rows), "judges": [j.name for j in judges]}, indent=1), encoding="utf-8")
    m = metrics(rows)
    ok = (m["recall_confirmed"] or 0) >= GATE_RECALL and (m["false_alarms_per_10_clean"] if m["false_alarms_per_10_clean"] is not None else 99) <= GATE_FALSE_ALARMS_PER_10
    print(json.dumps(m, indent=1))
    print("GATE:", "PASS" if ok else "FAIL", f"(recall >= {GATE_RECALL}, false alarms per 10 clean <= {GATE_FALSE_ALARMS_PER_10})")


if __name__ == "__main__":
    main()
