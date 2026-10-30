import asyncio

import pytest

from engine.narration.artifacts import BibleCharacter, SeriesBible
from engine.narration.cache import ArtifactCache
from engine.narration.runtime.client import StepModelError
from engine.narration.runtime.roles import RoleConfig
from engine.narration.runtime.scheduler import ModelScheduler
from engine.narration.steps.perceive import PanelFactsDraft, SpeakerGuess, perceive_chapter
from tests.unit.narration.fakes import FakeModelClient, RecordingUnloader, make_chapter_inputs


def _draft(**kw):
    base = dict(is_story=True, shot="medium", characters_visible=[], action="A man stands.",
                emotion="tense", speakers=[], sfx=[], setting="hall", importance=3, confidence=0.9)
    base.update(kw)
    return PanelFactsDraft(**base)


def _sched(concurrency=3):
    role = RoleConfig(model="m", temperature=0.1, max_tokens=512, concurrency=concurrency)
    return ModelScheduler({"vision": role}, RecordingUnloader())


def _bible():
    return SeriesBible(series_key="test-series", characters=[
        BibleCharacter(id="c1", name="Shangguan Yulin", aliases=["Yulin"], appearance_cues=["red robe"])])


def _run(tmp_path, drafts, ocr, concurrency=3, client=None, cache=None):
    inputs = make_chapter_inputs(tmp_path, len(drafts), ocr)
    client = client or FakeModelClient({"vision": list(drafts)})
    cache = cache or ArtifactCache(tmp_path / "cache")
    facts = asyncio.run(perceive_chapter(inputs, _bible(), client, _sched(concurrency), cache))
    return facts, client


def test_dialogue_text_is_copied_from_ocr_verbatim(tmp_path):
    d = _draft(speakers=[SpeakerGuess(region_id="p1-r1", speaker="Yulin")])
    facts, _ = _run(tmp_path, [d], {1: ["You dare?!"]})
    assert facts[0].dialogue[0].text == "You dare?!"
    assert facts[0].dialogue[0].speaker_id == "c1"
    assert facts[0].dialogue[0].speaker_confidence is None  # the draft gave none


def test_speakers_for_unknown_regions_are_ignored(tmp_path):
    d = _draft(speakers=[SpeakerGuess(region_id="r-not-in-panel", speaker="Yulin")])
    facts, _ = _run(tmp_path, [d], {1: ["a", "b"]})
    assert len(facts[0].dialogue) == 2
    assert all(x.speaker_id is None and x.speaker_confidence is None for x in facts[0].dialogue)


def test_bible_names_map_to_ids_and_others_become_stable_unknowns(tmp_path):
    d1 = _draft(characters_visible=["yulin", "masked man"])
    d2 = _draft(characters_visible=["masked man"])
    facts, _ = _run(tmp_path, [d1, d2], {})
    assert facts[0].characters_visible == ["c1", "unknown_1"]
    assert facts[1].characters_visible == ["unknown_1"]
    assert facts[0].unknown_cues == {"unknown_1": "masked man"}


def test_bible_ids_echoed_by_model_map_to_known_character(tmp_path):
    d = _draft(characters_visible=["c1"], speakers=[SpeakerGuess(region_id="p1-r1", speaker="C1")])
    facts, _ = _run(tmp_path, [d], {1: ["hi"]})
    assert facts[0].characters_visible == ["c1"]
    assert facts[0].dialogue[0].speaker_id == "c1"
    assert facts[0].unknown_cues == {}


def test_low_confidence_marks_needs_review(tmp_path):
    facts, _ = _run(tmp_path, [_draft(confidence=0.4), _draft(confidence=0.5)], {})
    assert facts[0].needs_review is True
    assert facts[1].needs_review is False


def test_long_action_is_truncated_to_20_words(tmp_path):
    facts, _ = _run(tmp_path, [_draft(action=" ".join(f"w{i}" for i in range(30)))], {})
    assert len(facts[0].action.split()) == 20


