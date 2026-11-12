"""The readiness report: what is still open before the project moves to rendering.

The sync metrics say whether the timeline is well cut. The readiness report
answers the other half: is there anything left that a person must decide?

It gathers what is still open from the pieces the pipeline already keeps:
the lines awaiting review, the characters without a voice, the takes that
failed the QA, and the state of the music and sound effects.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from engine.narration.artifacts import ScriptIR, VoiceTake
from engine.narration.qa import QaReport

Severity = Literal["block", "warn"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenIssue(_Strict):
    """One thing that is still open, and what it blocks."""

    kind: Literal["line", "voice", "qa", "outdated", "music"]
    severity: Severity
    detail: str
    line_ids: list[str] = Field(default_factory=list)
    character_ids: list[str] = Field(default_factory=list)


class ReadinessReport(_Strict):
    """What is still open before the project renders."""

    ready: bool = True
    issues: list[OpenIssue] = Field(default_factory=list)
    lines_awaiting_review: list[str] = Field(default_factory=list)
    characters_without_a_voice: list[str] = Field(default_factory=list)
    failed_qa_lines: list[str] = Field(default_factory=list)
    outdated_take_lines: list[str] = Field(default_factory=list)
    music_tracks: int = 0

    @property
    def blockers(self) -> list[OpenIssue]:
        return [i for i in self.issues if i.severity == "block"]


def _review_lines(script: ScriptIR, review_line_ids: list[str]) -> list[str]:
    """The lines that are still open: a line is open until it has passed, been repaired or fallen back."""
    open_ = set(review_line_ids)
    return [ln.line_id for ln in script.lines if ln.line_id in open_ or ln.status in ("fallback", "needs_review", "draft")]


def readiness(
    script: ScriptIR,
    takes: list[VoiceTake] | None = None,
    qa: dict[str, QaReport] | None = None,
    cast_plan=None,
    outdated: list[str] | None = None,
    review_line_ids: list[str] | None = None,
    music_tracks: int | None = None,
) -> ReadinessReport:
    """Work out what is still open before the project renders."""
    issues: list[OpenIssue] = []

    waiting = _review_lines(script, review_line_ids or [])
    if waiting:
        issues.append(OpenIssue(kind="line", severity="block",
                                detail=f"{len(waiting)} lines are still waiting for review", line_ids=waiting))

    if cast_plan is not None:
        without = list(cast_plan.uncast)
        if without:
            issues.append(OpenIssue(kind="voice", severity="block",
                                    detail=f"{len(without)} characters have no voice", character_ids=without))

    qa = qa or {}
    failed = [lid for lid, r in qa.items() if not r.passed]
    if failed:
        issues.append(OpenIssue(kind="qa", severity="block",
                                detail=f"{len(failed)} takes failed the audio QA", line_ids=failed))

    outdated = list(outdated or [])
    if outdated:
        issues.append(OpenIssue(kind="outdated", severity="warn",
                                detail=f"{len(outdated)} takes no longer match their line", line_ids=outdated))

    if music_tracks is not None and not music_tracks:
        issues.append(OpenIssue(kind="music", severity="warn", detail="no music track is set"))

    return ReadinessReport(
        ready=not any(i.severity == "block" for i in issues),
        issues=issues,
        lines_awaiting_review=waiting,
        characters_without_a_voice=list(cast_plan.uncast) if cast_plan is not None else [],
        failed_qa_lines=failed,
        outdated_take_lines=outdated,
        music_tracks=music_tracks or 0,
    )
