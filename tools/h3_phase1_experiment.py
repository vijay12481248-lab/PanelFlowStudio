"""Phase 1 of the H3 skill: two controlled experiments on real Dawn Gate shots, written to an isolated folder (the story's own clips are never touched).

  base   - the current prompt and length (a push-in camera line; 56 or 73 frames for these shots)
  static - same shot, same seed, same frame; ONLY the camera sentence says Static Shot
  long   - same shot, same seed, same frame, same prompt; ONLY the length is 124 frames (5.17 s, inside H3's trained range)

Run: .venv\\Scripts\\python.exe tools\\h3_phase1_experiment.py [--out DIR]. Waits until ComfyUI has been idle for 2 minutes. Resumable (make_clips reuses finished clips).
Then evaluate with engine.original.clip_eval.evaluate and LOOK at the clips; see docs/H3_CLIP_EVAL.md for the results.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.original import film  # noqa: E402
from engine.original.models import OriginalStory  # noqa: E402

SRC = Path("output/Original_Stories/dawn_gate")
SHOTS = ["p003", "p031", "p088", "p012", "p046", "p060"]  # silent shots, 3 extreme close-ups and 3 close-ups (the short ones)
STATIC = "nothing; it is a Static Shot, fixed on a tripod, with no zoom, no pan and no tilt"
LONG_SECONDS = 5.17  # 124 frames on the 17k+5 grid


def wait_idle(quiet_s: float = 120.0, comfy: str = "http://127.0.0.1:8188") -> None:
    """Block until ComfyUI's queue has been empty for `quiet_s` seconds (another job may be using the GPU)."""
    since = None
    while True:
        q = httpx.get(f"{comfy}/queue", timeout=10).json()
        busy = bool(q["queue_running"] or q["queue_pending"])
        since = None if busy else (since or time.monotonic())
        if since and time.monotonic() - since >= quiet_s:
            return
        time.sleep(10)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output/H3_Phase1")
    out = Path(ap.parse_args().out)
    story = OriginalStory.model_validate(json.loads((SRC / "story.json").read_text(encoding="utf-8")))
    base_camera, base_hold = dict(film.CAMERA), dict(film.HOLD)
    for variant in ("base", "static", "long"):
        ws = out / variant
        (ws / "film" / "frames").mkdir(parents=True, exist_ok=True)
        for sid in SHOTS:
            shutil.copy2(SRC / "film" / "frames" / f"{sid}.png", ws / "film" / "frames" / f"{sid}.png")
        film.CAMERA.update(base_camera if variant != "static" else {k: STATIC for k in base_camera})
        film.HOLD.update(base_hold if variant != "long" else {k: LONG_SECONDS for k in base_hold})
        wait_idle()
        print(f"[{time.strftime('%H:%M:%S')}] {variant}", flush=True)
        res = film.make_clips(story, ws, ids=SHOTS, free_llm_memory=True)
        print(variant, json.dumps(res), flush=True)


if __name__ == "__main__":
    main()
