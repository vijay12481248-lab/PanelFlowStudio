import json

import pytest

from engine.narration.artifacts import BibleCharacter, NARRATOR_ID, SeriesBible
from engine.narration.casting import (
    CastPlan, apply_recommendations, cast_for_script, load_cast, resolve_cast, save_cast, speakers_of,
)
from engine.narration.runtime.roles import VoiceProfile
from tests.unit.narration.test_write_speaker import _bible


CATALOG = [
    VoiceProfile(id="narrator", name="The Narrator", voice="am_michael", gender="male"),
    VoiceProfile(id="aria", name="Aria", voice="af_heart", gender="female"),
    VoiceProfile(id="bella", name="Bella", voice="af_bella", gender="female"),
    VoiceProfile(id="adam", name="Adam", voice="am_adam", gender="male"),
]


def _script(*speaker_ids):
    from engine.narration.artifacts import ScriptIR, ScriptLine
    return ScriptIR(project_id="p", lines=[
        ScriptLine(line_id=f"L{i + 1}", panel_id=f"p{i + 1}", text=f"the line number {i + 1} is said out loud",
                   facts_used=["action"], kind="narration", speaker_id=sid)
        for i, sid in enumerate(speaker_ids)
    ])


def test_the_narrator_reads_with_the_configured_voice():
    plan = resolve_cast("s", _bible(), [NARRATOR_ID], CATALOG, {})
    assert [(a.character_id, a.profile_id, a.source) for a in plan.assignments] == [(NARRATOR_ID, "narrator", "narrator")]


def test_an_owners_assignment_is_kept():
    """A voice the owner chose is never replaced by the assistant."""
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="he")])
    plan = resolve_cast("s", bible, ["c1"], CATALOG, {"c1": "aria"})
    assert [(a.character_id, a.profile_id, a.source) for a in plan.assignments] == [("c1", "aria", "assigned")]
    assert plan.recommendations == []


def test_a_character_without_an_assignment_gets_a_recommendation_not_an_assignment():
    """The assistant proposes; it does not decide on its own."""
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="she")])
    plan = resolve_cast("s", bible, ["c1"], CATALOG, {})
    assert plan.assignments == []
    assert [(r.character_id, r.profile_id, r.source) for r in plan.recommendations] == [("c1", "aria", "recommended")]


def test_the_recommendation_fits_the_characters_pronouns():
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="he")])
    plan = resolve_cast("s", bible, ["c1"], CATALOG, {})
    assert plan.recommendations[0].profile_id in {"adam", "narrator"}  # a male voice


def test_a_character_with_no_voice_at_all_is_flagged():
    """Nobody is given a voice that does not exist."""
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="he")])
    plan = resolve_cast("s", bible, ["c1"], CATALOG[:1], {})  # only the narrator exists
    assert plan.uncast == ["c1"]
    assert plan.recommendations == []


def test_two_characters_are_not_given_the_same_voice():
    bible = SeriesBible(series_key="s", characters=[
        BibleCharacter(id="c1", name="Kai", pronouns="she"),
        BibleCharacter(id="c2", name="Vex", pronouns="she"),
    ])
    plan = resolve_cast("s", bible, ["c1", "c2"], CATALOG, {})
    assert len({r.profile_id for r in plan.recommendations}) == 2


def test_accepted_recommendations_are_kept_for_the_next_chapter(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.narration.casting.settings.app_data_dir", tmp_path)
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="she")])
    plan = resolve_cast("s", bible, ["c1"], CATALOG)
    apply_recommendations(plan, "s", CATALOG)
    assert load_cast("s") == {"c1": "aria"}
    again = resolve_cast("s", bible, ["c1"], CATALOG)
    assert [(a.character_id, a.profile_id, a.source) for a in again.assignments] == [("c1", "aria", "assigned")]
    assert again.recommendations == []


def test_accepting_a_recommendation_never_overwrites_an_existing_assignment(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.narration.casting.settings.app_data_dir", tmp_path)
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="she")])
    save_cast("s", {"c1": "bella"})
    plan = resolve_cast("s", bible, ["c1"], CATALOG)  # the stored assignment is what the assistant sees
    assert plan.recommendations == []  # the owner already cast it, so there is nothing to propose
    apply_recommendations(plan, "s", CATALOG)
    assert load_cast("s") == {"c1": "bella"}


def test_the_cast_of_a_script_names_the_voice_of_each_speaker(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.narration.casting.settings.app_data_dir", tmp_path)
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="she")])
    save_cast("s", {"c1": "aria"})
    script = _script(NARRATOR_ID, "c1")
    assert speakers_of(script) == [NARRATOR_ID, "c1"]
    plan, voices = cast_for_script("s", bible, script, CATALOG)
    assert voices == {"c1": "af_heart"}  # the narrator's voice is the fallback, not in the map
    assert plan.assignment_of("c1").source == "assigned"


def test_a_character_with_no_cast_voice_falls_back_to_the_narrator(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.narration.casting.settings.app_data_dir", tmp_path)
    bible = SeriesBible(series_key="s", characters=[BibleCharacter(id="c1", name="Kai", pronouns="she")])
    script = _script(NARRATOR_ID, "c1")
    _, voices = cast_for_script("s", bible, script, CATALOG)
    assert "c1" not in voices  # the owner has not cast it, so the narrator reads it


def test_a_corrupt_casting_file_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.narration.casting.settings.app_data_dir", tmp_path)
    path = tmp_path / "series" / "s" / "casting.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert load_cast("s") == {}
