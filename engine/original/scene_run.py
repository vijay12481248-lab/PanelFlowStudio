"""The fast-path run loop: plan -> prompt -> Qwen -> check against the plan -> correct or stop, with every candidate kept.

It is the existing `refine.refine_image` loop (correction planner, attempt budget, cancel, "unverified when the judge does not answer") given a scene-specific
generate and check; nothing here re-implements those rules. A picture that does not pass is still delivered (the best candidate) with what it missed listed.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from engine.original.models import Review
from engine.original.planner import Budget, CorrectionPlan, best_iteration
from engine.original.refine import record_candidate, refine_image, sha256_hex
from engine.comfyui.art import ART_WORKFLOW_ID
from engine.creative.mistakes import MistakeLedger
from engine.original.scene_check import check_scene
from engine.original.scene_lessons import lessons_for, record_outcome
from engine.original.scene_plan import ScenePlan
from engine.original.scene_prompt import compile_scene_prompt


class SceneBudget(BaseModel):
    max_attempts: int = 3
    max_seconds: float = 60.0  # no new attempt starts after this; measured here: one attempt is a ~8-11 s draw plus a ~9-15 s fast check


class SceneResult(BaseModel):
    image_path: str  # relative to the workspace
    plan: ScenePlan
    review: Review | None
    status: str  # accept | accept_low | needs_review | unverified
    unmet: list[str] = Field(default_factory=list)  # plan items the delivered picture misses, plus "cancelled" / "time budget used"
    unverified: bool = False  # the checker could not judge the picture: never read this as a pass
    escalated: bool = False
    seconds: float = 0.0
    iterations: list[dict] = Field(default_factory=list)


class _OutOfTime(Exception):
    pass


def generate_scene(art_engine, provider, plan: ScenePlan, *, ws: Path, key: str, seed: int | None = None, budget: SceneBudget = SceneBudget(),
                   lessons: str = "", ledger: MistakeLedger | None = None, is_cancelled: Callable[[], bool] = lambda: False,
                   timeout: float = 300.0) -> SceneResult:
    """Blocking: callers in async code run it in a thread. RuntimeError("cancelled") only when nothing was drawn yet.
    With a `ledger`, lessons seen twice are added to the prompt and the failures of the FIRST attempt (what the plain prompt gets wrong) are recorded."""
    t0 = time.monotonic()
    lessons = " ".join(x for x in (lessons, lessons_for(ledger, ART_WORKFLOW_ID, plan.scene_type) if ledger else "") if x)
    base_seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    iters: list[dict] = []
    reviews: dict[str, Review] = {}  # by picture hash, so a stopped run can still report the review of its best candidate

    def generate(attempt: int, correction: CorrectionPlan | None):
        if attempt > 0 and time.monotonic() - t0 > budget.max_seconds:
            raise _OutOfTime()
        positive, negative, (w, h) = compile_scene_prompt(plan, emphasis=correction.emphasis if correction else None, lessons=lessons)
        s = base_seed + attempt * 7919
        art = art_engine.generate(positive, negative, w, h, s, "panelflow_scene", timeout=timeout, is_cancelled=is_cancelled)
        return art.png, {"seed": s, "prompt": positive, "negative": negative, "width": art.width, "height": art.height, "engine": "qwen",
                         "workflow": art.workflow_id, "workflow_sha256": art.workflow_sha256, "prompt_id": art.prompt_id}

    def look(png: bytes) -> Review:
        rev = asyncio.run(check_scene(provider, png, plan))
        reviews[sha256_hex(png)] = rev
        return rev

    extra: list[str] = []
    try:
        res = refine_image(generate=generate, review=look, record=lambda data, **meta: record_candidate(ws, key, iters, data, **meta),
                           budget=Budget(max_attempts=budget.max_attempts), is_cancelled=is_cancelled)
        png, review, status, history = res.png, res.review, res.status, res.iterations
    except (_OutOfTime, RuntimeError) as exc:
        reason = "time budget used" if isinstance(exc, _OutOfTime) else "cancelled" if is_cancelled() else None
        best = best_iteration(iters)
        if reason is None or best is None:
            raise
        png, review, status, history = (ws / best["file"]).read_bytes(), reviews.get(best["sha256"]), "needs_review", iters
        extra.append(reason)

    first = reviews.get(iters[0]["sha256"]) if iters else None
    if ledger and first:
        record_outcome(ledger, ART_WORKFLOW_ID, plan.scene_type, first)

    out = ws / "panels" / f"{key}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    unmet = [i.item for i in review.items if not i.passed] if review else []
    result = SceneResult(
        image_path=f"panels/{key}.png", plan=plan, review=review, status=status, unmet=unmet + extra,
        unverified=review is None or any("unverified" in r for r in review.reasons), seconds=round(time.monotonic() - t0, 1),
        iterations=[{k: i.get(k) for k in ("n", "kind", "file", "sha256", "seed", "review")} for i in history],
    )
    (ws / "panels" / f"{key}.json").write_text(json.dumps(result.model_dump(), indent=2, default=str), encoding="utf-8")
    return result
