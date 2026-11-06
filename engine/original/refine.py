"""The generic refinement loop: generate -> review -> plan -> (repair | regenerate | stop), for any image and any caller.

`refine_image` owns only the control flow. What a generation, a review and a repair ARE is passed in as callables, so the same loop serves the story
panels (`art.generate_art`) and any prompt (`refine_prompt_image`, used by ChronoFlow and the Comfy image screen) without a second job manager,
a second ComfyUI client or a second history format. The decisions come from `planner.plan_correction`; every candidate is kept with its record
(`record_candidate`), and the result names the candidate that was chosen. It never overwrites a candidate and never accepts silently: a picture that
still fails after the budget is `needs_review`.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageDraw, ImageFilter

from engine.original import review as review_mod
from engine.original.models import Review
from engine.original.planner import Budget, CorrectionPlan, PlanTarget, plan_correction

STATUS = {"accept": "accept", "accept_low": "accept_low", "human_review": "needs_review"}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def review_summary(rev: Review | None) -> dict | None:
    if rev is None:
        return None
    return {"decision": rev.decision, "score": rev.score, "confidence": rev.confidence, "defects": list(rev.defects),
            "failed": [i.item for i in rev.items if not i.passed][:8]}


def record_candidate(ws: Path, key: str, iterations: list[dict], data: bytes, mask: bytes | None = None, **meta) -> dict:
    """Keep one candidate under <ws>/panels/_candidates/<key>/ and append its generation record. Candidate files are never overwritten or deleted,
    so a redraw, a repair or a re-run can always be compared with, or rolled back to, what came before. A repair's mask is kept beside it."""
    n = max((i["n"] for i in iterations), default=0) + 1
    folder = ws / "panels" / "_candidates" / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"c{n:03d}.png").write_bytes(data)
    entry = {"n": n, "file": f"panels/_candidates/{key}/c{n:03d}.png", "sha256": sha256_hex(data), **meta}
    if mask is not None:
        (folder / f"c{n:03d}_mask.png").write_bytes(mask)
        entry["mask"] = f"panels/_candidates/{key}/c{n:03d}_mask.png"
    iterations.append(entry)
    return entry


def repair_improved(after: Review, before: Review) -> bool:
    """A repair is kept only if the picture got better: the gates now pass without losing the score, or fewer defects and a higher score."""
    return bool((after.anatomy_passed and after.spatial_contact_passed and after.score >= before.score - 0.05)
                or (len(after.defects) < len(before.defects) and after.score > before.score))


def mask_from_boxes(size: tuple[int, int], targets: list[PlanTarget], padding: int = 12, blur: int = 8) -> bytes | None:
    """White = redraw. Only boxes the reviewer reported are used (normalised 0..1); no box, no mask."""
    w, h = size
    mask = Image.new("L", (w, h), 0)
    draw, drawn = ImageDraw.Draw(mask), 0
    for t in targets:
        if not t.bbox:
            continue
        x1, y1, x2, y2 = t.bbox[0] * w, t.bbox[1] * h, t.bbox[2] * w, t.bbox[3] * h
        draw.rectangle([max(0, x1 - padding), max(0, y1 - padding), min(w, x2 + padding), min(h, y2 + padding)], fill=255)
        drawn += 1
    if not drawn:
        return None
    buf = io.BytesIO()
    (mask.filter(ImageFilter.GaussianBlur(blur)) if blur else mask).save(buf, "PNG")
    return buf.getvalue()


def repair_prompt(prompt: str, targets: list[PlanTarget]) -> str:
    """The masked redraw reads a description, not an instruction: the whole prompt plus what the redrawn area must show."""
    shows = "; ".join(t.correction if t.defect_type else t.item for t in targets)
    return f"{prompt.rstrip()} The redrawn area must show: {shows}."


