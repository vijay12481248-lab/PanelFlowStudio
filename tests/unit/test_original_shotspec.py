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
