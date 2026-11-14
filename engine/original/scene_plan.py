"""ScenePlan: the staging of one picture written down - who stands where, what each body is doing, what touches what, camera, light, depth.

A vague brief becomes a ScenePlan (scene_planner.py); the plan becomes a prompt and a checklist (scene_prompt.py); the picture is checked against it (scene_check.py).
Playbooks (playbooks/<scene_type>.json) hold what differs per scene type: allowed action states, the questions worth asking, defaults, staging rules.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

PLAYBOOK_DIR = Path(__file__).with_name("playbooks")
Side = Literal["left", "center", "right"]
Depth = Literal["foreground", "midground", "background"]


class ActorPlan(BaseModel):
    id: str  # one short lowercase word; matches a Character.id when the actor is a known character
    description: str  # comma-separated visual tags (hair, clothes, build): becomes the character's `look`
    species: str = "human"  # "human" or what it is ("dragon"): a human tag is never put on a creature
    gender: Literal["male", "female", "neutral"] = "neutral"
    age_group: Literal["child", "teen", "adult", "elder"] = "adult"
    side: Side
    depth: Depth = "midground"
    action_state: str  # one of the playbook's action_states
    expression: str = ""


class ContactPlan(BaseModel):
    source: str
    target: str
    body_part: str = ""
    direction: str = ""  # screen-relative: left | right | up | down | up-left | down-right ...


class CameraPlan(BaseModel):
    angle: Literal["eye_level", "low", "high", "dutch"]
    distance: Literal["close", "medium", "wide"]
    note: str = ""


class LightPlan(BaseModel):
    direction: Literal["front", "back", "left", "right", "top", "below"]
    quality: str = ""
    color: str = ""


class ScenePlan(BaseModel):
    scene_type: str
    brief: str
    actors: list[ActorPlan] = Field(default_factory=list)
    contacts: list[ContactPlan] = Field(default_factory=list)
    camera: CameraPlan
    light: LightPlan
    depth: dict[str, str] = Field(default_factory=dict)  # foreground | midground | background -> what is there
    mood: str = ""
    setting: str = ""
    assumed: list[str] = Field(default_factory=list)  # dotted field paths the planner defaulted, e.g. "camera.angle"


class Playbook(BaseModel):
    scene_type: str
    keywords: list[str]
    action_states: list[str]
    high_impact: list[str]  # dotted field paths worth asking about ("actors.*.action_state" = every actor)
    defaults: dict
    questions: dict[str, str]  # one per high_impact path
    staging_rules: list[str]


def scene_types() -> list[str]:
    return sorted(p.stem for p in PLAYBOOK_DIR.glob("*.json"))


def load_playbook(scene_type: str) -> Playbook:
    path = PLAYBOOK_DIR / f"{scene_type}.json"
    if scene_type not in scene_types():
        raise ValueError(f"unknown scene type {scene_type!r}; known: {scene_types()}")
    return Playbook(**json.loads(path.read_text(encoding="utf-8")))


def _points_toward(direction: str, source_side: str, target_side: str) -> bool | None:
    """Does a screen-relative direction go from source toward target? None when it cannot be decided (centre, vertical-only, empty)."""
    horizontal = {"left", "right"} & set(direction.lower().replace("-", " ").split())
    if not horizontal or "center" in (source_side, target_side) or source_side == target_side:
        return None
    return horizontal == {target_side}


def validate_plan(plan: ScenePlan, playbook: Playbook) -> list[str]:
    """Plain-language problems; an empty list means the plan is valid. A plan with one actor or none is never penalised for missing opponents."""
    problems: list[str] = []
    actors = {a.id: a for a in plan.actors}
    for a in plan.actors:
        if a.action_state not in playbook.action_states:
            problems.append(f"{a.id}: action_state {a.action_state!r} is not one of {playbook.action_states}")
    for c in plan.contacts:
        if c.source not in actors or c.target not in actors:
            missing = [x for x in (c.source, c.target) if x not in actors]
            problems.append(f"contact {c.source} -> {c.target}: unknown actor(s) {missing}")
            continue
        if c.source == c.target:
            problems.append(f"contact: {c.source} cannot act on itself")
            continue
        if plan.scene_type != "fight":
            continue
        s, t = actors[c.source], actors[c.target]
        if s.side == t.side != "center":
            problems.append(f"{s.id} and {t.id} are both on the {s.side}; fighters in contact must stand on opposite sides")
        elif _points_toward(c.direction, s.side, t.side) is False:
            problems.append(f"contact {s.id} -> {t.id}: direction {c.direction!r} points away from {t.id} (on the {t.side})")
    return problems