def qwen_repair(editor, png: bytes, plan: CorrectionPlan, prompt: str, negative: str, seed: int, *, timeout: float = 300.0,
                is_cancelled: Callable[[], bool] = lambda: False) -> tuple[bytes, dict] | None:
    """Masked redraw of the plan's located targets on the art model, with the original spliced back outside the mask. None when no target has a box."""
    with Image.open(io.BytesIO(png)) as im:
        size = im.size
    mask = mask_from_boxes(size, plan.targets)
    if mask is None:
        return None
    text = repair_prompt(prompt, plan.targets)
    raw = editor.inpaint_qwen(png, mask, text, negative, seed, timeout=timeout, is_cancelled=is_cancelled)
    with Image.open(io.BytesIO(png)) as base, Image.open(io.BytesIO(raw)) as redrawn, Image.open(io.BytesIO(mask)) as m:
        out = io.BytesIO()
        review_mod.splice_repaired_image(base, redrawn, m).save(out, "PNG")
    return out.getvalue(), {"seed": seed, "prompt": text, "negative": negative, "denoise": 1.0, "mask": mask}


@dataclass
class RefineResult:
    png: bytes
    selected: int | None
    review: Review | None
    status: str  # accept | accept_low | needs_review | unverified
    plan: CorrectionPlan
    iterations: list[dict]
    generations: int


def refine_image(*, generate: Callable[[int, CorrectionPlan | None], tuple[bytes, dict]], review: Callable[[bytes], Review | None],
                 record: Callable[..., dict], repair: Callable[[bytes, Review, CorrectionPlan], tuple[bytes, dict] | None] | None = None,
                 budget: Budget = Budget(), allow_heuristic_masks: bool = False,
                 is_cancelled: Callable[[], bool] = lambda: False) -> RefineResult:
    """generate(attempt, plan) -> (png, meta); review(png) -> Review (may raise: the candidate is then 'unverified');
    repair(png, review, plan) -> (png, meta) or None when no repair can be made; record(png, **meta) -> the iteration entry."""
    history: list[dict] = []
    pngs: dict[int, bytes] = {}
    reviews: dict[int, Review | None] = {}

    def look(png: bytes) -> Review | None:
        try:
            return review(png)
        except Exception:
            return None  # a judge that is not answering must not stop a whole episode, nor burn attempts

    plan: CorrectionPlan | None = None
    generations = 0
    while True:
        if is_cancelled():
            raise RuntimeError("cancelled")
        png, meta = generate(generations, plan)
        gen = record(png, kind="generate", attempt=generations, **meta)
        generations += 1
        history.append(gen)
        pngs[gen["n"]], reviews[gen["n"]] = png, look(png)
        gen["review"] = review_summary(reviews[gen["n"]])
        cur, can_repair = gen, repair is not None
        while True:
            plan = plan_correction(reviews[cur["n"]], history, budget=budget, edit_available=can_repair, allow_heuristic_masks=allow_heuristic_masks)
            if plan.action != "repair_local":
                break
            out = repair(pngs[cur["n"]], reviews[cur["n"]], plan)
            if out is None:
                can_repair = False  # no usable mask or no edit tool after all: plan again without it
                continue
            rpng, rmeta = out
            rep = record(rpng, kind="repair", parent=gen["n"], attempt=generations - 1, **rmeta)
            history.append(rep)
            pngs[rep["n"]], reviews[rep["n"]] = rpng, look(rpng)
            rep["review"] = review_summary(reviews[rep["n"]])
            before, after = reviews[cur["n"]], reviews[rep["n"]]
            rep["kept"] = bool(after is not None and before is not None and repair_improved(after, before))
            if rep["kept"]:
                cur = rep
        if plan.final:
            break
    sel = plan.select if plan.select is not None else gen["n"]
    rev = reviews.get(sel)
    return RefineResult(png=pngs[sel], selected=sel, review=rev, status="unverified" if rev is None else STATUS[plan.action], plan=plan,
                        iterations=history, generations=generations)


