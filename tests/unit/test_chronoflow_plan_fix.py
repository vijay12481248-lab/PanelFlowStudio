"""Auto-fix for an uploaded Video Plan: repairs what can be repaired safely, says what it did, leaves the rest as problems."""
import copy
import json
import re
from pathlib import Path

import pytest

from engine.chronoflow import plan_check as pc
from engine.chronoflow import plan_fix as pf

EXAMPLE = json.loads((Path(pc.__file__).parent / "plan_kit" / "example_plan.json").read_text(encoding="utf-8"))


def good():
    return copy.deepcopy(EXAMPLE)


def fixed(fn):
    p = good()
    fn(p)
    out, changes = pf.autofix(p)
    return out, changes, pc.check(out)


def test_a_valid_plan_is_left_exactly_as_it_is():
    out, changes = pf.autofix(good())
    assert out == EXAMPLE and changes == []


def test_autofix_never_edits_the_plan_it_is_given():
    p = good()
    p["takes"][0]["seconds"] = 9
    before = copy.deepcopy(p)
    pf.autofix(p)
    assert p == before


def test_autofix_is_idempotent():
    p = good()
    p["takes"][0]["narration"] = "After the rain has stopped, bright sunlight breaks through the thinning grey clouds above the wide green meadow today."
    once, _ = pf.autofix(p)
    twice, changes = pf.autofix(once)
    assert twice == once and changes == []


def test_ids_become_clean_slugs_and_every_reference_follows():
    def damage(p):
        p["cast"][0]["id"], p["places"][0]["id"], p["scenes"][0]["id"] = "Mira Keeper", "Rainy Meadow!", "Scene 1"
        for t in p["takes"]:
            t["cast"] = ["Mira Keeper" if c == "mira" else c for c in t["cast"]]
        p["scenes"][0]["place"] = "Rainy Meadow!"
        for t in p["takes"][:2]:
            t["scene"] = "Scene 1"
    out, changes, problems = fixed(damage)
    assert problems == [] and out["cast"][0]["id"] == "mira_keeper" and out["places"][0]["id"] == "rainy_meadow" and out["scenes"][0]["id"] == "scene_1"
    assert out["takes"][0]["cast"][0] == "mira_keeper" and out["scenes"][0]["place"] == "rainy_meadow" and any("id" in c.lower() for c in changes)


def test_a_take_longer_than_the_clip_is_trimmed_and_the_total_follows():
    out, changes, problems = fixed(lambda p: p["takes"][0].update(seconds=9))
    assert problems == [] and out["takes"][0]["seconds"] == 5 and out["production"]["total_seconds"] == 20
    assert any("5" in c and "9" in c for c in changes)


def test_total_length_follows_the_takes():
    out, _, problems = fixed(lambda p: p["production"].update(total_seconds=100))
    assert problems == [] and out["production"]["total_seconds"] == 20


def test_words_for_enums_are_understood():
    def damage(p):
        p["takes"][0]["framing"], p["takes"][1]["camera"], p["format"], p["genre"] = "Wide Shot", "slow zoom in", "landscape", "Explainer"
        p["production"]["narration"], p["production"]["join"] = "voice-over", "clip_tail"
    out, _, problems = fixed(damage)
    assert problems == [] and out["takes"][0]["framing"] == "wide" and out["takes"][1]["camera"] == "slow push-in" and out["format"] == "16:9"
    assert out["genre"] == "explainer" and out["production"]["narration"] == "narrator" and out["production"]["join"] == "matched_pictures"


def test_an_unknown_genre_becomes_custom():
    out, changes, problems = fixed(lambda p: p.update(genre="western"))
    assert problems == [] and out["genre"] == "custom" and any("genre" in c for c in changes)


def test_start_picture_on_a_previous_end_take_is_dropped_and_a_scene_opener_is_a_new_picture():
    out, _, problems = fixed(lambda p: p["takes"][1].update(start_picture="Mira stands somewhere in the meadow doing nothing much at all today."))
    assert problems == [] and "start_picture" not in out["takes"][1]
    out2, _, problems2 = fixed(lambda p: p["takes"][2].update(start_from="previous_end"))
    assert problems2 == [] and out2["takes"][2]["start_from"] == "new_picture"  # it already has its own start picture, so the opener is a new picture


