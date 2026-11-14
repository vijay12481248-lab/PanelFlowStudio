"""THROWAWAY spike (plan Task 7, step 1): does a code-drawn mannequin picture steer the H3-Image transfer to the planned pose/camera?

Renders a mannequin staging picture for a ScenePlan, then edits the matching raw baseline picture with it (character picture = Picture 1, staging = Picture 2,
through compose_transfer_prompt + ArtEngine.edit) and checks before/after with check_scene. Results are looked at by a person; nothing here is product code.

    .venv\\Scripts\\python.exe tools/scene_director/staging_spike.py --baseline <baseline_raw dir> --out <dir> fight-01 fight-02 ...
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# unit-space joints for a figure FACING RIGHT, feet at y=0, height 1: (head, neck, hip, hand_front, hand_back, foot_front, foot_back)
POSES = {
    "striking": [(0.14, 0.93), (0.10, 0.80), (0.0, 0.50), (0.62, 0.82), (-0.06, 0.74), (0.30, 0.0), (-0.28, 0.0)],
    "blocking": [(0.04, 0.93), (0.02, 0.80), (0.0, 0.50), (0.26, 0.86), (0.22, 0.68), (0.14, 0.0), (-0.14, 0.0)],
    "readying": [(0.05, 0.93), (0.03, 0.80), (0.0, 0.50), (0.22, 0.78), (0.14, 0.66), (0.16, 0.0), (-0.16, 0.0)],
    "struck": [(-0.18, 0.92), (-0.12, 0.80), (0.0, 0.50), (-0.42, 0.95), (-0.40, 0.60), (0.10, 0.12), (-0.20, 0.0)],
    "falling": [(-0.45, 0.62), (-0.30, 0.55), (0.0, 0.45), (-0.62, 0.90), (-0.55, 0.30), (0.20, 0.0), (0.05, 0.12)],
    "dodging": [(-0.10, 0.90), (-0.06, 0.79), (0.0, 0.50), (0.15, 0.70), (-0.25, 0.62), (0.20, 0.0), (-0.22, 0.0)],
    "standing": [(0.0, 0.93), (0.0, 0.80), (0.0, 0.50), (0.12, 0.52), (-0.12, 0.52), (0.10, 0.0), (-0.10, 0.0)],
}
COLORS = {"left": (40, 90, 200), "center": (60, 60, 60), "right": (200, 50, 40)}


def render(plan, size=(1344, 768)) -> bytes:
    w, h = size
    horizon = {"low": 0.86, "high": 0.18, "eye_level": 0.5, "dutch": 0.5}[plan.camera.angle]
    scale = {"close": 0.9, "medium": 0.68, "wide": 0.38}[plan.camera.distance] * h
    img = Image.new("RGB", (w, h), (214, 220, 226))
    d = ImageDraw.Draw(img)
    d.rectangle([0, int(h * horizon), w, h], fill=(176, 170, 160))
    spots = {"left": 0.28, "center": 0.5, "right": 0.72}
    hands = {}
    for a in plan.actors:
        s = scale * {"foreground": 1.15, "midground": 1.0, "background": 0.85}[a.depth]
        face = 1 if a.side != "right" else -1
        x0, y0 = spots[a.side] * w, (h * 0.5 + s * 0.5) if plan.camera.angle != "low" else h * 0.97
        pts = [(x0 + face * px * s, y0 - py * s) for px, py in POSES.get(a.action_state, POSES["standing"])]
        head, neck, hip, hf, hb, ff, fb = pts
        col, lw = COLORS[a.side], max(6, int(s * 0.07))
        for p, q in ((neck, hip), (neck, hf), (neck, hb), (hip, ff), (hip, fb)):
            d.line([p, q], fill=col, width=lw)
        r = s * 0.075
        d.ellipse([head[0] - r, head[1] - r, head[0] + r, head[1] + r], fill=col)
        hands[a.id] = (hf, hip)
    for c in plan.contacts:
        if c.source in hands and c.target in hands:
            (sx, sy), (tx, ty) = hands[c.source][0], hands[c.target][1]
            d.line([(sx, sy), (tx, ty)], fill=(230, 160, 0), width=8)
            ang = math.atan2(ty - sy, tx - sx)
            d.polygon([(tx, ty), (tx - 28 * math.cos(ang - 0.4), ty - 28 * math.sin(ang - 0.4)), (tx - 28 * math.cos(ang + 0.4), ty - 28 * math.sin(ang + 0.4))], fill=(230, 160, 0))
    if plan.camera.angle == "dutch":
        img = img.rotate(12, resample=Image.BICUBIC, fillcolor=(214, 220, 226))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


HINT = ("Picture 2 is only a rough mannequin diagram of the staging. Copy from it the camera angle, the placement of the two figures (blue on the left, red on the right), "
        "and their body poses; do not copy its flat colours, its stick-figure drawing style or its arrows. The result is a finished painting like Picture 1.")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("ids", nargs="+")
    a = ap.parse_args()
    from engine.comfyui.art import ArtEngine
    from engine.comfyui.edit_prompt import compose_transfer_prompt, release_local_model
    from engine.llm.registry import llm_registry
    from engine.original.scene_check import check_scene
    from engine.original.scene_planner import propose

    briefs = {b["id"]: b for b in json.loads((Path(__file__).with_name("baseline_briefs.json")).read_text(encoding="utf-8"))}
    out, base = Path(a.out), Path(a.baseline)
    out.mkdir(parents=True, exist_ok=True)
    provider, art = llm_registry.get_ollama_provider(), ArtEngine()
    rows = []
    for bid in a.ids:
        plan = (await propose(provider, briefs[bid]["text"])).plan
        stage = render(plan)
        (out / f"{bid}_stage.png").write_bytes(stage)
        before = (base / f"{bid}.png").read_bytes()
        r0 = await check_scene(provider, before, plan)
        t = time.time()
        prompt = compose_transfer_prompt(before, stage, HINT)
        release_local_model()  # the local model and the H3 checkpoint do not fit in VRAM together
        edited = art.edit(prompt, [before, stage], width=1344, height=768, seed=11)
        dt = time.time() - t
        (out / f"{bid}_after.png").write_bytes(edited.png)
        r1 = await check_scene(provider, edited.png, plan)
        row = {"id": bid, "edit_s": round(dt, 1), "before": [r0.decision, r0.score, [i.item[-40:] for i in r0.items if not i.passed]],
               "after": [r1.decision, r1.score, [i.item[-40:] for i in r1.items if not i.passed]]}
        rows.append(row)
        print(json.dumps(row), flush=True)
    (out / "spike.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
