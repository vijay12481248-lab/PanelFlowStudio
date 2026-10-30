import asyncio

import pytest

from engine.narration.artifacts import (
    Beat, BeatSheet, BibleCharacter, OcrDialogue, PanelFacts, Scene, SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.understand import (
    MergeDraft, NeedsReview, WindowBeatDraft, WindowDraft, WindowSceneDraft,
    check_beat_sheet, stitch_windows, understand_chapter, windows,
)
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader


def _facts(k, is_story=True, **kw):
    base = dict(panel_id=f"p{k}", order=k, is_story=is_story, shot="medium", action=f"act {k}",
                emotion="calm", importance=3, confidence=0.9)
    base.update(kw)
    return PanelFacts(**base)


def _bible():
    return SeriesBible(series_key="s", plot_so_far="Yulin fled the sect.", characters=[
        BibleCharacter(id="c1", name="Shangguan Yulin", appearance_cues=["red robe"])])


def _scene(first, last, beats=None):
    beats = beats or [[first, last]]
    return WindowSceneDraft(first=first, last=last, goal="g", conflict="c", turn="t", beats=[
        WindowBeatDraft(panels=b, what_happens="w", function="setup", intensity=0.5) for b in beats])


def _merge(**kw):
    base = dict(hook="h", chapter_summary="sum", character_resolutions={}, bible_proposals=[])
    base.update(kw)
    return MergeDraft(**base)


def _run(tmp_path, facts, planner, client=None):
    client = client or FakeModelClient({"planner": list(planner)})
    role = RoleConfig(model="m", temperature=0.2, max_tokens=512, concurrency=1)
    sched = ModelScheduler({"planner": role}, RecordingUnloader())
    sheet = asyncio.run(understand_chapter("proj", facts, _bible(), client, sched,
                                           ArtifactCache(tmp_path / "cache")))
    return sheet, client


def test_windows():
    assert windows(70) == [(0, 30), (25, 55), (50, 70)]
    assert windows(12) == [(0, 12)]
    assert windows(0) == []


def test_stitch_cuts_overlap_at_midpoint():
    d0 = WindowDraft(scenes=[_scene(20, 30, [[20, 25], [26, 30]])])
    d1 = WindowDraft(scenes=[_scene(26, 40, [[26, 27], [28, 40]])])
    out = stitch_windows([(0, 30), (25, 55)], [d0, d1])
    assert [(s.first, s.last) for s in out] == [(20, 27), (28, 40)]
    assert [b.panels for b in out[0].beats] == [[20, 25], [26]]
    assert [b.panels for b in out[1].beats] == [[28, 40]]


def test_check_beat_sheet_reports_gap_and_double_cover():
    def scene(sid, a, b):
        return Scene(scene_id=sid, first_panel_id=a, last_panel_id=b, goal="g", conflict="c", turn="t",
                     beats=[Beat(beat_id=f"{sid}b0", panel_ids=[a], what_happens="w",
                                 function="setup", intensity=0.5)])
    sheet = BeatSheet(project_id="x", hook="h", chapter_summary="s",
                      scenes=[scene("s0", "p1", "p2"), scene("s1", "p2", "p3")])
    errors = check_beat_sheet(sheet, ["p1", "p2", "p3", "p4"], _bible())
    assert any("p2" in e and "2 scenes" in e for e in errors)
    assert any("p4" in e and "no scene" in e for e in errors)


def test_non_story_panels_are_excluded_from_scenes(tmp_path):
    facts = [_facts(1), _facts(2, is_story=False), _facts(3, dialogue=[OcrDialogue(region_id="r", text="Hi")])]
    sheet, client = _run(tmp_path, facts, [WindowDraft(scenes=[_scene(1, 2)]), _merge()])
    prompt = client.calls[0][1]
    assert "P1 |" in prompt and "P2 |" in prompt and "P3 |" not in prompt
    assert "act 3" in prompt and "Hi" in prompt and "act 2" not in prompt
    assert (sheet.scenes[0].first_panel_id, sheet.scenes[0].last_panel_id) == ("p1", "p3")
    assert sheet.scenes[0].beats[0].panel_ids == ["p1", "p3"]


def test_zero_story_panels_needs_review(tmp_path):
    with pytest.raises(NeedsReview) as exc:
        _run(tmp_path, [_facts(1, is_story=False)], [])
    assert exc.value.reasons == ["no story panels"]


def test_invalid_window_is_reasked_once_then_needs_review(tmp_path):
    bad = WindowDraft(scenes=[_scene(1, 2)])
    client = FakeModelClient({"planner": [bad, bad, _merge()]})
    with pytest.raises(NeedsReview) as exc:
        _run(tmp_path, [_facts(1), _facts(2), _facts(3)], [], client=client)
    assert any("p3" in r for r in exc.value.reasons)
    assert len(client.calls) == 2
    assert "Fix these problems" in client.calls[1][1] and "P3" in client.calls[1][1]
    assert "Fix these problems" not in client.calls[0][1]


def test_invalid_window_fixed_on_reask_returns_sheet(tmp_path):
    bad, good = WindowDraft(scenes=[_scene(1, 2)]), WindowDraft(scenes=[_scene(1, 2), _scene(3, 3)])
    sheet, client = _run(tmp_path, [_facts(1), _facts(2), _facts(3)], [bad, good, _merge()])
    assert len(client.calls) == 3
    assert [(s.first_panel_id, s.last_panel_id) for s in sheet.scenes] == [("p1", "p2"), ("p3", "p3")]
    assert [s.scene_id for s in sheet.scenes] == ["s0", "s1"]
    assert sheet.scenes[1].beats[0].beat_id == "s1b0"
    assert sheet.hook == "h"


def test_merge_resolutions_only_accept_bible_ids(tmp_path):
    facts = [_facts(1, characters_visible=["unknown_1", "unknown_2"],
                    unknown_cues={"unknown_1": "masked man", "unknown_2": "old monk"})]
    merge = _merge(character_resolutions={"unknown_1": "c1", "unknown_2": "not-a-bible-id", "unknown_9": "c1"})
    sheet, client = _run(tmp_path, facts, [WindowDraft(scenes=[_scene(1, 1)]), merge])
    assert sheet.character_resolutions == {"unknown_1": "c1"}
    assert "unknown_1: masked man" in client.calls[1][1]
