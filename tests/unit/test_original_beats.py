import asyncio

from engine.original import beats
from engine.original.genres import GENRES
from engine.original.models import Line, OriginalStory, Panel, Scene
from tests.unit.test_original_story import full_bible


def test_split_caption_groups_sentences_up_to_the_word_limit():
    t = "Pip takes a deep breath. The forest hum begins to lower. He steps out of the dark hollow, ready to catch the first drifting whispers for his basket."
    parts = beats.split_caption(t, 14)
    assert parts == ["Pip takes a deep breath. The forest hum begins to lower.", "He steps out of the dark hollow, ready to catch the first drifting whispers for his basket."]
    assert beats.split_caption("One short line.") == ["One short line."] and beats.split_caption("") == []


def story():
    p = Panel(id="p010", scene_id="sc01", shot="wide", angle="eye_level", location_id="attic", character_ids=["mira", "pip"],
              action="old action", caption="The attic glows softly tonight and everything is still and quiet and warm, with moonlight on the old wooden floor. "
                                           "Mira closes her eyes, drifting peacefully into dreams while the lamp keeps watch.",
              dialogue=[Line(speaker_id="pip", text="Sleep well.")], sfx=["hush"])
    return OriginalStory(bible=full_bible(), scenes=[Scene(id="sc01", location_id="attic", character_ids=["mira"], summary="s", mood="m")], panels=[p])


def shot(**kw):
    base = dict(shot="medium", camera="eye_level", setting="a dusty attic with a round window", lighting="warm lamp light", mood="calm",
                key_visuals=["lamp glowing"],
                characters=[dict(id="mira", side="left", pose="sitting on the floor", expression="calm", action="holding a lamp"),
                            dict(id="pip", side="right", pose="perched on a beam", expression="alert", action="watching")])
    return beats._Shot(**{**base, **kw})


class Director:
    def __init__(self, fail=False):
        self.prompts, self.fail = [], fail

    async def generate_structured(self, prompt, model, **kw):
        self.prompts.append(prompt)
        if self.fail:
            return shot(shot="nonsense", characters=[])
        spoken = prompt.split("reads this aloud while the picture is on screen:")[1].split("Cast (use these ids)")[0]
        if "closes her eyes" in spoken:
            return shot(shot="Close", camera="Eye Level", key_visuals=["eyes closed", "asleep in bed with a very long extra phrase here"],
                        characters=[dict(id="Mira", side="center", pose="lying curled on her side", expression="eyes closed, peaceful smile", action="resting her head")])
        return shot(shot="wide", characters=[])  # nobody named: a wide shot of the place


def test_each_narrated_moment_gets_its_own_directed_picture():
    d = Director()
    out = asyncio.run(beats.expand_story(story(), d))
    assert [p.id for p in out.panels] == ["p010_1", "p010_2"]
    a, b = out.panels
    assert a.shot == "wide" and a.caption.startswith("The attic glows") and a.dialogue == [] and a.sfx == [] and a.director["lighting"] == "warm lamp light"
    assert b.shot == "close" and b.character_ids == ["mira", "pip"] and b.director["characters"][0]["pose"] == "lying curled on her side"
    assert b.key_visuals == ["eyes closed", "sleeping"]  # pattern rules first; a phrase over 5 words is dropped, never cut off mid-sentence
    assert [x.text for x in b.dialogue] == ["Sleep well."] and b.sfx == ["hush"]  # dialogue and SFX belong to the last beat
    assert "(a dusty attic with a round window; warm lamp light)" in d.prompts[1].split("Previous picture:")[1]  # continuity: the director sees the previous shot


def test_a_moment_about_one_characters_face_and_every_named_character_are_enforced():
    bible = story().bible
    assert beats.focus_character("Mira closes her eyes, drifting into dreams.", bible) == "mira"
    assert beats.focus_character("Mira and Pip close their eyes.", bible) is None
    assert beats.focus_character("The attic glows softly tonight.", bible) is None
    g = GENRES["bedtime"]
    wide = shot(shot="wide")
    assert any("about mira alone" in m for m in beats._check(wide, bible, g, "Mira closes her eyes."))
    pip_only = shot(characters=[dict(id="pip", side="center", pose="perched", expression="alert", action="watching")])
    assert any("names ['mira']" in m for m in beats._check(pip_only, bible, g, "Mira waves at Pip."))
    three = shot()
    three.characters.append(beats._CharOut(id="mira", side="center", pose="x", expression="y", action="z"))
    assert any("at most 2" in m for m in beats._check(three, bible, g, ""))


def test_failed_director_falls_back_to_a_spec_built_from_the_words_with_a_warning():
    out = asyncio.run(beats.expand_story(story(), Director(fail=True)))
    a, b = out.panels
    assert b.shot == "close" and b.director["characters"][0]["id"] == "mira" and "eyes closed" in b.director["key_visuals"]
    assert any("shot rejected" in w for w in out.warnings) and any("no shot could be directed" in w for w in out.warnings)


def test_speaker_is_added_to_the_picture_when_there_is_room():
    out = asyncio.run(beats.expand_story(story(), Director()))
    assert "pip" in out.panels[0].character_ids or "pip" in out.panels[1].character_ids


def test_media_story_prefers_the_beat_file(tmp_path):
    s = story()
    (tmp_path / "story.json").write_text(s.model_dump_json())
    assert len(beats.media_story(tmp_path).panels) == 1
    (tmp_path / beats.BEATS_FILE).write_text(asyncio.run(beats.expand_story(s, Director())).model_dump_json())
    assert len(beats.media_story(tmp_path).panels) == 2


def test_pose_requirements_come_from_the_words_not_from_the_model():
    assert beats.pose_keys("Pip closes his eyes, drifting peacefully into dreams while his friends keep watch.") == ["eyes closed", "sleeping"]
    assert beats.pose_keys("Mira yawns and smiles.") == ["yawning", "smiling"]
    assert beats.pose_keys("The attic glows softly.") == []
    assert beats.pose_keys("He drifts into a peaceful slumber, carried by the hum.") == ["sleeping"]
    assert beats.pose_keys("Pip dozes by the fire.") == ["sleeping"]
    out = asyncio.run(beats.expand_story(story(), Director(fail=True)))
    assert "eyes closed" in out.panels[1].key_visuals