def test_a_second_take_without_a_start_picture_continues_from_the_first():
    def damage(p):
        p["takes"][1]["start_from"] = "new_picture"
    out, _, problems = fixed(damage)
    assert problems == [] and out["takes"][1]["start_from"] == "previous_end"


def test_a_look_written_as_a_sentence_becomes_tags():
    out, changes, problems = fixed(lambda p: p["cast"][0].update(look="a young woman with shoulder-length copper-red hair and a green scarf and a brown jacket"))
    assert problems == [] and out["cast"][0]["look"].count(",") >= 2 and "copper-red hair" in out["cast"][0]["look"] and any("look" in c for c in changes)


def test_narration_that_is_too_long_is_cut_at_a_sentence_or_word_limit():
    long = "After rain, sunlight breaks through the thinning clouds above the meadow. Then the whole sky turns slowly bright and warm over every hill nearby."
    out, changes, problems = fixed(lambda p: p["takes"][0].update(narration=long))
    assert problems == [] and out["takes"][0]["narration"] == "After rain, sunlight breaks through the thinning clouds above the meadow." and any("narration" in c for c in changes)
    out2, _, problems2 = fixed(lambda p: p["takes"][0].update(narration="After the rain has stopped falling the bright sunlight slowly breaks through the thinning grey clouds above the wide green meadow today."))
    assert problems2 == [] and len(out2["takes"][0]["narration"].split()) <= 11


def test_a_traveller_without_a_direction_gets_one():
    out, changes, problems = fixed(lambda p: p["takes"][1].update(motion="Mira walks across the meadow while Pip follows slowly behind her."))
    assert problems == [] and re.search(r"walks to the (right|left) across", out["takes"][1]["motion"]) and any("direction" in c for c in changes)


def test_the_noun_head_becomes_face():
    out, _, problems = fixed(lambda p: p["takes"][0].update(motion="Mira looks up at the clouds while Pip tilts its head and watches the light."))
    assert problems == [] and "tilts its face" in out["takes"][0]["motion"]


def test_a_clause_naming_two_characters_is_split_with_a_semicolon():
    text = "Wide view of the meadow, Mira stands on the left side of the frame with Pip sitting beside her under grey clouds."
    out, changes, problems = fixed(lambda p: p["takes"][0].update(start_picture=text))
    assert problems == [] and "; Pip" in out["takes"][0]["start_picture"] and any("own clause" in c for c in changes)


def test_a_negated_clause_is_removed_when_enough_text_remains():
    text = "Wide view of a green meadow after rain; Mira stands on the left side of the frame; Pip sits beside her; no smoke and no dust in the air; pale sunlight breaks through on the right."
    out, changes, problems = fixed(lambda p: p["takes"][0].update(start_picture=text))
    assert problems == [] and "no smoke" not in out["takes"][0]["start_picture"] and "pale sunlight breaks through" in out["takes"][0]["start_picture"]
    assert any("must not appear" in c for c in changes)


def test_missing_optional_fields_get_plain_defaults_and_are_reported():
    def damage(p):
        for t in p["takes"]:
            t.pop("camera"), t.pop("atmosphere")
        p.pop("rules"), p["production"].pop("music"), p["production"].pop("join")
        p["cast"][0].pop("personality"), p["cast"][0].pop("gender")
        p["scenes"][0].pop("music"), p["scenes"][0].pop("mood")
    out, changes, problems = fixed(damage)
    assert problems == [] and out["production"]["join"] == "matched_pictures" and out["cast"][0]["gender"] == "neutral" and out["rules"] == []
    assert changes  # defaults are never silent


def test_an_empty_cast_is_read_from_the_pictures():
    out, changes, problems = fixed(lambda p: p["takes"][0].update(cast=[]))
    assert problems == [] and out["takes"][0]["cast"] == ["mira", "pip"] and any("cast" in c for c in changes)


