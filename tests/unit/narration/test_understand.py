import asyncio

import pytest

from engine.narration.runtime.client import StepModelError

from engine.narration.artifacts import (
    Beat, BeatSheet, BibleCharacter, OcrDialogue, PanelFacts, Scene, SeriesBible,
)
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.understand import (
    MergeDraft, NeedsReview, NewCharacter, NewThread, WindowBeatDraft, WindowDraft, WindowSceneDraft,
    check_beat_sheet, normalize_beats, stitch_windows, understand_chapter, windows,
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
    base = dict(hook="h", chapter_summary="sum", character_resolutions={})
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
    assert [b.panels for b in out[0].beats] == [list(range(20, 26)), [26, 27]]
    assert [b.panels for b in out[1].beats] == [list(range(28, 41))]


_INTERLEAVED = [[21, 23], [22, 24], [25, 26], [27, 28], [29, 30]]


def test_normalize_beats_makes_interleaved_beats_contiguous():
    s = _scene(21, 30, _INTERLEAVED)
    s.beats[1].what_happens = "second"
    out = normalize_beats(s)
    assert [b.panels for b in out.beats] == [[21], [22, 23, 24], [25, 26], [27, 28], [29, 30]]
    assert out.beats[1].what_happens == "second"


def test_normalize_beats_clamps_beat_starting_before_scene():
    out = normalize_beats(_scene(21, 25, [[24, 25], [19, 20, 23]]))
    assert [b.panels for b in out.beats] == [[21, 22, 23], [24, 25]]


def test_interleaved_window_draft_needs_no_reask(tmp_path):
    facts = [_facts(k) for k in range(1, 31)]
    draft = WindowDraft(scenes=[_scene(1, 20), _scene(21, 30, _INTERLEAVED)])
    sheet, client = _run(tmp_path, facts, [draft, _merge()])
    assert len(client.calls) == 2  # one window call + merge
    assert sheet.scenes[1].beats[0].panel_ids == ["p21"]


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
    facts = [_facts(1, characters_visible=["unknown_1", "unknown_2"], names_mentioned=["The Masked Man"],
                    unknown_cues={"unknown_1": "masked man", "unknown_2": "old monk"})]
    merge = _merge(character_resolutions={"unknown_1": "c1", "unknown_2": "not-a-bible-id", "unknown_9": "c1"})
    sheet, client = _run(tmp_path, facts, [WindowDraft(scenes=[_scene(1, 1)]), merge])
    assert sheet.character_resolutions == {"unknown_1": "c1"}
    assert "unknown_1: masked man" in client.calls[1][1]


def _scenes_for(spans):
    """One scene per (first, last) 1-based span, a single beat each."""
    return WindowDraft(scenes=[_scene(a, b, [list(range(a, b + 1))]) for a, b in spans])


def test_three_window_stitch_covers_every_panel_once(tmp_path):
    facts = [_facts(k) for k in range(1, 71)]
    drafts = [_scenes_for([(1, 15), (16, 30)]), _scenes_for([(26, 40), (41, 55)]), _scenes_for([(51, 70)])]
    sheet, client = _run(tmp_path, facts, [*drafts, _merge()])
    assert len(client.calls) == 4
    spans = [(int(s.first_panel_id[1:]), int(s.last_panel_id[1:])) for s in sheet.scenes]
    assert spans == [(1, 15), (16, 27), (28, 40), (41, 52), (53, 70)]
    assert all(b == a2 - 1 for (_, b), (a2, _) in zip(spans, spans[1:]))  # no gap, no overlap
    covered = [p for s in sheet.scenes for b in s.beats for p in b.panel_ids]
    assert covered == [f"p{k}" for k in range(1, 71)]


def test_multi_window_reask_redoes_only_the_broken_window(tmp_path):
    facts = [_facts(k) for k in range(1, 71)]
    bad3 = _scenes_for([(51, 60)])  # panels 61-70 are in no scene
    good3 = _scenes_for([(51, 70)])
    drafts = [_scenes_for([(1, 30)]), _scenes_for([(26, 55)]), bad3, good3]
    sheet, client = _run(tmp_path, facts, [*drafts, _merge()])
    assert len(client.calls) == 5  # 3 windows + one re-ask + merge
    assert "Fix these problems" in client.calls[3][1] and "P61" in client.calls[3][1]
    assert "P51 |" in client.calls[3][1] and "P1 |" not in client.calls[3][1]
    assert sheet.scenes[-1].last_panel_id == "p70"


def test_reask_is_cached_and_never_overwrites_the_first_answer(tmp_path):
    facts = [_facts(1), _facts(2), _facts(3)]
    bad, good = WindowDraft(scenes=[_scene(1, 2)]), WindowDraft(scenes=[_scene(1, 2), _scene(3, 3)])
    first, c1 = _run(tmp_path, facts, [bad, good, _merge()])
    assert len(list((tmp_path / "cache" / "understand_window").glob("*.json"))) == 2
    second, c2 = _run(tmp_path, facts, [])  # an empty queue raises if any model call is made
    assert c2.calls == [] and second == first


def test_merge_draft_becomes_typed_bible_proposals(tmp_path):
    facts = [_facts(1, characters_visible=["unknown_1", "unknown_2"], names_mentioned=["The Masked Man"],
                    unknown_cues={"unknown_1": "masked man", "unknown_2": "man in mask"})]
    merge = _merge(
        new_characters=[
            NewCharacter(name="  The   Masked Man ", description="black mask",
                         unknown_ids=["unknown_1", "unknown_2", "unknown_9"]),
            NewCharacter(name="shangguan  yulin", description="dup of the bible", unknown_ids=[]),
            NewCharacter(name="the masked man", description="dup within the draft"),
            NewCharacter(name="   "),
        ],
        new_threads=[NewThread(text="Who is the masked man?"), NewThread(text=" "), NewThread(text="Who is the masked man?")],
        plot_update="Yulin met a masked man.",
        character_resolutions={"unknown_1": "c_1"},  # a proposed id is never a valid resolution
    )
    sheet, _ = _run(tmp_path, facts, [WindowDraft(scenes=[_scene(1, 1)]), merge])
    assert sheet.character_resolutions == {}
    assert [(p.kind, p.payload) for p in sheet.bible_proposals] == [
        ("add_character", {"id": "c_1", "name": "The Masked Man", "appearance_cues": ["black mask"],
                           "unknown_ids": ["unknown_1", "unknown_2"]}),
        ("add_thread", {"text": "Who is the masked man?"}),
        ("update_plot", {"plot_so_far": "Yulin met a masked man."}),
    ]


def test_oversized_window_prompt_fails_loudly_without_calling_model(tmp_path):
    client = FakeModelClient({"planner": [WindowDraft(scenes=[_scene(1, 1)]), _merge()]},
                             params={"num_ctx": 300, "max_tokens": 200})
    with pytest.raises(StepModelError, match="planner"):
        _run(tmp_path, [_facts(1)], [], client=client)
    assert client.calls == []

def test_duplicate_new_character_merges_unknown_ids():
    from engine.narration.artifacts import SeriesBible
    from engine.narration.steps.understand import MergeDraft, _proposals
    merge = MergeDraft.model_validate({
        "hook": "h", "chapter_summary": "s", "character_resolutions": {},
        "new_characters": [
            {"name": "Masked Man", "description": "", "unknown_ids": ["unknown_1"]},
            {"name": "masked man ", "description": "", "unknown_ids": ["unknown_2"]},
        ],
    })
    out, _ = _proposals(merge, SeriesBible(series_key="s"), {"unknown_1": "a", "unknown_2": "b"},
                        [_facts(1, names_mentioned=["Masked Man"])])
    assert len(out) == 1
    assert out[0].payload["unknown_ids"] == ["unknown_1", "unknown_2"]


def test_new_character_names_must_be_read_off_the_page():
    from engine.narration.steps.understand import MergeDraft, _proposals
    merge = MergeDraft.model_validate({
        "hook": "h", "chapter_summary": "s", "character_resolutions": {},
        "new_characters": [
            {"name": "Blue-skinned Invulnerable Opponent", "unknown_ids": ["unknown_1"]},
            {"name": "yulin", "unknown_ids": ["unknown_2"]},
        ],
    })
    out, _ = _proposals(merge, SeriesBible(series_key="s"), {"unknown_1": "a", "unknown_2": "b"},
                        [_facts(1, names_mentioned=["Yulin"], action="Blue man holds a map")])
    assert [p.payload["name"] for p in out] == ["yulin"]


def test_merge_prompt_lists_names_on_the_unknowns_panels(tmp_path):
    facts = [_facts(1, characters_visible=["unknown_1"], unknown_cues={"unknown_1": "bald man"},
                    names_mentioned=["Yulin", "Feixiong"]), _facts(2, characters_visible=["unknown_1"])]
    _, client = _run(tmp_path, facts, [WindowDraft(scenes=[_scene(1, 2)]), _merge()])
    assert "unknown_1: bald man | panels P1, P2 | names on those panels: Yulin, Feixiong" in client.calls[-1][1]
