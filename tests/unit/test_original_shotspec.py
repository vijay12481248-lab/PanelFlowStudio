from engine.original import shotspec as ss
from tests.unit.test_original_story import full_bible
from engine.original.models import OriginalStory

STORY = OriginalStory(bible=full_bible(), scenes=[], panels=[])


def spec(**kw):
    base = dict(shot="close", camera="low", setting="a dusty attic with a round window", lighting="warm golden lamp light", mood="peaceful",
                key_visuals=["eyes closed"],
                characters=[ss.CharPose(id="mira", side="center", pose="lying curled on her side", expression="eyes closed, peaceful smile",
                                        action="hugging a pillow")])
    return ss.ShotSpec(**{**base, **kw})


def test_prompt_is_composed_from_the_spec_with_vocabulary_tags_and_weights():
    pos, neg = ss.compose(STORY, spec(), "attic")
    for needle in ("solo", "short brown hair", "closed eyes", "serene", "lying down", "(closed eyes:1.3)", "hug", "dusty attic",
                   "warm lighting", "close-up", "from below", "storybook"):
        assert needle in pos, needle
    assert "open eyes" in neg and "nsfw" in neg  # closed eyes: the model is told not to draw open ones
    assert pos.count("(closed eyes:1.3)") == 1  # no duplicated tokens


def test_two_characters_are_ordered_left_to_right_for_the_masked_workflow():
    s = spec(characters=[ss.CharPose(id="pip", side="right", pose="perched", expression="alert", action="watching"),
                         ss.CharPose(id="mira", side="left", pose="sitting", expression="calm", action="holding a lamp")])
    pos, _ = ss.compose(STORY, s, "attic")
    assert "2others" in pos and pos.index("short brown hair") < pos.index("small grey owl")  # Mira (left) first


def test_emphasis_from_a_failed_attempt_is_weighted():
    pos, _ = ss.compose(STORY, spec(key_visuals=["lamp glowing"]), "attic", emphasis=["lamp glowing", "a red scarf"])
    assert "(lamp glowing:1.3)" in pos and "(a red scarf:1.4)" in pos


def test_from_behind_shots_negate_looking_at_the_viewer_and_pose_sensitivity_is_detected():
    s = spec(key_visuals=["seen from behind"], characters=[ss.CharPose(id="mira", pose="standing, facing away", expression="unseen", action="")])
    pos, neg = ss.compose(STORY, s, "attic")
    assert "looking at viewer" in neg and ss.pose_sensitive(s)
    assert not ss.pose_sensitive(spec(key_visuals=["lamp"], characters=[ss.CharPose(id="mira", pose="standing", expression="smiling", action="waving")]))


def test_required_text_names_characters_with_their_look_for_the_judge():
    text = spec().required_text({c.id: c for c in STORY.bible.characters})
    assert "Mira (short brown hair)" in text and "eyes closed, peaceful smile" in text and "Must be visible: eyes closed" in text


def test_natural_language_prompt_for_prompt_following_models():
    s = spec(shot="medium", camera="eye_level", key_visuals=["a silver bell on the wall", "eyes open"],
             characters=[ss.CharPose(id="pip", side="right", pose="standing", expression="wide-eyed", action="staring at the bell"),
                         ss.CharPose(id="mira", side="left", pose="sitting", expression="calm", action="holding a lamp")])
    pos, neg = ss.compose_natural(STORY, s, "attic", emphasis=["a silver bell on the wall"])
    assert neg == "" and pos.index("On the left:") < pos.index("On the right:")  # Mira (left) first
    for needle in ("Medium shot from the waist up.", "a little girl with short brown hair", "Sitting, calm, holding a lamp", "Setting: Attic",
                   "The picture must clearly show: a silver bell on the wall; eyes open.", "Pay special attention to: a silver bell on the wall.",
                   "No text, no captions, no speech bubbles"):
        assert needle in pos, needle
    assert "masterpiece" not in pos and ":1.3)" not in pos  # no booru tags or weights
    none, _ = ss.compose_natural(STORY, spec(characters=[]), "attic")
    assert "There are no people in the picture." in none


