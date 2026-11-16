"""'Fix problems': the safe, mechanical repairs for what QA finds. Everything it cannot fix is returned, never hidden."""
from __future__ import annotations

from typing import Callable

from engine.audio.studio.engine import AudioEngine
from engine.audio.studio.plan import Cue, SoundPlan
from engine.audio.studio.qa import OVERRUN_S, check_plan

_RESOURCE_RULES = {"clipping", "silent", "too_loud_take"}


def _push_narration(engine: AudioEngine, plan_id: str) -> list[dict]:
    """Move later narration lines so none starts before the previous one ends (plus 0.1 s). Not applied if the last line would then run past the video."""
    with engine.store.lock(plan_id):
        plan = engine.store.load(plan_id)
        lines = sorted((c for c in plan.cues if c.kind == "narration" and c.chosen() is not None), key=lambda c: c.t_in)
        moves: list[tuple[Cue, float]] = []
        prev_end = None
        for c in lines:
            t = c.t_in
            if prev_end is not None and t < prev_end - OVERRUN_S:
                t = round(prev_end + 0.1, 3)
                moves.append((c, t))
            prev_end = t + c.chosen().duration_s
        if not moves or (prev_end is not None and prev_end > plan.duration + OVERRUN_S):
            return []
        for c, t in moves:
            c.t_in = t
        engine.store.save(plan, "fix: moved narration")
        return [{"cue_id": c.id, "rule": "narration_overrun", "action": f"moved to {t:.2f} s"} for c, t in moves]


def fix_plan(engine: AudioEngine, plan_id: str, render_cue: Callable[[SoundPlan, Cue, "object"], "object"]) -> dict:
    """Re-source cues with a clipped / silent / too loud sound or no sound (once, a different clip), and push overrunning narration later."""
    plan = engine.store.load(plan_id)
    findings = check_plan(plan, render_cue)
    fixed: list[dict] = []
    tried: set[str] = set()
    for f in findings:
        c = plan.cue(f.cue_id)
        if f.cue_id in tried:
            continue
        if f.rule in _RESOURCE_RULES or (f.rule == "no_take" and c.status == "failed"):
            tried.add(f.cue_id)
            engine.source_cue(plan_id, f.cue_id, mode="auto")
            fixed.append({"cue_id": f.cue_id, "rule": f.rule, "action": "sourced again"})
    if any(f.rule == "narration_overrun" for f in findings):
        fixed += _push_narration(engine, plan_id)
    after = engine.store.load(plan_id)
    remaining = check_plan(after, render_cue)
    fixed_ok = [x for x in fixed if not (x["action"] == "sourced again" and any(r.cue_id == x["cue_id"] and r.rule == x["rule"] for r in remaining))]
    with engine.store.lock(plan_id):   # keep the placement errors the final check measured, on top of any edit made meanwhile
        cur = engine.store.load(plan_id)
        errs = {c.id: c.placement_error_ms for c in after.cues}
        for c in cur.cues:
            if c.id in errs:
                c.placement_error_ms = errs[c.id]
        engine.store.save(cur, "fix: checked")
    return {"fixed": fixed_ok, "remaining": [r.model_dump() for r in remaining]}
