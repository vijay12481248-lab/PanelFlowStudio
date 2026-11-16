"""PanelFlow Studio - Visual Semantics to Foley Cues Engine.

Analyzes ChronoFlow scene visual prompts, action directions, and narration to
automatically design and populate layered soundscapes (Ambience, Action Foley, SFX, and Dialogue)
in the Audio Studio Sound Plan with zero-VRAM procedural synthesis.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Literal

from engine.audio.studio.plan import Cue, SoundPlan, snap

logger = logging.getLogger("panelflow.audio.foley_generator")

# Semantic keyword rules for environmental ambience
AMBIENCE_RULES: list[tuple[list[str], str, float]] = [
    (["rain", "storm", "downpour", "drizzle", "monsoon", "thunderstorm"], "rain", -22.0),
    (["wind", "gale", "breeze", "blizzard", "howling", "gust", "mountain top"], "wind", -23.0),
    (["fire", "campfire", "flames", "burning", "torch", "inferno", "blaze"], "fire", -22.0),
    (["night", "midnight", "cricket", "stars", "moonlit", "dusk", "evening"], "night", -25.0),
    (["thunder", "lightning", "stormy sky"], "thunder", -18.0),
    (["dungeon", "castle", "hall", "corridor", "interior", "office", "room", "cave"], "room_tone", -26.0),
]

# Semantic keyword rules for physical action foley
ACTION_RULES: list[tuple[list[str], str, str, float, float]] = [
    # (keywords, track, kind, gain_db, relative_hit_offset_s)
    (["sword", "blade", "katana", "clash", "parry", "steel", "strike with sword"], "foley", "blade_clash", -11.0, 0.4),
    (["unsheathe", "sheathe", "draw sword", "ring of steel", "shimmer"], "foley", "sword_ring", -12.0, 0.2),
    (["punch", "kick", "slam", "smash", "heavy impact", "thud", "body fall", "crash"], "foley", "heavy_impact", -10.0, 0.5),
    (["explode", "explosion", "blast", "detonation", "bomb", "burst"], "sfx", "explosion", -8.0, 0.3),
    (["whoosh", "dash", "swing", "leap", "jump", "dodge", "speed", "evade", "fly"], "sfx", "whoosh", -12.0, 0.3),
    (["walk", "step", "running", "stride", "footstep", "sneak", "pacing"], "foley", "footstep", -14.0, 0.4),
    (["cloak", "cape", "coat", "robe", "jacket", "cloth rustle", "turn around"], "foley", "cloth_rustle", -16.0, 0.3),
    (["charge", "power up", "energy surge", "rising power", "glow"], "sfx", "riser", -13.0, 0.1),
]


def detect_ambience_kind(text: str) -> tuple[str, float]:
    """Identify matching atmospheric ambience and default gain from scene description."""
    t = text.lower()
    for keywords, kind, gain in AMBIENCE_RULES:
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in keywords):
            return kind, gain
    # Default to subtle room tone
    return "room_tone", -26.0


def detect_action_cues(text: str) -> list[tuple[str, str, float, float]]:
    """Identify action foley effects from scene prompt (track, kind, gain_db, hit_offset)."""
    t = text.lower()
    matches: list[tuple[str, str, float, float]] = []
    seen_kinds: set[str] = set()

    for keywords, track, kind, gain, offset in ACTION_RULES:
        if kind in seen_kinds:
            continue
        if any(re.search(rf"\b{re.escape(k)}\b", t) for k in keywords):
            matches.append((track, kind, gain, offset))
            seen_kinds.add(kind)
            if len(matches) >= 2:  # Max 2 action foley cues per shot to prevent muddy clutter
                break

    return matches


def parse_scene_audio_cues(
    scene: dict,
    shot_index: int,
    t_start: float,
    t_end: float,
    fps: float = 24.0,
) -> list[Cue]:
    """Generate layered Cue objects (Ambience, Action Foley, SFX, Dialogue) for a single storyboard scene."""
    cues: list[Cue] = []
    shot_dur = max(0.5, t_end - t_start)
    prompt = (scene.get("prompt") or "").strip()
    narration = (scene.get("narration") or "").strip()
    action_text = (scene.get("act") or scene.get("direction") or "").strip()
    full_context = f"{prompt} {action_text} {narration}".strip()

    # 1. Ambience Cue (spans full shot duration on 'ambience' track)
    amb_kind, amb_gain = detect_ambience_kind(full_context)
    cue_amb = Cue(
        id=f"cue_amb_{shot_index}_{uuid.uuid4().hex[:6]}",
        track="ambience",
        kind=amb_kind,
        intent=f"Shot {shot_index} atmospheric {amb_kind} bed",
        t_in=snap(t_start, fps),
        t_out=snap(t_end, fps),
        gain_db=amb_gain,
        fade_in=0.3,
        fade_out=0.3,
        mode="auto",
    )
    cues.append(cue_amb)

    # 2. Action Foley / SFX Cues
    actions = detect_action_cues(full_context)
    if actions:
        for act_idx, (track, kind, gain, offset) in enumerate(actions):
            hit_t = snap(t_start + min(offset, shot_dur * 0.5), fps)
            foley_dur = min(1.8, max(0.4, shot_dur - offset))
            cue_foley = Cue(
                id=f"cue_{kind}_{shot_index}_{act_idx + 1}_{uuid.uuid4().hex[:6]}",
                track=track,
                kind=kind,
                intent=f"Shot {shot_index} {kind.replace('_', ' ')}",
                t_in=hit_t,
                t_out=snap(hit_t + foley_dur, fps),
                hit_t=hit_t,
                gain_db=gain,
                mode="auto",
            )
            cues.append(cue_foley)
    elif prompt:
        hit_t = snap(t_start + 0.3, fps)
        cue_foley = Cue(
            id=f"cue_cloth_rustle_{shot_index}_1_{uuid.uuid4().hex[:6]}",
            track="foley",
            kind="cloth_rustle",
            intent=f"Shot {shot_index} subtle foley presence",
            t_in=hit_t,
            t_out=snap(min(t_end, hit_t + 1.0), fps),
            hit_t=hit_t,
            gain_db=-18.0,
            mode="auto",
        )
        cues.append(cue_foley)

    # 3. Dialogue / Narration Cue
    if narration:
        cue_dlg = Cue(
            id=f"cue_dlg_{shot_index}_{uuid.uuid4().hex[:6]}",
            track="dialogue",
            kind="speech",
            intent=narration,
            t_in=snap(t_start + 0.15, fps),
            t_out=snap(max(t_start + 0.5, t_end - 0.2), fps),
            gain_db=0.0,
            mode="auto",
        )
        cues.append(cue_dlg)

    return cues


def auto_populate_sound_plan(
    plan_id: str,
    scenes: list[dict],
    auto_source: bool = True,
) -> SoundPlan:
    """Analyze ChronoFlow scenes, compile multi-track cues, and optionally source audio takes immediately.
    
    Args:
        plan_id: Identifier of the SoundPlan in PlanStore.
        scenes: List of storyboard scene dicts (with 'prompt', 'narration', 'duration', etc.).
        auto_source: Whether to immediately render/source procedural takes via AudioEngine.
    """
    from engine.api.routers.audio_studio import get_engine
    engine = get_engine()

    with engine.store.lock(plan_id):
        plan = engine.store.load(plan_id)
        fps = plan.fps or 24.0

        # Preserve existing non-draft / user-edited cues if any
        preserved_cues: list[Cue] = [
            c for c in plan.cues if c.chosen_take or c.status == "ready" or c.mode == "ask"
        ]

        generated_cues: list[Cue] = []
        curr_t = 0.0

        for idx, sc in enumerate(scenes, 1):
            dur = float(sc.get("duration") or 3.4)
            t_start = curr_t
            t_end = curr_t + dur

            shot_cues = parse_scene_audio_cues(
                scene=sc,
                shot_index=idx,
                t_start=t_start,
                t_end=t_end,
                fps=fps,
            )
            generated_cues.extend(shot_cues)
            curr_t += dur

        # Merge cues
        plan.cues = preserved_cues + generated_cues
        original_note = plan.note
        if not plan.note or plan.note in ("created", "draft") or plan.note.startswith("Soundtrack -") or plan.note.startswith("sourced"):
            plan.note = f"Auto-Designed Foley & Soundscape ({len(scenes)} shots, {len(plan.cues)} cues)"
        saved_plan = engine.store.save(plan, note="auto_foley_populated")

    # If auto_source requested, source all newly added cues outside the lock
    if auto_source:
        logger.info("Auto-sourcing %d procedural cues for SoundPlan %s...", len(generated_cues), plan_id)
        for c in generated_cues:
            if c.track in ("ambience", "foley", "sfx"):
                try:
                    engine.source_cue(plan_id, c.id, mode="auto")
                except Exception as exc:
                    logger.warning("Could not auto-source cue %s (%s): %s", c.id, c.kind, exc)

        with engine.store.lock(plan_id):
            plan = engine.store.load(plan_id)
            if original_note and original_note not in ("created", "draft") and not original_note.startswith("Soundtrack -") and not original_note.startswith("sourced"):
                plan.note = original_note
            else:
                plan.note = f"Auto-Designed Foley & Soundscape ({len(scenes)} shots, {len(plan.cues)} cues)"
            saved_plan = engine.store.save(plan, note=plan.note)

    return saved_plan
