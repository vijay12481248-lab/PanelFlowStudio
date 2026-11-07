"""Validation scenarios 2, 3, 4 (+ L2VA and T2VA) and 10 of the H3 skill, on this machine (results: docs/H3_CLIP_EVAL.md, Phase 5).

Makes two first frames with the art workflow, then: stickman walking (I2VA, static camera), girl with a cup (I2VA), first+last frame (FL2VA, the last frame is the last frame of the
cup clip), last frame only (L2VA), text only (T2VA), and a second clip that starts from the cup clip's last frame (continuity, scenario 10). Every clip is measured with clip_eval
and every cut with continuity.boundary. Output: output/H3_Validation/. Resumable; ~20 minutes on the RTX 5060 Ti. Run: .venv\\Scripts\\python.exe tools\\h3_validation_scenarios.py
"""
import json
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.original import art as art_mod  # noqa: E402
from engine.original import continuity, h3_modes as hm  # noqa: E402
from engine.original.animate import release_ollama  # noqa: E402
from engine.original.clip_eval import evaluate  # noqa: E402

OUT = Path("output/H3_Validation")
NEG = "blurry, low quality, text, watermark"
FRAMES = {
    "stick": "Minimalist stickman drawing: a simple black line stick figure with a round head on a plain white background, full body, standing in side view facing right, thin black lines, flat 2D, no shading.",
    "girl": "Anime illustration. Medium shot. A teenage girl with short copper-red hair and a green scarf sits at a wooden table holding a white ceramic cup in both hands at chest height, calm expression, warm window light, soft background.",
}
SECONDS = 3.75


def last_frame(clip: Path, dest: Path) -> Path:
    cap = cv2.VideoCapture(str(clip))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, n - 1)
    ok, f = cap.read()
    cap.release()
    assert ok
    cv2.imwrite(str(dest), f)
    return dest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    release_ollama()
    runner = art_mod.ComfyRunner()
    for name, prompt in FRAMES.items():
        if not (OUT / f"{name}.png").exists():
            print("frame", name, flush=True)
            (OUT / f"{name}.png").write_bytes(runner.generate(prompt, NEG, 12345, 1344, 768, f"h3val_{name}"))
    results = {}

    def clip(name: str, mode: str, prompt: str, **kw) -> Path:
        path = OUT / f"{name}.mp4"
        if not path.exists():
            t = time.time()
            print("clip", name, mode, flush=True)
            path.write_bytes(hm.make_clip(mode, prompt, seed=7, seconds=SECONDS, prefix=f"video/h3val_{name}", **kw))
            print(f"  {name}: {round(time.time() - t)} s", flush=True)
        results[name] = evaluate(path, expect_camera="static", expect_audio=True)
        r = results[name]
        print(f"  {name}: frames {r['frames']} zoom {r['camera']['zoom_pct']:+.1f}% drift {r['drift']['max']} flicker {r['flicker']} cuts {r['cuts_s']} flags {[f['axis'] + ':' + f['status'][:4] for f in r['flags']]}", flush=True)
        return path

    stick = clip("s2_stick_walk_i2va", "i2va", hm.i2va_prompt("The stick figure walks to the right at a steady pace, arms swinging, staying the same size and the same distance from the camera. The white background does not change."), first=OUT / "stick.png")
    cup = clip("s3_girl_cup_i2va", "i2va", hm.i2va_prompt("She lifts the cup to her mouth and drinks. The cup keeps its shape and colour."), first=OUT / "girl.png")
    end = last_frame(cup, OUT / "girl_last.png")
    fl = clip("s4_girl_cup_fl2va", "fl2va", hm.fl2va_prompt("She lifts the cup to her mouth and drinks. The cup keeps its shape and colour.", SECONDS), first=OUT / "girl.png", last=end)
    l2 = clip("s4b_girl_cup_l2va", "l2va", hm.l2va_prompt("She holds the cup at her chest, then raises it to her mouth. The cup keeps its shape and colour.", SECONDS), last=end)
    t2 = clip("s4c_stick_walk_t2va", "t2va", hm.t2va_prompt("A black line stick figure with a round head on a plain white background.", "It walks from left to right at a steady pace, arms swinging, staying the same size."))
    nxt = clip("s10_girl_sets_cup_down_i2va", "i2va", hm.i2va_prompt("She lowers the cup and sets it down on the table. The cup keeps its shape and colour."), first=end)
    # last-frame landing for FL2VA / L2VA: how close is the result's last frame to the supplied last frame (0-255 gray, lower = closer)
    import numpy as np

    target = cv2.cvtColor(cv2.resize(cv2.imread(str(end)), (384, 216)), cv2.COLOR_BGR2GRAY).astype(float)
    for name, p in (("s4_girl_cup_fl2va", fl), ("s4b_girl_cup_l2va", l2), ("s3_girl_cup_i2va", cup)):
        _, lf = continuity.edge_frames(p)
        results[name]["last_frame_gray_diff"] = round(float(np.abs(cv2.cvtColor(lf, cv2.COLOR_BGR2GRAY).astype(float) - target).mean()), 1)
    results["boundary_continuation"] = continuity.boundary(cup, nxt, continuous=True)
    results["boundary_unrelated"] = continuity.boundary(cup, stick, continuous=True)
    results["boundary_cut_dawn_like"] = continuity.boundary(stick, cup)
    for k in ("boundary_continuation", "boundary_unrelated", "boundary_cut_dawn_like"):
        r = results[k]
        print(k, "hist", r["hist_distance"], "gray", r["gray_diff"], "flags", [f["axis"] for f in r["flags"]], flush=True)
    print({n: results[n].get("last_frame_gray_diff") for n in ("s4_girl_cup_fl2va", "s4b_girl_cup_l2va", "s3_girl_cup_i2va")}, flush=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