def test_previous_chunk_context_is_in_prompt(tmp_path):
    _, client = _run(tmp_path, [_draft(action="Yulin bows."), _draft()], {}, concurrency=1)
    assert "Yulin bows." in client.calls[1][1]
    assert "Yulin bows." not in client.calls[0][1]


def test_second_run_uses_cache_and_calls_no_model(tmp_path):
    cache = ArtifactCache(tmp_path / "cache")
    first, client = _run(tmp_path, [_draft(), _draft()], {1: ["hi"]}, cache=cache)
    n = len(client.calls)
    inputs = make_chapter_inputs(tmp_path, 2, {1: ["hi"]})
    second = asyncio.run(perceive_chapter(inputs, _bible(), client, _sched(), cache))
    assert len(client.calls) == n
    assert second == first


def test_speaker_confidence_comes_from_the_draft():
    from pydantic import ValidationError

    assert SpeakerGuess(region_id="r", speaker="s", confidence=0.7).confidence == 0.7
    with pytest.raises(ValidationError):
        SpeakerGuess(region_id="r", speaker="s", confidence=1.5)


def test_speaker_attribution_forces_story_even_if_model_said_no(tmp_path):
    d = _draft(is_story=False, speakers=[SpeakerGuess(region_id="p1-r1", speaker="Yulin", confidence=0.9)])
    facts, _ = _run(tmp_path, [d], {1: ["You dare?!"]})
    assert facts[0].is_story is True and facts[0].dialogue[0].speaker_confidence == 0.9


def test_ocr_text_or_visible_characters_alone_do_not_force_story(tmp_path):
    d = _draft(is_story=False, characters_visible=["Yulin"])
    facts, _ = _run(tmp_path, [d], {1: ["You dare?!"]})
    assert facts[0].is_story is False


def test_credits_text_stays_non_story_even_with_a_speaker(tmp_path):
    d = _draft(is_story=False, speakers=[SpeakerGuess(region_id="p1-r1", speaker="Yulin")])
    facts, _ = _run(tmp_path, [d], {1: ["Join our Discord for faster updates"]})
    assert facts[0].is_story is False


def test_blank_names_are_skipped_and_repeats_deduped(tmp_path):
    d = _draft(characters_visible=["  ", "masked man", "Masked Man", "Yulin", "c1", ""],
               speakers=[SpeakerGuess(region_id="p1-r1", speaker=" ")])
    facts, _ = _run(tmp_path, [d], {1: ["hi"]})
    assert facts[0].characters_visible == ["unknown_1", "c1"]
    assert facts[0].unknown_cues == {"unknown_1": "masked man"}
    assert facts[0].dialogue[0].speaker_id is None


def test_ocr_sfx_regions_join_panel_sfx(tmp_path):
    inputs = make_chapter_inputs(tmp_path, 1, {})
    inputs.panels[0].sfx.extend(["BOOM", "crash"])
    client = FakeModelClient({"vision": [_draft(sfx=["crash", "whoosh"])]})
    facts = asyncio.run(perceive_chapter(inputs, _bible(), client, _sched(), ArtifactCache(tmp_path / "cache")))
    assert facts[0].sfx == ["crash", "whoosh", "BOOM"]


def test_prompt_label_is_earlier_panel(tmp_path):
    _, client = _run(tmp_path, [_draft()], {})
    assert "Earlier panel:" in client.calls[0][1] and "Previous panel" not in client.calls[0][1]


def test_oversized_vision_prompt_fails_loudly_without_calling_model(tmp_path):
    client = FakeModelClient({"vision": [_draft()]}, params={"num_ctx": 1000, "max_tokens": 500})
    with pytest.raises(StepModelError, match="vision") as e:
        _run(tmp_path, [_draft()], {}, client=client)
    assert "prompt" in str(e.value) and client.calls == []