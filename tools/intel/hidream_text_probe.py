"""Probe: why does HiDream-I1 Fast draw stray lettering / signatures, and what stops it? Same scene and seeds under four conditions.
  A  current reel prompt (STYLE says "no text, no letters, no numbers, no words, no speech bubbles")
  B  same prompt with every mention of text removed
  C  B + positive wording ("nothing written anywhere, unsigned, plain background")
  D  B + a negative prompt with cfg 2.0 (the registered graph runs cfg 1.0, where the negative is ignored)
Output: output/intel/hidream_wm/<cond>_<seed>.png (skips existing).  Needs ComfyUI on :8188."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "reels"))
from specs import STYLE  # noqa: E402
from spec_lunch import LUNCH  # noqa: E402
from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry  # noqa: E402
from engine.comfyui.art import ArtEngine, _patch_workflow  # noqa: E402

OUT = ROOT / "output" / "intel" / "hidream_wm"
OUT.mkdir(parents=True, exist_ok=True)
SEEDS = [11, 12, 13, 14]
SCENE = LUNCH["scenes"][2]["img"].replace("{BOSS}", "")  # scene 3: the boss eats the sandwich
NO_TEXT = ", no text, no letters, no numbers, no words, no speech bubbles"
STYLE_B = STYLE.replace(NO_TEXT, "")
assert STYLE_B != STYLE
POS = "pure illustration with nothing written anywhere, unsigned clean artwork, plain empty background"
NEG = "text, letters, words, watermark, signature, logo, caption, speech bubble, handwriting, scribble"
PROMPTS = {"A": f"{SCENE}. {LUNCH['palette']}. {STYLE}", "B": f"{SCENE}. {LUNCH['palette']}. {STYLE_B}", "C": f"{SCENE}. {LUNCH['palette']}. {STYLE_B}, {POS}",
           "D": f"{SCENE}. {LUNCH['palette']}. {STYLE_B}"}

client = ComfyUIClient()
reg = ComfyWorkflowRegistry(client)
eng = ArtEngine(client, reg)
for cond, prompt in PROMPTS.items():
    for seed in SEEDS:
        dest = OUT / f"{cond}_{seed}.png"
        if dest.exists():
            continue
        t0 = time.monotonic()
        if cond == "D":
            wf, _ = reg.load("hidream_i1_fast")
            g = _patch_workflow(wf, reg.metadata("hidream_i1_fast")["patch_slots"], prompt, "", 768, 1344, seed, "intel/wm_D")
            g["90"]["inputs"]["text"] = NEG
            g["94"]["inputs"]["cfg"] = 2.0
            raw = eng.run(g, timeout=600.0)[0]
        else:
            raw = eng.generate(prompt, width=768, height=1344, seed=seed, prefix=f"intel/wm_{cond}", workflow_id="hidream_i1_fast").png
        dest.write_bytes(raw)
        print(cond, seed, f"{time.monotonic() - t0:.0f}s", flush=True)
