"""Check a picture against its ScenePlan.

Fast mode (the default, used inside the run loop): only the critical plan items, no description pass and no anatomy audit.
The vision model is one witness; code is the second where code can decide: the number of figures is COUNTED (a separate question that does not say the
expected number), and each actor's side comes from the centre of the box the model reports for it. An item no code witness can confirm is believed at
confidence 0.5, never twice. Full mode runs the whole reviewer on the compiled prompt with the plan's own checklist.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import BaseModel

from engine.original.models import Review
from engine.original.review import (
    STATUS_TO_ANSWER, _annotate, _count_check, _Grounded, _grounded_check, _QA, _valid_box, combine, evaluate_prompt_image,
)
from engine.original.scene_plan import ScenePlan, load_playbook
from engine.original.scene_prompt import compile_scene_prompt, describe_actor, plan_requirements

SPATIAL_KINDS = {"pose", "placement", "camera"}
SIDE_ORDER = {"left": 0, "center": 1, "right": 2}
SEEN_ANGLE = {"eye_level": "level", "low": "looks_up", "high": "looks_down", "dutch": "tilted"}


class _Blind(BaseModel):
    camera: Literal["looks_up", "level", "looks_down", "tilted"]
    figures: list[str]  # one action word per person, left to right


def _same_state(seen: str, wanted: str, groups: list[list[str]]) -> bool:
    return seen == wanted or any(seen in g and wanted in g for g in groups)


async def _blind_read(provider, image: Path | bytes, states: list[str]) -> _Blind | None:
    """The second witness for camera angle and action states: the model is asked to CLASSIFY, never to confirm, and is not told what the plan says.
    (Measured: a yes/no check accepted an eye-level fight as "low angle"; this read, 0.4-0.6 s, called it level.) None when the answer is unusable."""
    prompt = ("Describe only what you see; do not guess what was intended.\n"
              "1. camera: is the camera looking UP at the subjects from below (looks_up), level with them (level), looking DOWN on them from above "
              "(looks_down), or tilted sideways (tilted)?\n"
              f"2. figures: list every person from the LEFT of the picture to the RIGHT. For each, give the one word from {states} that best "
              "describes what that person's body is doing.")
    try:
        raw = await provider.analyze_vision(image, prompt, format_schema=_Blind.model_json_schema(), max_tokens=200, temperature=0.0)
        return _Blind(**raw) if isinstance(raw, dict) else _Blind.model_validate_json(raw)
    except Exception:
        return None


def _picture(image: Path | bytes, max_side: int | None) -> Path | bytes:
    """The picture as the model should see it. Not shrunk by default: measured, the same low-angle picture read "looks_up" at 1344x768 and "level" at 1024 and below."""
    if max_side is None:
        return image
    img = Image.open(io.BytesIO(image) if isinstance(image, bytes) else image).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _side_witness(claim_text: str, box: list[float] | None) -> bool | None:
    """True when the reported box sits where the claim says, False when it contradicts it, None when there is no usable box or no side in the claim."""
    if box is None:
        return None
    cx = (box[0] + box[2]) / 2
    if "on the left of the picture" in claim_text:
        return cx < 0.5
    if "on the right of the picture" in claim_text:
        return cx > 0.5
    if "in the centre of the picture" in claim_text:
        return abs(cx - 0.5) <= 0.25
    return None


async def check_scene(provider, image: Path | bytes, plan: ScenePlan, *, full: bool = False, max_side: int | None = None) -> Review:
    claims = plan_requirements(plan)
    if full:
        positive, _, _ = compile_scene_prompt(plan)
        return await evaluate_prompt_image(provider, image, positive, claims=claims)

    claims = [c for c in claims if c.critical]
    small = _picture(image, max_side)
    try:
        grounded = await _grounded_check(provider, small, claims)
    except Exception as exc:  # reviewer unreachable: nothing is judged, and nothing is passed
        grounded = [_Grounded(n=i + 1, status="uncertain", evidence=f"reviewer unavailable: {type(exc).__name__}") for i in range(len(claims))]

    # every claim here comes from the plan, so it is visible by construction: "not_verifiable" means the picture was NOT judged, never "nothing to check"
    grounded = [g.model_copy(update={"status": "uncertain", "evidence": f"not judged: {g.evidence}"[:200]}) if g.status == "not_verifiable" else g for g in grounded]
    witnessed = [False] * len(claims)  # a second witness (code, or the blind read) agrees with the vision answer
    ordered = sorted(plan.actors, key=lambda a: SIDE_ORDER[a.side])
    playbook = load_playbook(plan.scene_type)
    blind = await _blind_read(provider, small, [*playbook.action_states, "other"])
    state_claim = {f"{describe_actor(a)} is {a.action_state}": i for i, a in enumerate(ordered)}  # claim text -> position left to right
    for k, (c, g) in enumerate(zip(claims, grounded)):
        if c.kind == "subject":  # the figure count
            seen = await _count_check(provider, small, "figures")
            if seen is not None and seen != len(plan.actors):
                grounded[k] = g.model_copy(update={"status": "incorrect", "evidence": f"counted {seen}, the plan has {len(plan.actors)}: {g.evidence}"[:200]})
            elif seen is not None:
                witnessed[k] = g.status == "correct"
        elif c.kind == "camera" and blind:
            if blind.camera != SEEN_ANGLE[plan.camera.angle]:
                grounded[k] = g.model_copy(update={"status": "incorrect", "evidence": f"a blind read saw the camera {blind.camera}: {g.evidence}"[:200]})
            else:
                witnessed[k] = g.status == "correct"
        elif c.kind == "pose" and c.text in state_claim and blind and len(blind.figures) == len(ordered):
            seen = blind.figures[state_claim[c.text]].strip().lower()
            if not _same_state(seen, ordered[state_claim[c.text]].action_state, playbook.state_groups):
                grounded[k] = g.model_copy(update={"status": "incorrect", "evidence": f"a blind read saw '{seen}': {g.evidence}"[:200]})
            else:
                witnessed[k] = g.status == "correct"
        elif c.kind == "placement":
            side_ok = _side_witness(c.text, _valid_box(g.bbox_1000))
            if side_ok is False:
                grounded[k] = g.model_copy(update={"status": "incorrect", "evidence": f"the box centre is not where the plan puts it: {g.evidence}"[:200]})
            elif side_ok:
                witnessed[k] = g.status == "correct"

    review = combine(claims, [_QA(n=n + 1, answer=STATUS_TO_ANSWER[g.status], evidence=g.evidence) for n, g in enumerate(grounded)], witnessed)
    _annotate(review, claims, grounded)
    # camera and action states rest on the agreeable yes/no witness alone when the blind read is missing or unusable: flagged, never a plain accept
    lacking = [c.text for k, c in enumerate(claims) if (c.kind == "camera" or c.text in state_claim) and not witnessed[k] and grounded[k].status == "correct"]
    if lacking and review.decision == "accept":
        review.decision = "accept_low"
        review.reasons.append("no second witness for: " + "; ".join(lacking))
    checked, kept = claims, grounded
    if checked and all(g.status == "uncertain" for g in kept):
        review.decision, review.confidence = "accept_low", 0.0
        review.reasons.append("unverified: the reviewer could not judge any item")
    return review


def spatial_failure(review: Review) -> bool:
    """A failed pose, placement, camera or contact item: words did not stage the picture, so a staging picture is the next step."""
    return any(not i.passed and (i.kind in SPATIAL_KINDS or i.category == "spatial_contact") for i in review.items)
