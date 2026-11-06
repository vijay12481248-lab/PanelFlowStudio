"""Correction planner: given a Review (and the candidates made so far), decide what to do next. Pure logic: no GPU, no model, no I/O.

Why it exists: the story loop in `art.generate_art` hard-codes one policy (anatomy/contact defect -> one inpaint with a heuristic region, anything
else -> redraw with emphasis, three attempts) and nothing else can reuse it. The planner states that policy as data, so a loop for any caller can
execute it and a test can check it:

    accept        the picture passes; stop.
    repair_local  every failure is a located, existing-but-wrong thing (a model-reported box), an edit tool is available and the repair budget
                  is not spent: edit inside the boxes, keep everything else.
    regenerate    something is missing or composition-level wrong, or repair is not possible: redraw with a new seed and a refined prompt.
    accept_low    the budget is spent and the best candidate is acceptable but flagged.
    human_review  the budget is spent / no progress / the reviewer cannot be trusted: stop and keep the best candidate for a person.

It never invents a location: a box comes from the reviewer or there is none, and a region guessed from the defect type is used only when the
caller explicitly allows it (`allow_heuristic_masks`).
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from engine.original.models import ItemVerdict, Review

RANK = {"accept": 2, "accept_low": 1}
DEFECT_FIX = {  # generic, never story-specific
    "polycephaly": "redraw so each figure has a single head",
    "extra_limbs": "remove the extra limb",
    "missing_limbs": "draw the complete limb",
    "distorted_digits": "redraw the hand with the correct number of fingers",
    "limb_topology": "redraw the limb with a natural joint angle",
    "unanchored_object": "rest the object on a surface so it does not float",
    "disconnected_interaction": "make the hand grip the object",
}


@dataclass(frozen=True)
class Budget:
    max_attempts: int = 3  # full generations (a repair belongs to the attempt that it repairs)
    max_repairs_per_generation: int = 1
    max_local_targets: int = 2  # more regions than this is cheaper and cleaner to redraw
    min_confidence: float = 0.35  # below this the reviewer's verdict is not trusted
    plateau_after: int = 3  # generations with the same failures and no score gain stop the loop early (only bites when max_attempts > 3)
    plateau_epsilon: float = 0.02


class PlanTarget(BaseModel):
    item: str
    status: str
    severity: str = ""
    defect_type: str = ""
    evidence: str = ""
    bbox: list[float] | None = None
    correction: str  # what to change, in plain words


class CorrectionPlan(BaseModel):
    action: str  # accept | repair_local | regenerate | accept_low | human_review
    reason: str
    final: bool = False  # the loop stops after this plan
    select: int | None = None  # for a final plan: the iteration `n` to keep
    targets: list[PlanTarget] = Field(default_factory=list)
    mask_source: str = ""  # "vlm" (a model-reported box) | "heuristic" (guessed from the defect type, only when allowed) | ""
    emphasis: list[str] = Field(default_factory=list)  # regenerate: what the next prompt must state first
    avoid_defects: list[str] = Field(default_factory=list)  # regenerate: defect types to steer away from
    widen_frame: bool = False
    simplify: bool = False
    new_seed: bool = False
    flags: list[str] = Field(default_factory=list)


def best_iteration(iterations: list[dict]) -> dict | None:
    """The candidate to keep: best decision rank, then score, then confidence. Ties keep the earlier one (as the story loop does).
    A candidate with no review only wins when nothing was reviewed."""
    def key(i: dict):
        r = i.get("review")
        return (-1, 0.0, 0.0) if not r else (RANK.get(r["decision"], 0), r.get("score") or 0.0, r.get("confidence") or 0.0)
    best = None
    for i in iterations:
        if best is None or key(i) > key(best):
            best = i
    return best


def _target(item: ItemVerdict) -> PlanTarget:
    if item.defect_type in DEFECT_FIX:
        fix = DEFECT_FIX[item.defect_type]
    else:
        fix = {"missing": f"add: {item.item}", "incorrect": f"change so that: {item.item}"}.get(item.status, f"make clearer: {item.item}")
    return PlanTarget(item=item.item, status=item.status, severity=item.severity, defect_type=item.defect_type,
                      evidence=item.evidence[:160], bbox=list(item.bbox) if item.bbox and item.bbox_source == "vlm" else None, correction=fix)


def _is_critical(item: ItemVerdict) -> bool:
    return item.critical or item.severity == "critical"


def _plateau(gens: list[dict], budget: Budget) -> bool:
    window = [g for g in gens[-budget.plateau_after:] if g.get("review")]
    if len(window) < budget.plateau_after:
        return False
    same_failures = set(window[-1]["review"].get("failed", [])) == set(window[-2]["review"].get("failed", []))
    gain = window[-1]["review"]["score"] - window[0]["review"]["score"]
    return same_failures and gain < budget.plateau_epsilon


def plan_correction(review: Review | None, history: list[dict], *, budget: Budget = Budget(), edit_available: bool = False,
                    allow_heuristic_masks: bool = False) -> CorrectionPlan:
    """`history` is the candidates of THIS run (Phase 2 `iterations`), including the one `review` is about."""
    gens = [i for i in history if i.get("kind") == "generate"]
    attempts = len(gens)
    best = best_iteration(history)

    def stop(action: str, reason: str, flags: list[str]) -> CorrectionPlan:
        return CorrectionPlan(action=action, reason=reason, final=True, select=best["n"] if best else None, flags=flags)

    if review is None:
        return stop("human_review", "the reviewer returned no verdict, so nothing can be corrected or trusted", ["unverified"])
    flags = ["unverifiable_requirements"] if review.unverifiable else []
    if review.decision == "accept":
        return stop("accept", "the picture passes the review", flags)
    if review.confidence < budget.min_confidence:
        return stop("human_review", f"reviewer confidence {review.confidence:.2f} is below {budget.min_confidence:.2f}: the verdict is not trusted",
                    flags + ["low_confidence"])

    failures = [i for i in review.items if not i.passed]
    local = [i for i in failures if i.repairable_locally and i.bbox and i.bbox_source == "vlm"]
    guessed = [i for i in failures if i not in local and i.category in ("anatomy", "spatial_contact") and allow_heuristic_masks]
    rest = [i for i in failures if i not in local and i not in guessed]
    last_gen_n = gens[-1]["n"] if gens else None
    repairs = [i for i in history if i.get("kind") == "repair" and i.get("parent") == last_gen_n]
    targets = local + guessed

    can_repair = (edit_available and targets and not any(_is_critical(i) for i in rest) and len(targets) <= budget.max_local_targets
                  and len(repairs) < budget.max_repairs_per_generation)
    if can_repair:
        return CorrectionPlan(action="repair_local", reason=f"{len(targets)} located defect(s); everything else in the picture passes",
                              targets=[_target(i) for i in targets], mask_source="vlm" if not guessed else "heuristic", flags=flags)

    if attempts >= budget.max_attempts:
        kept = (best or {}).get("review") or {}
        if kept.get("decision") == "accept_low":
            return stop("accept_low", f"{attempts} attempts used; the best candidate is acceptable but flagged", flags)
        return stop("human_review", f"{attempts} attempts used and no candidate passes", flags)
    if _plateau(gens, budget):
        return stop("human_review", "the same failures came back with no score gain: more attempts will not help", flags + ["plateau"])

    ordered = sorted((i for i in failures if i.category not in ("anatomy", "spatial_contact")), key=lambda i: not _is_critical(i))
    why = ("repair is not possible here (" + ("no edit tool" if not edit_available else "a located defect is not the only failure, or the repair budget is spent") + ")"
           if targets else "something required is missing or wrong in the picture as a whole")
    return CorrectionPlan(
        action="regenerate", reason=why, targets=[_target(i) for i in failures],
        emphasis=[i.item for i in ordered][:5],
        avoid_defects=list(dict.fromkeys(i.defect_type for i in failures if i.defect_type)),
        widen_frame=attempts >= 2, simplify=attempts >= 2, new_seed=True, flags=flags)
