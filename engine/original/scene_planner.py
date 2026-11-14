"""The planner: a vague brief -> a complete ScenePlan with proposed defaults, at most 3 questions, and the owner's corrections applied safely.

What the brief did not state is filled from the playbook by code (never by the model) and named in `plan.assumed`; only those high-impact items are asked about.
The local 9B model is a noisy writer, so every plan is checked by `validate_plan` and retried with the concrete problems.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from engine.original.scene_plan import (
    ActorPlan, CameraPlan, ContactPlan, LightPlan, Playbook, ScenePlan, load_playbook, scene_types, validate_plan,
)

MAX_BRIEF_CHARS = 1000
MAX_QUESTIONS = 3
SYSTEM = "You are a film director's staging assistant. You turn a short idea into a precise shot plan and answer in the requested JSON only."

ANGLE_WORDS = {
    "low": r"from below|low[- ]angle|looking up|worm'?s",
    "high": r"from above|high[- ]angle|bird'?s|overhead|looking down",
    "eye_level": r"eye[- ]level",
    "dutch": r"dutch|tilted",
}
LIGHT_WORDS = r"back[- ]?lit|from behind|rim light|side light|lit from|light from|lit by|lighting|spotlight|silhouette"


class _CameraOut(BaseModel):
    angle: Literal["eye_level", "low", "high", "dutch"] | None = None
    distance: Literal["close", "medium", "wide"] | None = None
    note: str = ""


class _LightOut(BaseModel):
    direction: Literal["front", "back", "left", "right", "top", "below"] | None = None
    quality: str = ""
    color: str = ""


class _PlanOut(BaseModel):
    actors: list[ActorPlan] = Field(default_factory=list)
    contacts: list[ContactPlan] = Field(default_factory=list)
    camera: _CameraOut | None = None
    light: _LightOut | None = None
    depth: dict[str, str] = Field(default_factory=dict)
    mood: str = ""
    setting: str = ""


class _TypeOut(BaseModel):
    scene_type: str


class Question(BaseModel):
    field: str  # dotted path, e.g. "camera.angle" or "actors.hero.action_state"
    text: str
    default: str


class Proposal(BaseModel):
    plan: ScenePlan
    summary: str
    questions: list[Question]


def _keyword_hit(word: str, text: str) -> bool:
    # long keywords match as word starts ("fight" -> "fights"); short ones ("war", "vs") only as whole words
    return bool(re.search(rf"\b{re.escape(word)}" + (r"\b" if len(word) <= 3 else ""), text))


def classify_scene_type(brief: str) -> str | None:
    """The scene type with the most playbook keyword hits; None when nothing hits or two types tie (then the model decides)."""
    text = brief.lower()
    scores = {t: sum(_keyword_hit(k, text) for k in load_playbook(t).keywords) for t in scene_types()}
    best = max(scores.values(), default=0)
    winners = [t for t, s in scores.items() if s == best]
    return winners[0] if best > 0 and len(winners) == 1 else None


def _stated(brief: str, playbook: Playbook, plan_out: _PlanOut) -> set[str]:
    """Which high-impact items the brief itself says, decided by rules on the brief's words."""
    text = brief.lower()
    found: set[str] = set()
    if any(re.search(p, text) for p in ANGLE_WORDS.values()):
        found.add("camera.angle")
    if re.search(LIGHT_WORDS, text):
        found.add("light.direction")
    # an actor's state counts as stated only when the brief says the state that was chosen for it ("lost her friend" does not state "grieving")
    found.update(f"actors.{a.id}.action_state" for a in plan_out.actors if re.search(rf"\b{re.escape(a.action_state[:5])}", text))
    return found


def _build(brief: str, scene_type: str, out: _PlanOut, playbook: Playbook) -> ScenePlan:
    stated = _stated(brief, playbook, out)
    d = playbook.defaults
    cam, light = out.camera or _CameraOut(), out.light or _LightOut()
    assumed: list[str] = []
    angle = cam.angle if "camera.angle" in stated and cam.angle else d["camera"]["angle"]
    direction = light.direction if "light.direction" in stated and light.direction else d["light"]["direction"]
    if "camera.angle" not in stated or not cam.angle:
        assumed.append("camera.angle")
    if "light.direction" not in stated or not light.direction:
        assumed.append("light.direction")
    if not cam.distance:
        assumed.append("camera.distance")
    assumed += [f"actors.{a.id}.action_state" for a in out.actors if f"actors.{a.id}.action_state" not in stated]
    return ScenePlan(
        scene_type=scene_type, brief=brief, actors=out.actors, contacts=out.contacts,
        camera=CameraPlan(angle=angle, distance=cam.distance or d["camera"]["distance"], note=cam.note),
        light=LightPlan(direction=direction, quality=light.quality or d["light"].get("quality", ""), color=light.color),
        depth={**d.get("depth", {}), **out.depth}, mood=out.mood, setting=out.setting, assumed=assumed,
    )


async def _ask_plan(provider, prompt: str, check, attempts: int = 4):
    """Retries with the concrete problems (same loop as story._ask, with a staging system prompt)."""
    feedback: list[str] = []
    for _ in range(attempts):
        text = prompt + ("\n\nYour last answer had these problems, fix them all:\n- " + "\n- ".join(feedback[:8]) if feedback else "")
        raw = await provider.generate_structured(text, _PlanOut, system_prompt=SYSTEM, temperature=0.4, max_tokens=1500, num_ctx=8192)
        try:
            out = raw if isinstance(raw, _PlanOut) else _PlanOut(**raw)
        except ValueError as exc:
            feedback = [f"not valid plan JSON: {str(exc)[:200]}"]
            continue
        feedback = check(out)
        if not feedback:
            return out
    raise ValueError("scene plan failed validation after retries: " + "; ".join(feedback[:6]))


