"""Measure engine.original.clip_identity on clips whose truth was decided by looking at the frames (see docs/H3_CLIP_EVAL.md, Phase 5).

Run: .venv\\Scripts\\python.exe tools\\h3_identity_calibration.py   (needs Ollama; ~100 s per clip). Prints one line per clip and writes the JSON next to this file's output dir.
Truth: V = a character vanishes inside the clip, L = a character's hair/outfit colours drift, - = neither (checked on the contact sheets).
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.llm.registry import llm_registry  # noqa: E402
from engine.original import clip_identity as ci  # noqa: E402
from engine.original.models import OriginalStory  # noqa: E402

OUT = Path("output/Original_Stories")
A = Path("output/H3_Phase3/dawn/film/attempts")
P1 = Path("output/H3_Phase1")
CLIPS = [  # (label, story slug, panel id, clip, truth)
    ("p005 r4_a2 (Pip leaves after 0.5 s)", "dawn_gate", "p005", A / "p005/r4_a2.mp4", "V"),
    ("p005 r3_a3 (Pip leaves after ~1.6 s)", "dawn_gate", "p005", A / "p005/r3_a3.mp4", "V"),
    ("p070 r3_a0 (outfits wash out)", "dawn_gate", "p070", A / "p070/r3_a0.mp4", "L"),
    ("p070 r3_a3 (colours stable)", "dawn_gate", "p070", A / "p070/r3_a3.mp4", "-"),
    ("p012 static (everyone stays)", "dawn_gate", "p012", P1 / "static/film/clips/p012.mp4", "-"),
    ("p046 static (Rook stays)", "dawn_gate", "p046", P1 / "static/film/clips/p046.mp4", "-"),
    ("cat p004_1 (hair turns blue)", "vox_cat_table", "p004", Path(r"E:\VIJAY SEKAR\PanelFlow Studio\output\chronoflow\f98388c84143_chunk_3.mp4"), "L"),
    ("cat p001_1 (good)", "vox_cat_table", "p001", Path(r"E:\VIJAY SEKAR\PanelFlow Studio\output\chronoflow\f98388c84143_chunk_1.mp4"), "-"),
    ("cat p010_1 (good)", "vox_cat_table", "p010", Path(r"E:\VIJAY SEKAR\PanelFlow Studio\output\chronoflow\ece4b338f879_chunk_4.mp4"), "-"),
]


async def main() -> None:
    prov = llm_registry.get_ollama_provider()
    res = {}
    for label, slug, pid, clip, truth in CLIPS:
        if not clip.exists():
            print("MISSING", clip)
            continue
        story = OriginalStory.model_validate(json.loads((OUT / slug / "story.json").read_text(encoding="utf-8")))
        panel = next((p for p in story.panels if p.id == pid), None)
        chars = ci.shot_characters(story, panel) if panel else [(c.name, c.look) for c in story.bible.characters[:2]]
        t = time.time()
        r = await ci.check(clip, chars, prov)
        res[label] = {"truth": truth, **r}
        print(f"{truth} {label:40s} {round(time.time() - t)}s " + " | ".join(f"{n}: {d['presence']} {d['colours']}" for n, d in r["characters"].items()) + "  flags=" + str([f['axis'] for f in r['flags']]), flush=True)
    Path("output/H3_Phase3/identity_calibration.json").write_text(json.dumps(res, indent=1), encoding="utf-8")


asyncio.run(main())