def test_what_cannot_be_fixed_stays_a_problem():
    def damage(p):
        p["takes"][0]["narration"] = "Too short."
        p["takes"][1].pop("end_picture")
    _, _, problems = fixed(damage)
    joined = " ".join(problems)
    assert "narration has 2 words" in joined and "end_picture" in joined


def test_many_problems_at_once_all_get_fixed():
    def damage(p):
        p["production"].update(total_seconds=99, join="clip_tail", narration="yes")
        p["format"], p["genre"] = "Landscape", "Explainer "
        p["cast"][0]["look"] = "a young woman with copper hair and a green scarf"
        p["takes"][0].update(seconds=8, framing="Wide Shot", motion="Mira looks up while Pip tilts its head to see the light.")
        p["takes"][1].update(start_picture="Mira stands in the meadow with Pip beside her for a long moment today.", motion="Mira runs across the meadow while Pip follows her closely.")
        p["takes"][2]["narration"] = "A prism bends sunlight and splits it into all its colors. Then it makes a rainbow on the grass for everyone to see clearly."
        p["takes"][3]["start_from"] = "clip_tail"
    out, changes, problems = fixed(damage)
    assert problems == [], problems
    assert len(changes) >= 8


def test_the_fixed_plan_imports():
    from engine.chronoflow import plan_import as pi

    p = good()
    p["production"].update(total_seconds=99)
    p["takes"][1]["motion"] = "Mira walks across the meadow while Pip follows slowly behind her."
    out, _ = pf.autofix(p)
    assert len(pi.plan_to_cards(out)["screenplay"]["scenes"]) == 4


# ---- the reader also forgives comments and Python-style dictionaries
@pytest.mark.parametrize("wrap", [
    lambda s: s.replace('"panelflow_plan": 2,', '"panelflow_plan": 2, // the format version'),
    lambda s: "// plan for Mira\n" + s,
    lambda s: s.replace(": true", ": True").replace('"', "'"),
])
def test_reader_forgives_comments_and_single_quotes(wrap):
    body = json.dumps(EXAMPLE, indent=2)
    plan = pc.read_plan(wrap(body))
    assert plan["title"] == "Why Do Rainbows Appear?" and len(plan["takes"]) == 4


# ---- `shows` is taken from the plan's own pictures when the narration does not talk about it
def test_a_missing_or_unrelated_shows_is_taken_from_the_part_of_the_pictures_the_narration_talks_about():
    out, changes, problems = fixed(lambda p: p["takes"][0].update(shows=""))
    assert problems == [] and 4 <= len(out["takes"][0]["shows"].split()) <= 25 and any("shows" in c for c in changes)
    assert out["takes"][0]["shows"] in EXAMPLE["takes"][0]["start_picture"] + " " + EXAMPLE["takes"][0]["end_picture"]  # nothing invented: a part of the plan's own pictures
    out2, _, problems2 = fixed(lambda p: p["takes"][0].update(shows="a purple elephant dancing happily in deep snow"))
    assert problems2 == [] and "elephant" not in out2["takes"][0]["shows"]


def test_shows_stays_a_problem_when_the_narration_shares_nothing_with_the_pictures():
    _, _, problems = fixed(lambda p: p["takes"][2].update(narration="Mysterious things happen every single night somewhere far away.", shows=""))
    assert any("shows" in m for m in problems)


def test_a_character_named_in_the_pictures_joins_the_take_cast():
    out, changes, problems = fixed(lambda p: p["takes"][2].update(cast=["mira"]))
    assert problems == [] and out["takes"][2]["cast"] == ["mira", "pip"] and any("pip" in c.lower() and "cast" in c for c in changes)


def test_a_part_where_someone_speaks_on_screen_is_removed():
    motion = "Mira waves to the right as the light brightens; Pip says hello loudly; the clouds slowly part overhead."
    out, changes, problems = fixed(lambda p: p["takes"][0].update(motion=motion))
    assert problems == [] and "says" not in out["takes"][0]["motion"] and "clouds slowly part" in out["takes"][0]["motion"] and any("speaks" in c for c in changes)