def _questions(plan: ScenePlan, playbook: Playbook) -> list[Question]:
    qs: list[Question] = []
    for path in playbook.high_impact:
        paths = [f"actors.{a.id}.action_state" for a in plan.actors] if "*" in path else [path]
        for p in paths:
            if p in plan.assumed:
                qs.append(Question(field=p, text=playbook.questions[path], default=_get(plan, p)))
    return qs[:MAX_QUESTIONS]


def _get(plan: ScenePlan, path: str) -> str:
    parts = path.split(".")
    if parts[0] == "actors":
        return str(getattr(next(a for a in plan.actors if a.id == parts[1]), parts[2]))
    return str(getattr(getattr(plan, parts[0]), parts[1]))


async def propose(provider, brief: str, scene_type: str | None = None) -> Proposal:
    """ValueError for an empty brief (before any model call) or a plan that stays invalid after retries."""
    brief = " ".join(brief.split())[:MAX_BRIEF_CHARS]
    if not brief:
        raise ValueError("The brief is empty: describe the picture in a sentence")
    scene_type = scene_type or classify_scene_type(brief)
    if scene_type is None:
        raw = await provider.generate_structured(
            f"Brief: {brief}\nWhich scene type is it: {', '.join(scene_types())}? Answer with scene_type only.", _TypeOut,
            system_prompt=SYSTEM, temperature=0.0, max_tokens=50, num_ctx=4096)
        scene_type = (raw.get("scene_type") if isinstance(raw, dict) else raw.scene_type) or ""
    playbook = load_playbook(scene_type)  # ValueError for an unknown type
    prompt = (
        f"Brief: \"{brief}\"\nScene type: {scene_type}.\nPlan this single picture. Only include people the brief mentions or clearly implies "
        f"(a picture of a place alone has no actors). Fill: actors (id = one short lowercase word such as hero or guard, one-line description, side left|center|right, "
        f"depth, action_state, expression), contacts (source, target, body_part, direction as seen on screen), camera (angle eye_level|low|high|dutch, "
        f"distance close|medium|wide), light (direction front|back|left|right|top|below), depth layers, mood, setting. Leave camera or light fields out when "
        f"the brief does not say them.\nAllowed action_state values: {playbook.action_states}.\nStaging rules:\n- " + "\n- ".join(playbook.staging_rules))

    def check(out: _PlanOut) -> list[str]:
        return validate_plan(_build(brief, scene_type, out, playbook), playbook)

    plan = _build(brief, scene_type, await _ask_plan(provider, prompt, check), playbook)
    return Proposal(plan=plan, summary=plan_to_words(plan), questions=_questions(plan, playbook))


_SIDE = {"left": "on the left", "center": "in the centre", "right": "on the right"}
_ANGLE = {"eye_level": "eye-level view", "low": "low angle", "high": "high angle", "dutch": "tilted angle"}
_DIST = {"close": "close shot", "medium": "medium shot", "wide": "wide shot"}
_LIGHT = {"front": "light from the front", "back": "light from behind", "left": "light from the left", "right": "light from the right",
          "top": "light from above", "below": "light from below"}


def plan_to_words(plan: ScenePlan) -> str:
    """One plain sentence the owner can read and correct."""
    parts = [f"{_ANGLE[plan.camera.angle]}, {_DIST[plan.camera.distance]}"]
    for a in plan.actors:
        hit = next((c for c in plan.contacts if c.source == a.id and c.direction), None)
        parts.append(f"{a.id} {_SIDE[a.side]} {a.action_state}" + (f" {hit.direction}" if hit else ""))
    parts.append(_LIGHT[plan.light.direction])
    return ", ".join(parts)


def apply_corrections(plan: ScenePlan, playbook: Playbook, corrections: dict[str, str]) -> ScenePlan:
    """Dotted-path corrections ("camera.angle", "actors.hero.side", "depth.background", "mood"). The plan is returned changed, or ValueError with the
    problems and the original untouched (it is never mutated)."""
    d = plan.model_dump()
    for path, value in corrections.items():
        parts = path.split(".")
        if parts[0] in ("mood", "setting") and len(parts) == 1:
            d[parts[0]] = value
        elif parts[0] in ("camera", "light") and len(parts) == 2 and parts[1] in d[parts[0]]:
            d[parts[0]][parts[1]] = value
        elif parts[0] == "depth" and len(parts) == 2:
            d["depth"][parts[1]] = value
        elif parts[0] == "actors" and len(parts) == 3 and any(a["id"] == parts[1] and parts[2] in a for a in d["actors"]):
            next(a for a in d["actors"] if a["id"] == parts[1])[parts[2]] = value
        else:
            raise ValueError(f"cannot correct {path!r}")
    d["assumed"] = [p for p in d["assumed"] if p not in corrections]
    new = ScenePlan(**d)  # pydantic's ValidationError is a ValueError: a bad enum value is rejected here
    problems = validate_plan(new, playbook)
    if problems:
        raise ValueError("; ".join(problems))
    return new
