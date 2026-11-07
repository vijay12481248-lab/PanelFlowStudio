"""Scenario 5 (multiple reference images) and the Pip test: does Ref2VA keep a character in the clip that image-to-video lost? (results: docs/H3_CLIP_EVAL.md, Phase 5)

Reference <Picture 1> = a Dawn Gate frame with Mira and Pip (identity), <Picture 2> = a location made with the art workflow (floating rock spires, no people). The prompt asks for
the p005 action (the glider banks around the spire, Pip beside her). The same action as image-to-video lost Pip after 0.5 s (p005). Measured with clip_eval and clip_identity.
Needs the FastH3 OmniRef weights in ComfyUI/models/diffusion_models (it does NOT download anything). Run: .venv\\Scripts\\python.exe tools\\h3_ref2va_test.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.llm.registry import llm_registry  # noqa: E402
from engine.original import art as art_mod  # noqa: E402
from engine.original import clip_identity as ci  # noqa: E402
from engine.original import h3_modes as hm  # noqa: E402
from engine.original.animate import release_ollama  # noqa: E402
from engine.original.clip_eval import evaluate  # noqa: E402
from engine.original.models import OriginalStory  # noqa: E402

OUT = Path("output/H3_Validation/ref2va")
DAWN = Path("output/Original_Stories/dawn_gate")
LOCATION = "Anime illustration. Wide landscape: tall rock spires and floating islands over a sea of clouds at golden hour, blue sky, no people, no characters, no vehicles."
ACTION = ("Mira rides the cloth-winged glider in a tight curve around the tall rock spire, leaning into the turn, while Pip floats right beside her and stays beside her the whole time")
SUBJECTS = [("Mira, the teenage girl with short messy copper-red hair, a green scarf and a brown leather jacket, and Pip, the small white fluffy sky-fox kit,", 1, "fully_preserved", "faces, hair, outfit colours and Pip's pure white fur"),
            ("the sky with floating rock spires and clouds", 2, "partially_preserved", "the rock spire, the clouds and the golden light")]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    release_ollama()
    if not (OUT / "location.png").exists():
        (OUT / "location.png").write_bytes(art_mod.ComfyRunner().generate(LOCATION, "blurry, low quality, text", 4242, 1344, 768, "ref2va_location"))
    ident = DAWN / "film" / "frames" / "p012.png"  # Mira and Pip together
    clip = OUT / "ref2va_p005_style.mp4"
    if not clip.exists():
        t = time.time()
        clip.write_bytes(hm.make_clip("ref2va", hm.ref2va_prompt(SUBJECTS, ACTION), seed=7, seconds=3.75, refs=[ident, OUT / "location.png"], prefix="video/h3val_ref2va"))
        print(f"clip made in {round(time.time() - t)} s", flush=True)
    rep = evaluate(clip, expect_camera="static", expect_audio=True)
    print("clip_eval:", f"frames {rep['frames']} zoom {rep['camera']['zoom_pct']:+.1f}% drift {rep['drift']['max']} flicker {rep['flicker']} cuts {rep['cuts_s']} flags", [f["axis"] + ":" + f["status"][:4] for f in rep["flags"]], flush=True)
    story = OriginalStory.model_validate(json.loads((DAWN / "story.json").read_text(encoding="utf-8")))
    chars = {c.name: c.look for c in story.bible.characters if c.name in ("Mira", "Pip")}
    r = asyncio.run(ci.check(clip, list(chars.items()), llm_registry.get_ollama_provider()))
    for name, d in r["characters"].items():
        print(f"presence {name}: {d['presence']}  colours {d['colours']}", flush=True)
    print("identity flags:", [f["evidence"] for f in r["flags"]], flush=True)
    (OUT / "result.json").write_text(json.dumps({"eval": rep, "identity": r}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
