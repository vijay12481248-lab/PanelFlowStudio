"""What the image model gets wrong when it is told plainly, kept per model and scene type so the next prompt can say it differently.

Built on the existing `MistakeLedger` (`engine/creative/mistakes.py`; pass a file under the app-data folder, never the repo's vault ledger). A failure is keyed by
what failed (camera angle, a pose word, placement, count, contact), never by story words, so a lesson learned on one story helps the next. The reviewer is a noisy
9B judge: a failure is only a lesson after it has been seen twice (`recurrence_count`), a single sighting is recorded and waits.
"""
from __future__ import annotations

import re

from engine.creative.mistakes import MistakeLedger
from engine.creative.schema import MistakeSeverity
from engine.original.models import Review
from engine.original.scene_prompt import CAMERA_FIX

POSE_FIX = {
    "striking": "The attacker's arm or weapon is fully extended toward the opponent in mid-motion.",
    "blocking": "The defender's arms or weapon are raised in front of the body to stop the strike.",
    "readying": "Knees bent, fists or weapon raised in a guard stance, not yet attacking.",
    "struck": "Body recoiling backwards from the hit, head turned away, off balance.",
    "falling": "Body tilted far over, feet leaving the ground.",
    "dodging": "Torso twisted sideways away from the attack, one foot stepping aside.",
}
PLACEMENT_FIX = "Put each figure exactly on the side stated, with clear empty space between the figures."
COUNT_FIX = "Show exactly the stated number of people, each one fully visible."
CONTACT_FIX = "The weapon or hand visibly touches or reaches the other figure."


def lesson_domain(model: str, scene_type: str) -> str:
    return f"scene:{model}:{scene_type}"


def _classify(item) -> tuple[str, str, str] | None:
    """(flawed_pattern, prevention_rule, category) from what kind of requirement failed; None for kinds that are not lessons (light, depth, framing)."""
    text = item.item.lower()
    if item.kind == "camera":
        angle = next((a for a, w in (("low", "low angle"), ("high", "high angle"), ("eye_level", "eye level"), ("dutch", "dutch")) if w in text), None)
        return (f"camera angle '{angle}' not achieved", CAMERA_FIX[angle], "camera") if angle else None
    if item.kind == "placement":
        return "figure not on the planned side", PLACEMENT_FIX, "placement"
    if item.kind == "subject":
        return "wrong number of figures", COUNT_FIX, "subject"
    if item.kind == "pose" and " reaches " in text:
        return "contact between figures not shown", CONTACT_FIX, "contact"
    m = re.search(r" is ([a-z_]+)$", text) if item.kind == "pose" else None
    if m:
        state = m.group(1)
        return f"pose '{state}' not shown", POSE_FIX.get(state, f"Show the '{state}' state unmistakably in the whole body and face."), "pose"
    return None


def record_outcome(ledger: MistakeLedger, model: str, scene_type: str, review: Review, fixed_by: str = "") -> int:
    """One sighting per failure pattern per review. Only items the reviewer actually judged wrong ("missing" or "incorrect") count: a reviewer that judged
    nothing, or marked its own review unverified, teaches nothing. Returns how many patterns were written."""
    if any("unverified" in r for r in review.reasons):
        return 0
    seen: set[str] = set()
    for it in review.items:
        if it.passed or it.status not in ("missing", "incorrect"):
            continue
        found = _classify(it)
        if found is None or found[0] in seen:
            continue
        seen.add(found[0])
        flawed, rule, category = found
        ledger.record_or_escalate_mistake(domain=lesson_domain(model, scene_type), flawed_pattern=flawed, prevention_rule=rule,
                                          example_good=fixed_by, category=category, severity=MistakeSeverity.HIGH)
    return len(seen)


def _fits(record, plan) -> bool:
    """A camera or pose rule only applies to a plan that asks for that very angle or state; count, placement and contact rules apply to every plan."""
    if record.category == "camera":
        return f"'{plan.camera.angle}'" in record.flawed_pattern
    if record.category == "pose":
        return any(f"'{a.action_state}'" in record.flawed_pattern for a in plan.actors)
    return True


def lessons_for(ledger: MistakeLedger, model: str, scene_type: str, min_recurrence: int = 2, plan=None) -> str:
    """The rules of failures seen at least `min_recurrence` times, most frequent first; with a `plan`, only those that fit it. "" when there are none."""
    rows = sorted((r for r in ledger.load_mistakes(lesson_domain(model, scene_type)) if r.recurrence_count >= min_recurrence and (plan is None or _fits(r, plan))),
                  key=lambda r: -r.recurrence_count)
    return " ".join(r.prevention_rule for r in rows)
