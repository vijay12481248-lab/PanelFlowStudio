"""One call that draws a picture either plainly or through the anatomy check, for callers (Reels first) that want a switch instead of two code paths."""
from __future__ import annotations

from pathlib import Path

from engine.comfyui.art import ART_WORKFLOW_ID
from engine.creative.mistakes import MistakeLedger
from engine.original.anatomy.loop import AnatomyBudget, generate_checked


def draw_picture(art_engine, *, prompt: str, width: int, height: int, seed: int, prefix: str, negative_prompt: str = "", workflow_id: str = ART_WORKFLOW_ID,
                 reference_image=None, check: bool = False, judges=None, ledger: MistakeLedger | None = None, record_path: Path | None = None,
                 budget: AnatomyBudget = AnatomyBudget(), between=None, check_text: bool = False, text_judge=None,
                 before_judge=None, text_fallback: str | None = None) -> tuple[bytes, dict | None]:
    """(png, report). Unchecked: exactly `art_engine.generate` and no report. Checked: `generate_checked` (redraw on confirmed defects) and a small JSON-ready report."""
    if check_text and not check:  # stray-text check only (HiDream): one judge, redraw while text is found
        from engine.original.anatomy.text_check import generate_text_free
        got = generate_text_free(art_engine, text_judge, prompt=prompt, width=width, height=height, seed=seed, prefix=prefix, workflow_id=workflow_id,
                                 before_judge=before_judge, before_draw=between, fallback_workflow_id=text_fallback)
        return got.png, {"status": got.status, "seed": got.seed, "attempts": len(got.attempts), "text": [a["text"] for a in got.attempts], "confirmed": [], "suspected": [], "prompt": prompt}
    if not check:
        kw = {"reference_image": reference_image} if reference_image is not None else {}
        return art_engine.generate(prompt, negative_prompt, width, height, seed, prefix, workflow_id=workflow_id, **kw).png, None
    result = generate_checked(art_engine, judges or [], prompt=prompt, width=width, height=height, seed=seed, prefix=prefix, workflow_id=workflow_id,
                              reference_images=[reference_image] if reference_image is not None else None, budget=budget, ledger=ledger, record_path=record_path,
                              between=between)
    report = {"status": result.status, "seed": result.seed, "attempts": len(result.attempts), "confirmed": [d.kind for d in result.report.confirmed],
              "suspected": [d.kind for d in result.report.suspected], "prompt": result.prompt}
    return result.png, report
