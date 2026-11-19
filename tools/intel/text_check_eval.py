"""Measure the stray-text judge on pictures whose state was read by eye (2026-11-17, output/intel/hidream_wm). Positives: a poster headline or a gibberish speech bubble is
visible; negatives: nothing written anywhere (corner signature already trimmed). Needs Ollama with qwen3.5:9b."""
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.llm.registry import llm_registry  # noqa: E402
from engine.original.anatomy.text_check import has_stray_text  # noqa: E402
from engine.original.judges import OllamaJudge  # noqa: E402

D = ROOT / "output" / "intel" / "hidream_wm"
POS = ["A_13", "A_14", "E_11", "F_s3_11", "F_s4_11", "F_s4_14", "G_s4_11", "G_s4_12", "G_s4_13", "H_s4_11", "H_s4_12", "I_s4_11"]
NEG = ["G_s3_11", "G_s3_12", "G_s3_13", "G_s3_14", "G_s4_14", "F_s3_12", "F_s3_13", "F_s3_14", "F_s4_12", "F_s4_13", "H_s4_13", "H_s4_14", "I_s4_12", "I_s4_13", "I_s4_14",
       "E_12", "E_13", "E_14"]


async def main():
    judge = OllamaJudge(llm_registry.get_ollama_provider())
    wrong, t0 = [], time.monotonic()
    for name, truth in [(n, True) for n in POS] + [(n, False) for n in NEG]:
        got = await has_stray_text(judge, (D / f"{name}.png").read_bytes())
        print(f"{name:10} truth={truth!s:5} judge={got}", flush=True)
        if got is not truth:
            wrong.append((name, truth, got))
    print(f"\n{len(POS)} text pictures, {len(NEG)} clean pictures, {time.monotonic() - t0:.0f}s total")
    print("missed text:", [w[0] for w in wrong if w[1] is True and w[2] is False], "| unverified:", [w[0] for w in wrong if w[2] is None],
          "| false alarms:", [w[0] for w in wrong if w[1] is False and w[2] is True])


asyncio.run(main())
