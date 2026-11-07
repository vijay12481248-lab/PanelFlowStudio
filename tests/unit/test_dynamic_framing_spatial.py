import io
from pathlib import Path
from PIL import Image

from engine.original import art
from engine.original import shotspec as ss
from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene
from tests.unit.test_original_story import full_bible


def test_resolve_dimensions_aspect_ratios():
    # 1. Full-body / standing / character sheet shots -> Portrait (832x1216)
    assert ss.resolve_dimensions("full", num_characters=1) == (832, 1216)
    assert ss.resolve_dimensions("full_body", num_characters=1) == (832, 1216)
    assert ss.resolve_dimensions("Full-Body", num_characters=1) == (832, 1216)
    assert ss.resolve_dimensions("character_sheet", num_characters=1) == (832, 1216)
    assert ss.resolve_dimensions("sheet", num_characters=1) == (832, 1216)
    assert ss.resolve_dimensions("portrait", num_characters=1) == (832, 1216)

    # 2. Close / extreme close / medium / cowboy -> Square (1024x1024)
    assert ss.resolve_dimensions("close", num_characters=1) == (1024, 1024)
    assert ss.resolve_dimensions("extreme_close", num_characters=1) == (1024, 1024)
    assert ss.resolve_dimensions("medium", num_characters=1) == (1024, 1024)
    assert ss.resolve_dimensions("cowboy", num_characters=1) == (1024, 1024)

    # 3. Wide / scenery / over-the-shoulder
    assert ss.resolve_dimensions("wide", num_characters=1) == (1344, 768)
    assert ss.resolve_dimensions("extreme_wide", num_characters=1) == (1344, 768)
    assert ss.resolve_dimensions("landscape", num_characters=1) == (1344, 768)
    assert ss.resolve_dimensions("over_shoulder", num_characters=1) == (1152, 896)

    # 4. Two or more characters side-by-side -> Always Widescreen Landscape (1344x768)
    assert ss.resolve_dimensions("close", num_characters=2) == (1344, 768)
    assert ss.resolve_dimensions("medium", num_characters=2) == (1344, 768)
    assert ss.resolve_dimensions("full", num_characters=2) == (1344, 768)

    # 5. None / Unknown -> Fallback to default
    assert ss.resolve_dimensions(None) == (1344, 768)
    assert ss.resolve_dimensions("unknown_exotic_shot") == (1344, 768)
    assert ss.resolve_dimensions("unknown_exotic_shot", default=(1024, 1024)) == (1024, 1024)


def test_interaction_kinematic_compilation_tags():
    # Detects interactions from action strings
    tags_holding = ss.compile_interaction_bindings_tags(["holding a heavy silver sword"])
    assert "firmly gripped in hands" in tags_holding
    assert "physical contact visible" in tags_holding
    assert "zero gap" in tags_holding

    tags_carrying = ss.compile_interaction_bindings_tags(["carrying a lost lantern through fog"])
    assert "holding securely against body" in tags_carrying
    assert "hands supporting object" in tags_carrying

    tags_hugging = ss.compile_interaction_bindings_tags(["hugging an old companion"])
    assert "arms wrapped tightly around" in tags_hugging
    assert "embracing" in tags_hugging

    # Word boundary guard: substrings must not trigger false positives
    tags_negative = ss.compile_interaction_bindings_tags(["beholding the sunset", "the cold wind blows", "should be fine"])
    assert tags_negative == []


def test_interaction_kinematic_compilation_natural():
    phrases = ss.compile_interaction_bindings_natural(["gripping the stone ledge tightly"])
    assert any("fingers wrapped firmly around it" in p for p in phrases)

    phrases_touch = ss.compile_interaction_bindings_natural(["touching the glowing runes"])
    assert any("no air gap between them" in p for p in phrases_touch)

    phrases_reading = ss.compile_interaction_bindings_natural(["reading an ancient parchment"])
    assert any("visible finger contact on the cover or pages" in p for p in phrases_reading)


def test_margin_and_contact_tokens_in_composed_prompts():
    story = OriginalStory(bible=full_bible(), scenes=[], panels=[])

    # 1. Tag composer for full body shot with object interaction
    spec_full = ss.ShotSpec(
        shot="full",
        characters=[ss.CharPose(id="mira", side="center", pose="standing tall", expression="determined", action="holding a wooden staff")],
        setting="stone temple courtyard",
    )
    pos_tag, neg_tag = ss.compose(story, spec_full, "attic")

    # Margin tokens
    assert "full body" in pos_tag
    assert "head to toe" in pos_tag
    assert "visible feet" in pos_tag
    assert "wide margins" in pos_tag

    # Kinematic contact tokens
    assert "firmly gripped in hands" in pos_tag
    assert "physical contact visible" in pos_tag
    assert "zero gap" in pos_tag

    # Negative prompt suppresses floating and disconnected parts
    assert "floating objects" in neg_tag
    assert "disconnected hands" in neg_tag

    # 2. Natural language composer for full body shot
    pos_nat, neg_nat = ss.compose_natural(story, spec_full, "attic")
    assert "Full body shot from head to toe with visible feet resting on the ground" in pos_nat
    assert "Physical contact: hands firmly gripping the object with fingers visibly curled around it" in pos_nat


