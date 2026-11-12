import asyncio
import re

import pytest

from engine.narration.artifacts import (
    Beat, BeatSheet, BibleCharacter, NARRATOR_ID, PanelFacts, Scene, SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.critique.rules import rule_checks
from engine.narration.steps.write import LineDraft, SceneLinesDraft, write_chapter
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader


def _facts(k, is_story=True, visible=("c1",), dialogue=()):
    return PanelFacts(
        panel_id=f"p{k}", order=k, is_story=is_story, shot="medium", action=f"act {k}",
        emotion="calm", importance=3, confidence=0.9, characters_visible=list(visible),
        dialogue=list(dialogue),
    )


def _sheet(*ranges, resolutions=None):
    scenes = [Scene(scene_id=f"s{i}", first_panel_id=a, last_panel_id=b, goal="g", conflict="c", turn=f"turn {i}",
                    beats=[Beat(beat_id=f"s{i}b0", panel_ids=[a, b], what_happens="w", function="setup", intensity=0.5)])
              for i, (a, b) in enumerate(ranges)]
    return BeatSheet(project_id="proj", scenes=scenes, hook="a dark hook", chapter_summary="sum",
                     character_resolutions=dict(resolutions or {}))


def _bible(*names):
    return SeriesBible(series_key="s", characters=[BibleCharacter(id=cid, name=nm) for cid, nm in names])


def _draft(prompt, skip=(), tag="x", facts=("action",), speaker=NARRATOR_ID):
    ks = [int(m) for m in re.findall(r"^P(\d+) \|", prompt, re.M) if int(m) not in skip]
    return SceneLinesDraft(lines=[LineDraft(panel=k, text=f"{tag} line for P{k} goes right here", facts_used=list(facts),
                                            kind="narration", speaker=speaker) for k in ks])


def _drafts(*specs):
    """One line per panel, each with its own facts and speaker: (facts, speaker) per panel."""
    def answer(prompt):
        if "exactly 3 candidates" in prompt:
            return _cands(prompt)
        ks = [int(m) for m in re.findall(r"^P(\d+) \|", prompt, re.M)]
        return SceneLinesDraft(lines=[
            LineDraft(panel=k, text=f"line for P{k} goes right here", facts_used=list(specs[min(k - 1, len(specs) - 1)][0]),
                      kind="narration", speaker=specs[min(k - 1, len(specs) - 1)][1]) for k in ks])
    return answer


def _cands(prompt):
    from engine.narration.steps.write import CandidatesDraft
    return CandidatesDraft(candidates=["one two three four five", "six seven eight nine ten", "a b c d e"])


def _answer(prompt):
    return _cands(prompt) if "exactly 3 candidates" in prompt else _draft(prompt)


def _run(tmp_path, facts, sheet, responses, bible=None):
    client = FakeModelClient({"writer": responses})
    role = RoleConfig(model="w", temperature=0.7, max_tokens=512, concurrency=1)
    sched = ModelScheduler({"writer": role}, RecordingUnloader())
    out = asyncio.run(write_chapter("proj", facts, sheet, bible or _bible(("c1", "Kai")),
                                     client, sched, ArtifactCache(tmp_path / "c")))
    return out, client


def test_a_quoted_line_is_read_by_its_character(tmp_path):
    """A character reads the line that quotes them; every other line stays the narrator's."""
    facts = [_facts(1, visible=("c1",)), _facts(2, visible=("c1",))]
    # P1 quotes nothing, P2 quotes Kai
    answer = _drafts((("action",), NARRATOR_ID), (("dialogue",), "c1"))
    client = FakeModelClient({"writer": [answer] * 4})
    role = RoleConfig(model="w", temperature=0.7, max_tokens=512, concurrency=1)
    sched = ModelScheduler({"writer": role}, RecordingUnloader())
    (script, _cands) = asyncio.run(write_chapter(
        "proj", facts, _sheet(("p1", "p2")), _bible(("c1", "Kai")), client, sched,
        ArtifactCache(tmp_path / "c")))
    assert [ln.speaker_id for ln in script.lines] == [NARRATOR_ID, "c1"]


def test_a_character_speaker_needs_a_dialogue_fact(tmp_path):
    """A line that quotes nobody is never handed to a character, whatever the writer proposed."""
    facts = [_facts(1, visible=("c1",))]
    client = FakeModelClient({"writer": [_drafts((("action",), "c1"))] * 3})
    role = RoleConfig(model="w", temperature=0.7, max_tokens=512, concurrency=1)
    sched = ModelScheduler({"writer": role}, RecordingUnloader())
    (script, _cands) = asyncio.run(write_chapter(
        "proj", facts, _sheet(("p1", "p1")), _bible(("c1", "Kai")), client, sched,
        ArtifactCache(tmp_path / "c")))
    assert [ln.speaker_id for ln in script.lines] == [NARRATOR_ID]


def test_an_unknown_speaker_falls_back_to_the_narrator(tmp_path):
    """A speaker the scene does not offer is ignored; the line keeps the narrator's voice."""
    facts = [_facts(1, visible=("c1",))]
    client = FakeModelClient({"writer": [_drafts((("dialogue",), "c9"))] * 3})
    role = RoleConfig(model="w", temperature=0.7, max_tokens=512, concurrency=1)
    sched = ModelScheduler({"writer": role}, RecordingUnloader())
    (script, _cands) = asyncio.run(write_chapter(
        "proj", facts, _sheet(("p1", "p1")), _bible(("c1", "Kai")), client, sched,
        ArtifactCache(tmp_path / "c")))
    assert [ln.speaker_id for ln in script.lines] == [NARRATOR_ID]


def test_the_prompt_offers_the_characters_present_as_speakers(tmp_path):
    """The speaker list names the characters of the scene, and never a raw unknown_<n> label."""
    facts = [_facts(1, visible=("c1", "unknown_1")), _facts(2, visible=("c1", "unknown_1"))]
    (_, _), client = _run(tmp_path, facts, _sheet(("p1", "p2")), [_answer] * 3)
    prompt = client.calls[0][1]
    assert "c1 - Kai" in prompt
    assert "narrator - the narrator voice" in prompt
    assert "unknown_1" not in prompt


def test_the_speaker_rule_blocks_a_character_who_is_not_in_the_scene():
    """The rule stops a line from being read by someone the panel does not show."""
    from engine.narration.artifacts import ScriptIR, ScriptLine

    facts = {"p1": _facts(1, visible=("c1",))}
    line = ScriptLine(line_id="L1", panel_id="p1", text="Kai says the door will not open for him today.",
                      facts_used=["dialogue"], kind="narration", speaker_id="c1")
    checks = rule_checks(ScriptIR(project_id="p", lines=[line]), facts, ["p1"], _bible(("c1", "Kai")))
    assert all(c.passed for c in checks["L1"] if c.rule != "speaker")

    away = line.model_copy(update={"speaker_id": "c2"})
    other = rule_checks(ScriptIR(project_id="p", lines=[away]), facts, ["p1"], _bible(("c1", "Kai"), ("c2", "Vex")))
    speaker = [c for c in other["L1"] if c.rule == "speaker"][0]
    assert speaker.passed is False and "not in this scene" in speaker.reason


def test_the_speaker_rule_blocks_a_line_that_quotes_nobody():
    from engine.narration.artifacts import ScriptIR, ScriptLine

    facts = {"p1": _facts(1, visible=("c1",))}
    script = ScriptIR(project_id="p", lines=[
        ScriptLine(line_id="L1", panel_id="p1", text="Kai walks slowly toward the heavy wooden door.",
                   facts_used=["action"], kind="narration", speaker_id="c1"),
    ])
    checks = rule_checks(script, facts, ["p1"], _bible(("c1", "Kai")))
    speaker = [c for c in checks["L1"] if c.rule == "speaker"][0]
    assert speaker.passed is False and "does not quote any dialogue" in speaker.reason