def test_natural_prompt_uses_the_genres_own_style_phrase_not_a_generic_anime_label():
    fantasy = STORY.model_copy(deep=True)
    fantasy.bible.premise.genre = "fantasy"  # its art_style ends in "dramatic lighting": the old code fell back to "Anime illustration"
    pos, _ = ss.compose_natural(fantasy, spec(), "attic")
    assert pos.startswith("Fantasy anime style.") and "Anime illustration" not in pos


def test_character_names_never_reach_the_image_prompt_as_words():
    from engine.original.models import Character

    cat = Character(id="biscuit", name="Biscuit", role="protagonist", age_group="adult", species="cat", gender="male", look="orange fur", personality="p")
    doc = Character(id="gravity", name="Dr. Gravity", role="other", age_group="elder", species="human", gender="female", look="white coat", personality="p")
    out = ss.unname("Biscuit taps the glass. So Biscuit's paw hovers while Gravity watches, then Dr. Gravity nods.", [cat, doc])
    assert "Biscuit" not in out and "Gravity" not in out and "Dr." in out  # the title is not a name, the person is
    assert out.startswith("The cat taps the glass. So the cat's paw hovers") and "the old woman" in out
    assert ss.unname("the biscuit nudges a glass off the table", [cat]) == "the cat nudges a glass off the table"  # LLM claims lowercase names
    assert ss.unname("The Biscuit blinks", [cat]) == "The cat blinks"
    s = STORY.model_copy(deep=True)
    pos, _ = ss.compose_natural(s, spec(characters=[ss.CharPose(id="mira", pose="standing", expression="smiling", action="Mira waves at Pip")],
                                        key_visuals=["Mira waving"]), "attic")
    assert "Mira waves" not in pos and "Mira waving" not in pos  # names removed from actions and key visuals


def test_director_prompt_carries_the_panel_author_note_to_resolve_ambiguous_nouns():
    import asyncio
    from engine.original import beats
    from engine.original.models import Panel

    seen = []

    class P:
        async def generate_structured(self, prompt, *a, **kw):
            seen.append(prompt)
            raise ValueError("stop")  # direct_shot turns a ValueError into None; only the prompt matters here

    panel = Panel(id="p1", scene_id="s", shot="medium", angle="eye_level", location_id="attic", character_ids=["mira"],
                  action="Mira pushes a drinking glass of water off a table", caption="She taps the glass.")
    asyncio.run(beats.direct_shot(P(), STORY, panel, "She taps the glass.", None, []))
    assert "Author note" in seen[0] and "drinking glass of water" in seen[0]


def test_character_description_is_the_same_words_every_time():
    elder = full_bible().characters[0].model_copy(update={"age_group": "elder", "gender": "male"})
    assert ss.describe_character(elder).startswith("an old man with a wrinkled face with ")
    fox = elder.model_copy(update={"species": "fox cub"})
    assert ss.describe_character(fox).startswith("a fox cub with ")


def test_shot_dimensions_preview_table_is_valid_and_multiples_of_16():
    for shot, (w, h) in ss.SHOT_DIMENSIONS_PREVIEW.items():
        assert w % 16 == 0, f"{shot} width {w} must be multiple of 16"
        assert h % 16 == 0, f"{shot} height {h} must be multiple of 16"
        mp = (w * h) / 1_000_000
        assert 0.20 <= mp <= 0.35, f"{shot} megapixels {mp} should be around 0.25 MP"


def test_resolve_dimensions_preview_mode():
    w, h = ss.resolve_dimensions("wide", preview=True)
    assert (w, h) == ss.SHOT_DIMENSIONS_PREVIEW["wide"]
    assert (w, h) == (672, 384)

    w_std, h_std = ss.resolve_dimensions("wide", preview=False)
    assert (w_std, h_std) == (1344, 768)

    w_close, h_close = ss.resolve_dimensions("close", preview=True)
    assert (w_close, h_close) == ss.SHOT_DIMENSIONS_PREVIEW["close"]
    assert (w_close, h_close) == (512, 512)

    w_full, h_full = ss.resolve_dimensions("full", num_characters=1, preview=True)
    assert (w_full, h_full) == (416, 608)

    w_char2, h_char2 = ss.resolve_dimensions("full", num_characters=2, preview=True)
    assert (w_char2, h_char2) == (672, 384)