def refine_prompt_image(art_engine, provider, prompt: str, negative: str = "", width: int = 1344, height: int = 768, *, ws: Path, key: str,
                        seed: int | None = None, editor=None, budget: Budget = Budget(), timeout: float = 300.0, prefix: str = "panelflow_refined",
                        is_cancelled: Callable[[], bool] = lambda: False) -> RefineResult:
    """Any prompt -> a reviewed picture. `art_engine` is the central ArtEngine; `editor` is a ComfyRunner with `inpaint_qwen` (optional: without it a
    located defect is redrawn as a whole). Blocking: callers in async code run it in a thread. Candidates go to <ws>/panels/_candidates/<key>/."""
    base_seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    iters: list[dict] = []
    state: dict[str, Any] = {}

    def generate(attempt: int, plan: CorrectionPlan | None):
        text = f"Most important: {'; '.join(plan.emphasis)}. {prompt}" if plan and plan.emphasis else prompt
        s = base_seed + attempt * 7919
        art = art_engine.generate(text, negative, width, height, s, prefix, timeout=timeout, is_cancelled=is_cancelled)
        state["prompt"] = text
        return art.png, {"seed": s, "prompt": text, "negative": negative, "width": art.width, "height": art.height, "engine": "qwen",
                         "workflow": art.workflow_id, "workflow_sha256": art.workflow_sha256, "prompt_id": art.prompt_id}

    def look(png: bytes) -> Review:
        tmp = ws / f"_try_{key}.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(png)
        try:
            return asyncio.run(review_mod.evaluate_prompt_image(provider, tmp, prompt, locate_defects=True))
        finally:
            tmp.unlink(missing_ok=True)

    def fix(png: bytes, rev: Review, plan: CorrectionPlan):
        return qwen_repair(editor, png, plan, state["prompt"], negative, base_seed + 1, timeout=timeout, is_cancelled=is_cancelled)

    can_edit = editor is not None and getattr(editor, "qwen_inpaint_wf", None) is not None
    return refine_image(generate=generate, review=look, repair=fix if can_edit else None, budget=budget, is_cancelled=is_cancelled,
                        record=lambda data, **meta: record_candidate(ws, key, iters, data, **meta))


def refine_art_image(prompt: str, negative: str | None, width: int, height: int, seed: int | None, *, ws: Path, key: str, client=None,
                     timeout: float = 900.0, is_cancelled: Callable[[], bool] = lambda: False):
    """Opt-in drop-in for `ArtEngine.generate` at callers that only need a picture: returns (ArtImage, RefineResult). Local-first: if the local vision
    model is unreachable it raises instead of handing back a picture that was never reviewed."""
    from engine.comfyui import ComfyUIClient
    from engine.comfyui.art import ART_WORKFLOW_ID, ArtImage
    from engine.llm.registry import llm_registry
    from engine.original.art import ComfyRunner

    runner = ComfyRunner(client=client or ComfyUIClient())
    provider = llm_registry.get_ollama_provider()
    if not asyncio.run(provider.health_check()):
        raise RuntimeError("Image refinement needs the local vision model (Ollama), which is not reachable; nothing was generated or silently skipped")
    res = refine_prompt_image(runner.art, provider, prompt, negative or "", width, height, ws=ws, key=key, seed=seed, editor=runner, timeout=timeout,
                              is_cancelled=is_cancelled)
    chosen = next(i for i in res.iterations if i["n"] == res.selected)
    origin = next(i for i in res.iterations if i["n"] == (chosen.get("parent") or chosen["n"]))
    with Image.open(io.BytesIO(res.png)) as im:
        w, h = im.size
    meta = runner.art.registry.metadata(ART_WORKFLOW_ID)
    art = ArtImage(png=res.png, width=w, height=h, prompt_id=origin["prompt_id"], workflow_id=origin["workflow"], workflow_sha256=origin["workflow_sha256"],
                   model_files=list(meta.get("model_files", [])), source_output={"filename": f"{key}.png", "subfolder": "", "type": "output"},
                   seed=origin["seed"])
    return art, res
