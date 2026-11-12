"""The Casting Assistant: which approved voice reads which character.

The rules the workflow sets:

- the narrator's own configured voice is the default for the narrator;
- an assignment the owner already made is kept, never replaced;
- a character with no suitable voice is flagged, not silently given one;
- a recommendation is a proposal: it never overwrites an assignment on its own.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.config.settings import settings
from engine.narration.artifacts import NARRATOR_ID, SeriesBible
from engine.narration.runtime.roles import VoiceProfile, load_tts_config, load_voice_catalog

NARRATOR_PROFILE_ID = "narrator"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CastAssignment(_Strict):
    """One character, the voice profile it reads with, and where that decision came from."""

    character_id: str
    profile_id: str
    source: Literal["assigned", "recommended", "narrator"]


class CastPlan(_Strict):
    """The resolved cast: what is set, what is proposed, and what could not be cast."""

    series_key: str
    assignments: list[CastAssignment] = Field(default_factory=list)
    uncast: list[str] = Field(default_factory=list)  # characters with no voice at all
    recommendations: list[CastAssignment] = Field(default_factory=list)  # proposals, not applied

    def assignment_of(self, character_id: str) -> CastAssignment | None:
        return next((a for a in self.assignments if a.character_id == character_id), None)

    def profile_of(self, character_id: str, catalog: list[VoiceProfile]) -> VoiceProfile | None:
        """The approved profile a character reads with, or None when it has none."""
        a = self.assignment_of(character_id)
        return next((p for p in catalog if p.id == a.profile_id), None) if a else None

    def engine_voice_of(self, character_id: str, catalog: list[VoiceProfile],
                        fallback: str = "") -> str:
        """The engine voice id a character reads with; the narrator's voice when it has none of its own."""
        profile = self.profile_of(character_id, catalog)
        return profile.voice if profile else fallback


def cast_path(series_key: str) -> Path:
    return Path(settings.app_data_dir) / "series" / series_key / "casting.json"


def load_cast(series_key: str) -> dict[str, str]:
    """The assignments the owner already made: character id -> profile id."""
    path = cast_path(series_key)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and k and v}


def save_cast(series_key: str, assignments: dict[str, str]) -> None:
    path = cast_path(series_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(assignments, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def preferred_narrator(catalog: list[VoiceProfile]) -> str:
    """The profile that reads the narration: the owner's configured voice, if it is approved."""
    configured = load_tts_config().voice
    for p in catalog:
        if p.voice == configured:
            return p.id
    for p in catalog:
        if p.id == NARRATOR_PROFILE_ID:
            return p.id
    return catalog[0].id if catalog else NARRATOR_PROFILE_ID


def _match_gender(character_id: str, bible: SeriesBible, catalog: list[VoiceProfile],
                  taken: set[str]) -> VoiceProfile | None:
    """A voice that fits the character: their pronouns first, then anyone still free.

    The narrator's own profile is never offered to a character: the narrator reads the story
    around them, it does not become one of them.
    """
    pronouns = {c.pronouns for c in bible.characters if c.id == character_id and c.pronouns}
    wanted = {"he": "male", "him": "male", "she": "female", "her": "female"}
    gender = next((wanted[p] for p in pronouns if p in wanted), "")
    free = [p for p in catalog if p.id not in taken and p.id != NARRATOR_PROFILE_ID]
    if gender:
        fit = [p for p in free if p.gender == gender]
        if fit:
            return fit[0]
    return free[0] if free else None


def resolve_cast(
    series_key: str,
    bible: SeriesBible,
    character_ids: list[str],
    catalog: list[VoiceProfile] | None = None,
    assigned: dict[str, str] | None = None,
) -> CastPlan:
    """Work out the cast for a chapter.

    The owner's assignments win. A character without one gets a recommendation, which is
    returned as a proposal rather than applied, so nothing is decided behind the owner's back.
    """
    catalog = catalog if catalog is not None else load_voice_catalog()
    assigned = assigned if assigned is not None else load_cast(series_key)
    by_id = {p.id: p for p in catalog}
    narrator = preferred_narrator(catalog)
    assignments: list[CastAssignment] = []
    recommendations: list[CastAssignment] = []
    uncast: list[str] = []
    taken: set[str] = set()

    for cid in dict.fromkeys(character_ids):
        if cid == NARRATOR_ID:
            assignments.append(CastAssignment(character_id=cid, profile_id=narrator, source="narrator"))
            taken.add(narrator)
            continue
        keep = assigned.get(cid, "")
        if keep and keep in by_id:  # the owner's own assignment is never replaced
            assignments.append(CastAssignment(character_id=cid, profile_id=keep, source="assigned"))
            taken.add(keep)
            continue
        fit = _match_gender(cid, bible, catalog, taken)
        if fit is None:
            uncast.append(cid)
            continue
        recommendations.append(CastAssignment(character_id=cid, profile_id=fit.id, source="recommended"))
        taken.add(fit.id)

    return CastPlan(series_key=series_key, assignments=assignments, uncast=uncast,
                    recommendations=recommendations)


def speakers_of(script) -> list[str]:
    """The characters that read a script, the narrator first."""
    out = [NARRATOR_ID]
    out += [ln.speaker_id for ln in script.lines
            if getattr(ln, "speaker_id", NARRATOR_ID) != NARRATOR_ID]
    return list(dict.fromkeys(out))


def cast_for_script(series_key: str, bible: SeriesBible, script,
                     catalog: list[VoiceProfile] | None = None) -> tuple[CastPlan, dict[str, str]]:
    """The cast of a script and the engine voice each character reads with.

    The map holds only the characters with a voice of their own: the narrator's voice is
    the fallback for anyone else.
    """
    catalog = catalog if catalog is not None else load_voice_catalog()
    plan = resolve_cast(series_key, bible, speakers_of(script), catalog)
    voices = {}
    for cid in speakers_of(script):
        if cid == NARRATOR_ID:
            continue
        profile = plan.profile_of(cid, catalog)
        if profile is not None:
            voices[cid] = profile.voice
    return plan, voices


def apply_recommendations(plan: CastPlan, series_key: str, catalog: list[VoiceProfile] | None = None) -> dict[str, str]:
    """The owner accepts the proposals: they become the assignments, and are kept from now on."""
    catalog = catalog if catalog is not None else load_voice_catalog()
    known = {p.id for p in catalog}
    current = load_cast(series_key)
    for rec in plan.recommendations:
        if rec.profile_id in known and rec.character_id not in current:
            current[rec.character_id] = rec.profile_id
    if current:
        save_cast(series_key, current)
    return current
