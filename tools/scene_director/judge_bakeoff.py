"""Bake-off of the two vision judges and their cross-check on labelled pictures (plan Task 3).

    .venv\\Scripts\\python.exe tools/scene_director/judge_bakeoff.py --labels tools/scene_director/labels.json

Needs Ollama and ComfyUI (started with --disable-dynamic-vram) running. Every picture is read by judge A (qwen3.5:9b) and judge B (Qwen3-VL 8B), blind; the
cross-check then re-asks only the disputed items, replaying the stored first answers so nothing is read twice. Prints the table and the gate result and writes
judge_bakeoff.json next to the labels. The labels are the agent's own reading of the pictures (see the _note in labels.json), not the owner's.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


class Replay:
    """Returns the stored first answer, but delegates the re-look to the real judge."""

    def __init__(self, real, first):
        self.real, self.first, self.name = real, first, real.name

    async def read(self, image, states):
        return self.first

    async def reread(self, image, topic, index, other, states):
        return await self.real.reread(image, topic, index, other, states)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from engine.comfyui.client import ComfyUIClient
    from engine.comfyui.edit_prompt import release_local_model
    from engine.llm.registry import llm_registry
    from engine.original.crosscheck import cross_check
    from engine.original.judge_eval import METHODS, gate, score
    from engine.original.judges import ComfyJudge, OllamaJudge
    from engine.original.scene_plan import load_playbook

    labels_path = Path(args.labels)
    spec = json.loads(labels_path.read_text(encoding="utf-8"))
    labels = spec["labels"][: args.limit or None]
    ja, jb = OllamaJudge(llm_registry.get_ollama_provider()), ComfyJudge(ComfyUIClient())
    states = lambda lab: [*load_playbook(lab["scene_type"]).action_states, "other"]
    groups = {t: load_playbook(t).state_groups for t in {lab["scene_type"] for lab in labels}}
    same = lambda x, y: x == y or any(x in g and y in g for gs in groups.values() for g in gs)
    pic = lambda lab: (ROOT / lab["file"]).read_bytes()

    seconds = {"A": 0.0, "B": 0.0, "cc": 0.0}
    first_a, first_b = {}, {}
    for lab in labels:
        t = time.time(); first_a[lab["file"]] = await ja.read(pic(lab), states(lab)); seconds["A"] += time.time() - t
    release_local_model()
    for lab in labels:
        t = time.time(); first_b[lab["file"]] = await jb.read(pic(lab), states(lab)); seconds["B"] += time.time() - t
    answers, flips = {}, 0
    for lab in labels:
        t = time.time()
        cc = await cross_check([Replay(ja, first_a[lab["file"]]), Replay(jb, first_b[lab["file"]])], pic(lab), states(lab), same_state=same, between=release_local_model)
        seconds["cc"] += time.time() - t
        flips += sum(len(i.suspect_flips) for i in cc.items)
        answers[lab["file"]] = {"A": first_a[lab["file"]], "B": first_b[lab["file"]], "cc": cc}
    report = score(labels, answers, same_state=same)
    n = len(labels)
    print(f"{n} pictures, {report['items']} items. Seconds per picture: A {seconds['A']/n:.1f}  B {seconds['B']/n:.1f}  re-look {seconds['cc']/n:.1f}  suspect flips: {flips}")
    for m in METHODS:
        r = report[m]
        print(f"  {m:10s} answered {r['answered']:3d}/{report['items']}  wrong {r['wrong']:3d}  accuracy of answered {r['accuracy_of_answered']:.2f}  coverage {r['coverage']:.2f}")
    print("GATE:", "PASS" if gate(report) else "FAIL")
    out = {"report": report, "gate": gate(report), "seconds_per_picture": {k: round(v / n, 2) for k, v in seconds.items()}, "suspect_flips": flips,
           "per_picture": {f: {"A": a["A"].model_dump(), "B": a["B"].model_dump(), "cc": a["cc"].model_dump()} for f, a in answers.items()}}
    (labels_path.parent / "judge_bakeoff.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
