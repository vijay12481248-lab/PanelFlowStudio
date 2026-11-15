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
    names_mentioned: list[str] = Field(default_factory=list)  # proper names written in this panel's text
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
    pronouns: str = ""  # "he", "she" or "they"; empty when unknown


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
    evidence: list[str] = Field(default_factory=list)  # the panels this conclusion draws on
    confidence: float = Field(default=1.0, ge=0, le=1)
    uncertain: str = ""  # what the analyst is not sure about, or "" when sure


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

NARRATOR_ID = "narrator"  # the voice that reads the recap; a character id otherwise


class ScriptLine(_Strict):
    line_id: str
    panel_id: str
    text: str
    facts_used: list[Annotated[str, StringConstraints(pattern=_FACT_REF)]]
    kind: LineKind
    target_words: int = 8
    status: LineStatus = "draft"
    speaker_id: str = NARRATOR_ID  # who reads this line: the narrator, or a bible character id

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


class StopPoint(_Strict):
    """A decision the workflow cannot make on its own, and pauses for.

    The workflow pauses for the owner when the story brief is uncertain, when a
    voice needs approval, or when a proposed casting change would affect an
    assignment the owner already made. Routine generation and repair continue
    on their own.
    """

    kind: Literal["brief", "voice", "casting"]
    detail: str
    severity: Literal["block", "warn"] = "block"
    line_ids: list[str] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)  # what the owner can choose
    resolution: str = ""  # what the owner chose, once the stop point is settled


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


class LineMarks(_Strict):
    line_id: str
    emotion: str
    energy: Literal["low", "med", "high"]
    rate: float = Field(ge=0.9, le=1.1)
    pause_after_ms: int = Field(ge=150, le=800)
    emphasis_words: list[str] = Field(default_factory=list)
    intent: str = ""  # why this line is said, in one clause ("hold the tension before the reveal")


class PerformancePlan(_Strict):
    project_id: str
    script_revision: int
    revision: int = 0  # the direction as it stands; it moves when the delivery is changed
    lines: list[LineMarks] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_line_ids(self) -> "PerformancePlan":
        ids = [ln.line_id for ln in self.lines]
        if len(set(ids)) != len(ids):
            raise ValueError("line_id values must be unique")
        return self


class Word(_Strict):
    text: str
    start: float = Field(ge=0)
    end: float

    @model_validator(mode="after")
    def _ordered(self) -> "Word":
        if self.end < self.start:
            raise ValueError("word end must not precede its start")
        return self


class VoiceTake(_Strict):
    line_id: str
    audio_path: str
    duration: float = Field(gt=0)
    words: list[Word]
    lead_ms: int
    tail_ms: int
    stt_text: str
    wer: float = Field(ge=0, le=1)
    tts_model: str
    voice_id: str
    rate: float
    attempt: int = Field(ge=1, le=3)
    flagged: bool = False
    # what this take was made from, so an outdated take can be recognised later
    script_revision: int = 0  # the script revision the spoken text came from
    direction_revision: int = 0  # the performance plan revision the delivery came from
    voice_profile_id: str = ""  # the cast profile that read it, not the engine voice id
    provider: str = ""  # the TTS provider that produced it


class TimelinePanel(_Strict):
    panel_id: str
    start: float
    end: float
    cut_reason: Literal["line-start", "hold"]
    scene_id: str


class TimelineClip(_Strict):
    line_id: str
    panel_id: str
    start: float
    end: float
    audio_path: str


class LockedTimeline(_Strict):
    project_id: str
    duration: float
    panels: list[TimelinePanel]
    clips: list[TimelineClip]

    @model_validator(mode="after")
    def _consistent(self) -> "LockedTimeline":
        if len({p.panel_id for p in self.panels}) != len(self.panels):
            raise ValueError("panel_id values must be unique")
        eps, t = 1e-6, 0.0
        for p in self.panels:
            if abs(p.start - t) > eps or p.end < p.start:
                raise ValueError(f"panel {p.panel_id} is not contiguous with the one before it")
            t = p.end
        span = {p.panel_id: p for p in self.panels}
        prev = 0.0
        for c in sorted(self.clips, key=lambda c: c.start):
            p = span.get(c.panel_id)
            if p is None or c.end < c.start or c.start < p.start - eps or c.end > p.end + eps:
                raise ValueError(f"clip {c.line_id} lies outside its panel")
            if c.start < prev - eps:
                raise ValueError(f"clip {c.line_id} overlaps the clip before it")
            prev = c.end
        return self
