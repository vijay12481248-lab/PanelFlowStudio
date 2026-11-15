"""Plan -> OriginalStory -> storyboard cards, and the picture job that runs the existing storyboard.draw."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from engine.chronoflow import plan_check as pc
from engine.chronoflow import plan_import as pi
from engine.original import director, film  # noqa: F401  (director registers the explainer genre)
from engine.original.genres import GENRES

EXAMPLE = json.loads((Path(pc.__file__).parent / "plan_kit" / "example_plan.json").read_text(encoding="utf-8"))


def good():
    return copy.deepcopy(EXAMPLE)


def test_plan_becomes_a_real_original_story():
    s = pi.plan_to_story(good())
    assert [p.id for p in s.panels] == ["t01", "t02", "t03", "t04"] and [x.id for x in s.scenes] == ["s1", "s2"]
    assert [c.id for c in s.bible.characters] == ["mira", "pip"] and s.bible.premise.title == "Why Do Rainbows Appear?"
    t1, t2 = s.panels[0], s.panels[1]
    assert t2.action == t1.end_state  # previous_end: the take starts on the picture the last one ended on
    assert t1.location_id == "meadow" and s.panels[2].location_id == "hilltop"  # a take's place is its scene's place
    assert t1.dialogue[0].speaker_id == "narrator" and t1.dialogue[0].text.startswith("After rain")
    assert t1.key_visuals == [EXAMPLE["takes"][0]["shows"]] and t1.atmosphere == EXAMPLE["takes"][0]["atmosphere"]
    assert t1.seconds == 5.0 and t1.shot == "wide" and s.panels[3].camera == "slow push-in"
    assert t1.shots[0]["characters"] == ["mira", "pip"] and EXAMPLE["takes"][0]["motion"] in t1.shots[0]["action"]


def test_beats_become_the_shots_inside_a_take():
    p = good()
    p["production"].update(clip_seconds=10, total_seconds=40)
    p["takes"][0].update(seconds=10, beats=[{"at": 0, "action": "Mira looks up at the grey clouds above the meadow"}, {"at": 5, "action": "Mira points at the bright sunlight breaking through"}])
    shots = pi.plan_to_story(p).panels[0].shots
    assert [s["at"] for s in shots] == [0, 5] and "points at the bright sunlight" in shots[1]["action"]


def test_custom_style_reaches_the_picture_prompt_through_a_derived_genre():
    p = good()
    p["style"] = "watercolour storybook, soft edges"
    story = pi.plan_to_story(p)
    key = story.bible.premise.genre
    assert key != "explainer" and key in GENRES
    assert GENRES[key].art_style.startswith(GENRES["explainer"].art_style) and GENRES[key].art_style.endswith("watercolour storybook, soft edges")
    p["genre"], p["style"] = "custom", "chalk drawing on a blackboard"
    assert GENRES[pi.plan_to_story(p).bible.premise.genre].art_style == "chalk drawing on a blackboard"
    assert pi.plan_to_story(good()).bible.premise.genre == "explainer"  # no style: the genre's own look


def test_slug_is_stable_ascii_and_changes_with_the_plan():
    a, b = good(), good()
    assert pi.plan_slug(a) == pi.plan_slug(b) and pi.plan_slug(a).isascii() and " " not in pi.plan_slug(a)
    b["takes"][0]["motion"] = "Mira waves to the right while Pip watches her from the grass."
    assert pi.plan_slug(a) != pi.plan_slug(b)


def test_cards_carry_the_checked_clip_prompt_and_the_picture_prompts():
    plan = pi.plan_to_cards(good())
    cards = plan["screenplay"]["scenes"]
    assert len(cards) == 4 and plan["screenplay"]["title"] == "Why Do Rainbows Appear?"
    c1, c2 = cards[0], cards[1]
    assert c1["start_mode"] == "first_last" and c1["duration"] == 5.0 and (c1["width"], c1["height"], c1["lora_choice"]) == (1344, 768, "4step")
    assert "integrated_multimodal_description" in c1["prompt"] and "5.17-second mark" in c1["prompt"]  # storyboard.clip_prompt: the official FL2VA text, sent as written
    assert c1["first_prompt"] and c1["last_prompt"] and c1["first_frame"] == c1["last_frame"] == ""
    assert c2["first_prompt"] == "" and c2["chained_from_previous"] is True and c1["chained_from_previous"] is False  # its first picture is the previous last picture
    assert [c["plan_scene"] for c in cards] == ["s1", "s1", "s2", "s2"] and c1["narration"].startswith("After rain") and c1["take_id"] == "t01"
    assert [f["id"] for f in plan["screenplay"]["folders"]] == ["s1", "s2"] and cards[2]["folder_id"] == "s2"
    meta = plan["screenplay"]["anchor_images"]["plan"]
    assert meta["slug"] == pi.plan_slug(good()) and meta["pictures"] == 6 and meta["takes"] == 4 and meta["join"] == "matched_pictures"


def test_vertical_format_sets_the_card_size():
    p = good()
    p["format"] = "9:16"
    c = pi.plan_to_cards(p)["screenplay"]["scenes"][0]
    assert (c["width"], c["height"]) == (768, 1344)


def test_seamless_chain_imports_as_matched_pictures_and_says_so():
    p = good()
    p["scenes"] = p["scenes"][:1]
    p["takes"] = p["takes"][:2]
    p["production"].update(join="seamless_chain", total_seconds=10, clip_seconds=5)
    res = pi.plan_to_cards(p)
    assert res["screenplay"]["anchor_images"]["plan"]["join"] == "matched_pictures" and any("seamless" in w.lower() for w in res["warnings"])


def test_pictures_needed_counts_what_will_be_drawn():
    assert pi.pictures_needed(good()) == 6  # t01 start+end, t02 end, t03 start+end (new scene), t04 end
    p = good()
    p["takes"][1].update(start_from="new_picture", start_picture="Mira stands on the right side of the frame; Pip stands beside her; the clearing sky above them.")
    assert pi.pictures_needed(p) == 6  # storyboard.draw starts a same-place, same-cast take from the previous end picture anyway
    assert any("t02" in w and "previous end picture" in w for w in pi.plan_to_cards(p)["warnings"])


def test_invalid_plans_never_convert():
    p = good()
    p["takes"][0]["narration"] = "Too short."
    with pytest.raises(ValueError) as e:
        pi.plan_to_cards(p)
    assert "narration has 2 words" in str(e.value)


# ---- workspace + the picture job (the real storyboard.draw is replaced by a fake that writes the same files)
def test_workspace_keeps_the_plan_and_the_story(tmp_path):
    plan = good()
    ws = pi.save_workspace(plan, tmp_path)
    assert (ws / "plan.json").exists() and json.loads((ws / "plan.json").read_text(encoding="utf-8")) == plan
    assert (ws / "story.json").exists() and ws.name == pi.plan_slug(plan)
    assert pi.load_story(ws).bible.premise.title == "Why Do Rainbows Appear?"


def fake_draw(ws, story, problems=None):
    def draw(progress):
        fd = film.film_dir(ws)
        for p in story.panels:
            (fd / "frames" / f"{p.id}.png").write_bytes(b"start-" + p.id.encode())
            progress(f"  {p.id}: try 1: cast counts match the plan")
            (fd / "frames" / f"{p.id}_end.png").write_bytes(b"end-" + p.id.encode())
            progress(f"  {p.id}: end")
        return {p.id: {"chained": False, "attempts": 1, "problems": (problems or {}).get(p.id, {})} for p in story.panels}
    return draw


def test_picture_job_copies_frames_into_the_input_folder_and_reports_problems(tmp_path):
    ws, inp = tmp_path / "ws", tmp_path / "inputs"
    inp.mkdir()
    story = pi.plan_to_story(good())
    state = pi.new_job_state(pi.plan_slug(good()), story)
    asyncio.run(pi.run_pictures(story, ws, inp, state, fake_draw(ws, story, {"t02": {"end": ["cat: counted 2, planned 1"]}})))
    assert state["status"] == "done" and state["done_takes"] == 4 and state["error"] == ""
    slug = pi.plan_slug(good())
    t1 = next(i for i in state["items"] if i["take_id"] == "t01")
    assert t1["start"] == f"{slug}_t01_start.png" and t1["end"] == f"{slug}_t01_end.png"
    assert (inp / t1["start"]).read_bytes() == b"start-t01" and (inp / t1["end"]).read_bytes() == b"end-t01"
    assert next(i for i in state["items"] if i["take_id"] == "t02")["problems"] == ["end: cat: counted 2, planned 1"]
    assert next(i for i in state["items"] if i["take_id"] == "t03")["problems"] == []


def test_picture_job_failure_is_reported_not_swallowed(tmp_path):
    story = pi.plan_to_story(good())
    state = pi.new_job_state("x", story)

    def broken(progress):
        raise RuntimeError("Qwen Image 2.1 is not ready: ComfyUI is down")

    asyncio.run(pi.run_pictures(story, tmp_path / "ws", tmp_path, state, broken))
    assert state["status"] == "failed" and "ComfyUI is down" in state["error"]
