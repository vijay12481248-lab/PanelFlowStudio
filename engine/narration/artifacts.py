"""Typed data contracts shared by every Narration Compiler stage."""
from __future__ import annotations

from typing import Annotated, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _cap_words(value: str, limit: int, name: str) -> str:
    if len(value.split()) > limit:
        raise ValueError(f"{name} must be at most {limit} words")
    return value


class OcrDialogue(_Strict):
    region_id: str
    text: str
    speaker_id: str | None = None
    speaker_confidence: float | None = Field(default=None, ge=0, le=1)


class PanelFacts(_Strict):
    panel_id: str
    order: int
    is_story: bool
    shot: Literal["wide", "medium", "close", "insert"]
    characters_visible: list[str] = Field(default_factory=list)
    unknown_cues: dict[str, str] = Field(default_factory=dict)
    action: str
    emotion: str
    dialogue: list[OcrDialogue] = Field(default_factory=list)
    sfx: list[str] = Field(default_factory=list)
    setting: str = ""
    importance: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    needs_review: bool = False

    @field_validator("action")
    @classmethod
    def _action_len(cls, v: str) -> str:
        return _cap_words(v, 20, "action")


class BibleCharacter(_Strict):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    appearance_cues: list[str] = Field(default_factory=list)
    role: str = ""
    relationships: dict[str, str] = Field(default_factory=dict)
    catchphrases: list[str] = Field(default_factory=list)
    pronunciation: str | None = None


class BibleLocation(_Strict):
    id: str
    name: str
    description: str = ""


class NarratorVoice(_Strict):
    style_notes: list[str] = Field(default_factory=list)
    banned_phrases: list[str] = Field(default_factory=list)
    transitions: list[str] = Field(default_factory=list)


class BibleRevision(_Strict):
    version: int
    project_id: str
    applied: list[str]


class SeriesBible(_Strict):
    series_key: str
    version: int = 0
    characters: list[BibleCharacter] = Field(default_factory=list)
    locations: list[BibleLocation] = Field(default_factory=list)
    plot_so_far: str = ""
    open_threads: list[str] = Field(default_factory=list)
    glossary: dict[str, str] = Field(default_factory=dict)
    narrator_voice: NarratorVoice = Field(default_factory=NarratorVoice)
    history: list[BibleRevision] = Field(default_factory=list)

    @field_validator("plot_so_far")
    @classmethod
    def _plot_len(cls, v: str) -> str:
        return _cap_words(v, 150, "plot_so_far")


class Beat(_Strict):
    beat_id: str
    panel_ids: list[str] = Field(min_length=1)
    what_happens: str
    function: Literal["setup", "escalate", "reveal", "payoff", "cliffhanger"]
    intensity: float = Field(ge=0, le=1)


class Scene(_Strict):
    scene_id: str
    first_panel_id: str
    last_panel_id: str
    goal: str
    conflict: str
    turn: str
    beats: list[Beat] = Field(min_length=1)


class BibleProposal(_Strict):
    kind: Literal["add_character", "add_location", "update_plot", "add_thread", "close_thread"]
    payload: dict


class BeatSheet(_Strict):
    project_id: str
    scenes: list[Scene] = Field(min_length=1)
    hook: str
    chapter_summary: str
    character_resolutions: dict[str, str] = Field(default_factory=dict)
    bible_proposals: list[BibleProposal] = Field(default_factory=list)


class ArtifactIdError(ValueError):
    pass


def assert_known_ids(ids: Iterable[str], known: set[str], where: str) -> None:
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise ArtifactIdError(f"{where}: unknown ids {', '.join(unknown)}")


LineKind = Literal["hook", "narration", "paraphrase", "transition", "cliffhanger"]
LineStatus = Literal["draft", "passed", "repaired", "fallback", "needs_review"]
_FACT_REF = r"^(action|emotion|dialogue|characters|setting|sfx|beat:[A-Za-z0-9_-]+)$"


class ScriptLine(_Strict):
    line_id: str
    panel_id: str
    text: str
    facts_used: list[Annotated[str, StringConstraints(pattern=_FACT_REF)]]
    kind: LineKind
    target_words: int = 8
    status: LineStatus = "draft"

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


class ScriptIR(_Strict):
    project_id: str
    revision: int = 0
    parent_revision: int | None = None
    changed_line_ids: list[str] = Field(default_factory=list)
    lines: list[ScriptLine] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_line_ids(self) -> "ScriptIR":
        ids = [ln.line_id for ln in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("line_id values must be unique")
        return self


class LineCheck(_Strict):
    rule: str
    passed: bool
    severity: Literal["block", "warn"]
    reason: str = ""


class LineCritique(_Strict):
    line_id: str
    checks: list[LineCheck]
    scores: dict[str, bool] = Field(default_factory=dict)

    @field_validator("scores")
    @classmethod
    def _score_keys(cls, v: dict[str, bool]) -> dict[str, bool]:
        bad = set(v) - {"grounded", "clear", "voice", "flow"}
        if bad:
            raise ValueError(f"unknown score keys: {', '.join(sorted(bad))}")
        return v

    @property
    def blocked(self) -> bool:
        return any(not c.passed and c.severity == "block" for c in self.checks)


class CritiqueReport(_Strict):
    revision: int
    lines: list[LineCritique]
    coverage: float
    pace_estimate: float
    repetition: int
    gate: Literal["pass", "repair", "review"]
    gate_reasons: list[str] = Field(default_factory=list)


class ReviewItem(_Strict):
    run_id: str
    project_id: str
    series_key: str = ""
    run_dir: str
    reasons: list[str]
    line_ids: list[str]
    status: Literal["pending", "approved"] = "pending"


def check_script_ids(script: ScriptIR, story_panel_ids: list[str]) -> list[str]:
    got = [ln.panel_id for ln in script.lines]
    problems = []
    if len(got) != len(story_panel_ids):
        problems.append(f"count mismatch: {len(got)} lines for {len(story_panel_ids)} story panels")
    unknown = [p for p in got if p not in set(story_panel_ids)]
    if unknown:
        problems.append(f"unknown panel ids: {', '.join(unknown)}")
    elif len(got) == len(story_panel_ids) and got != story_panel_ids:
        problems.append("order mismatch: lines are not in reading order")
    return problems
