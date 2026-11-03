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


def test_character_description_is_the_same_words_every_time():
    elder = full_bible().characters[0].model_copy(update={"age_group": "elder", "gender": "male"})
    assert ss.describe_character(elder).startswith("an old man with a wrinkled face with ")
    fox = elder.model_copy(update={"species": "fox cub"})
    assert ss.describe_character(fox).startswith("a fox cub with ")
