"""Build the labelled set for the anatomy reviewer from the 2026-11-16 audit pictures.

    .venv\\Scripts\\python.exe tools/anatomy/build_labels.py --src <scratchpad>/img_ab/anatomy [--extra name.png=path ...]

Copies the pictures to output/anatomy_labels/ (about 45 MB, not committed) and writes tests/data/anatomy_labels.json (small, committed). The labels are the AGENT's
counts from looking at the pictures at 380 px and zoomed; they are marked `source: agent-2026-11-16` until the owner confirms them. `expected: null` means the agent
was not sure and the picture is left out of the accuracy numbers.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "anatomy_labels"
LABELS = ROOT / "tests" / "data" / "anatomy_labels.json"
SOURCE = "agent-2026-11-16"
MODELS = {"klein": "flux2_klein_4b", "zimage": "z_image_turbo"}
POSES = ["cross_legged", "high_kick", "running", "tie_shoe", "sword_overhead", "handshake", "hug", "fingers"]
PEOPLE = {"handshake": 2, "hug": 2}


def expected(model: str, pose: str, seed: int) -> list[str] | None:
    """Defect keys ("kind" or "kind|pose") the agent counted in this picture; [] = clean as far as the audit could tell; None = not sure."""
    if pose == "cross_legged":  # klein 101 and 103 have four hands; klein 102/104 and every Z-Image picture clasp the hands in the lap instead of resting them on the knees
        if model == "klein":
            return {101: ["extra_hands"], 103: ["extra_hands"], 102: ["pose_missing|hands_on_knees"], 104: ["pose_missing|hands_on_knees"]}[seed]
        return ["pose_missing|hands_on_knees"]
    if pose == "sword_overhead":  # klein: a ghost second blade (101, 103); one hand holds a loose fist instead of the grip (102, 103)
        if model == "klein":
            return {101: ["duplicate_object"], 102: ["pose_missing|two_hands"], 103: ["duplicate_object", "pose_missing|two_hands"], 104: []}[seed]
        return []
    if pose == "hug":  # Z-Image 101 and 103 merge two bodies into one mass; the other hugs the agent was not sure about
        return {101: ["merged_bodies"], 103: ["merged_bodies"]}.get(seed) if model == "zimage" else None
    return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="the img_ab/anatomy folder holding prompts.json and <model>/<pose>/<seed>.png")
    ap.add_argument("--extra", action="append", default=[], help="name.png=path[=defect,defect] a picture the owner pointed at")
    args = ap.parse_args()
    src = Path(args.src)
    prompts = json.loads((src / "prompts.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for model, model_id in MODELS.items():
        for pose in POSES:
            for seed in (101, 102, 103, 104):
                name = f"{model}_{pose}_{seed}.png"
                shutil.copy2(src / model / pose / f"{seed}.png", OUT / name)
                entries.append({"id": f"{model}/{pose}/{seed}", "file": name, "model": model_id, "prompt": prompts[pose], "people": PEOPLE.get(pose, 1),
                                "expected": expected(model, pose, seed), "source": SOURCE})
    for item in args.extra:
        name, path, *defects = item.split("=")
        shutil.copy2(path, OUT / name)
        entries.append({"id": f"owner/{name}", "file": name, "model": "flux2_klein_4b", "prompt": prompts["hug"], "people": 2,
                        "expected": [d for d in (defects[0].split(",") if defects else []) if d], "source": "owner-pointed 2026-11-16"})
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    LABELS.write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8")
    known = sum(1 for e in entries if e["expected"])
    clean = sum(1 for e in entries if e["expected"] == [])
    print(f"{len(entries)} pictures: {known} with known defects, {clean} clean, {len(entries) - known - clean} unsure -> {LABELS}")


if __name__ == "__main__":
    main()