def test_compose_natural_simplify_omits_optional_decorations():
    story = OriginalStory(bible=full_bible(), scenes=[], panels=[])
    spec = ss.ShotSpec(
        shot="full",
        characters=[ss.CharPose(id="mira", side="center", pose="standing", expression="calm", action="holding a crystal orb")],
        setting="a crystal cave",
    )
    pos, _ = ss.compose_natural(story, spec, "attic", emphasis=["the crystal orb"], simplify=True)
    assert pos.startswith("Most important: the picture must clearly show the crystal orb.")
    # In simplify mode, kinematic and margin clauses are omitted to avoid diluting the critical missing visual
    assert "Physical contact:" not in pos
    assert "generous margins around the subject" not in pos


def _make_story():
    b = Bible(
        premise=Premise(title="Test Story", genre="fantasy", logline="log", tone="tone", setting="setting"),
        characters=[
            Character(id="hero", name="Hero", role="protagonist", age_group="adult", look="silver armor, blue cape, dark hair", personality="brave"),
            Character(id="companion", name="Companion", role="other", age_group="teen", look="green tunic, leather boots, blonde hair", personality="loyal"),
        ],
        locations=[Location(id="citadel", name="Citadel", look="ancient white stone walls, banners, arches")],
    )
    panels = [
        Panel(id="p001", scene_id="s1", shot="full", angle="eye_level", location_id="citadel", character_ids=["hero"], action="Hero stands holding a halberd."),
        Panel(id="p002", scene_id="s1", shot="close", angle="low", location_id="citadel", character_ids=["hero"], action="Hero smiles."),
        Panel(id="p003", scene_id="s1", shot="medium", angle="eye_level", location_id="citadel", character_ids=["hero", "companion"], action="Hero talks with Companion."),
    ]
    return OriginalStory(bible=b, scenes=[Scene(id="s1", location_id="citadel", character_ids=["hero", "companion"], summary="s", mood="m")], panels=panels)


def _dummy_png():
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "blue").save(buf, "PNG")
    return buf.getvalue()


class CapturingRunner:
    def __init__(self):
        self.calls = []

    def generate(self, pos, neg, seed, w, h, prefix, reference=None, reference_b=None, **kw):
        self.calls.append({"prefix": prefix, "w": w, "h": h, "ref": reference, "ref_b": reference_b, "pos": pos})
        return _dummy_png()


def test_art_generator_dispatches_dynamic_dimensions(tmp_path):
    story = _make_story()
    runner = CapturingRunner()

    out = art.generate_art(story, tmp_path, runner)
    assert out["generated"] == 3

    # Check character sheets: should be rendered in portrait mode (832x1216)
    sheet_calls = [c for c in runner.calls if c["prefix"].startswith("sheet_")]
    assert len(sheet_calls) == 2
    for s in sheet_calls:
        assert (s["w"], s["h"]) == (832, 1216)

    # Check panels:
    panel_calls = {c["prefix"]: c for c in runner.calls if c["prefix"].startswith("panel_")}

    # p001: 1 character, full body -> (832, 1216) portrait
    assert (panel_calls["panel_p001"]["w"], panel_calls["panel_p001"]["h"]) == (832, 1216)
    assert "firmly gripped in hands" in panel_calls["panel_p001"]["pos"]

    # p002: 1 character, close-up -> (1024, 1024) square
    assert (panel_calls["panel_p002"]["w"], panel_calls["panel_p002"]["h"]) == (1024, 1024)

    # p003: 2 characters -> (1344, 768) widescreen landscape
    assert (panel_calls["panel_p003"]["w"], panel_calls["panel_p003"]["h"]) == (1344, 768)


def test_hash_incorporates_dimensions():
    pos = "solo, hero, armor"
    neg = "lowres, bad anatomy"
    h1 = art._hash(pos, neg, dims=(1344, 768))
    h2 = art._hash(pos, neg, dims=(832, 1216))
    h3 = art._hash(pos, neg, dims=(1024, 1024))

    assert h1 != h2
    assert h2 != h3
    assert h1 != h3
    # Default without dims matches (1344, 768) for backward compatibility
    assert art._hash(pos, neg) == h1


def test_a_story_that_asks_for_the_video_frame_draws_every_panel_16_by_9(tmp_path):
    story = _make_story()
    story.meta["frame"] = "16:9"  # the explainer format: a square close-up would sit on blurred side bars in the video
    runner = CapturingRunner()
    art.generate_art(story, tmp_path, runner)
    panels = [c for c in runner.calls if c["prefix"].startswith("panel_")]
    assert panels and all((c["w"], c["h"]) == (1344, 768) for c in panels)
    sheets = [c for c in runner.calls if c["prefix"].startswith("sheet_")]
    assert all((c["w"], c["h"]) == (832, 1216) for c in sheets)  # character sheets keep their portrait shape
