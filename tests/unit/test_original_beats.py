import asyncio

from engine.original import beats
from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene
from tests.unit.test_original_story import full_bible


def test_split_caption_groups_sentences_up_to_the_word_limit():
    t = "Pip takes a deep breath. The forest hum begins to lower. He steps out of the dark hollow, ready to catch the first drifting whispers for his basket."
    parts = beats.split_caption(t, 14)
    assert parts == ["Pip takes a deep breath. The forest hum begins to lower.", "He steps out of the dark hollow, ready to catch the first drifting whispers for his basket."]
    assert beats.split_caption("One short line.") == ["One short line."] and beats.split_caption("") == []


def story():
    b = full_bible()
    p = Panel(id="p010", scene_id="sc01", shot="wide", angle="eye_level", location_id="attic", character_ids=["mira", "pip"],
              action="old action", caption="The attic glows softly tonight and everything is still and quiet and warm, with moonlight on the old wooden floor. Mira closes her eyes, drifting peacefully into dreams while Pip keeps watch.",
              dialogue=[Line(speaker_id="pip", text="Sleep well.")], sfx=["hush"])
    return OriginalStory(bible=b, scenes=[Scene(id="sc01", location_id="attic", character_ids=["mira"], summary="s", mood="m")], panels=[p])


class Illustrator:
    def __init__(self, fail=False):
        self.prompts, self.fail = [], fail

    async def generate_structured(self, prompt, model, **kw):
        self.prompts.append(prompt)
        if self.fail:
            return model(shot="nonsense", character_ids=["ghost"], action="x", key_visuals=[])
        if "closes her eyes" in prompt.split("saying this right now:")[1].split("Characters:")[0]:
            return model(shot="Close", character_ids=["Mira"], action="Mira sleeps peacefully with her eyes closed in bed",
                         key_visuals=["eyes closed", "asleep in bed with a very long extra phrase here"])
        return model(shot="wide", character_ids=["mira", "pip"], action="The attic glows softly while the friends rest quietly", key_visuals=["soft glow"])


def test_each_narrated_moment_gets_its_own_picture_built_from_the_spoken_text():
    ill = Illustrator()
    out = asyncio.run(beats.expand_story(story(), ill))
    assert [p.id for p in out.panels] == ["p010_1", "p010_2"]
    a, b = out.panels
    assert a.shot == "wide" and a.caption.startswith("The attic glows") and a.dialogue == [] and a.sfx == []
    assert b.shot == "close" and b.character_ids == ["mira", "pip"] and "eyes closed" in b.action
    assert b.key_visuals == ["eyes closed", "sleeping", "asleep in bed with a very"]  # a long phrase is trimmed to 6 words, not rejected
    assert [d.text for d in b.dialogue] == ["Sleep well."] and b.sfx == ["hush"]  # dialogue and SFX belong to the last beat
    assert "The previous picture showed: The attic glows" in ill.prompts[1]


def test_speaker_is_added_to_the_picture_and_a_failed_brief_falls_back_with_a_warning():
    out = asyncio.run(beats.expand_story(story(), Illustrator(fail=True)))
    a, b = out.panels
    assert a.action == a.caption and a.shot == "wide"  # the spoken words are the fallback brief, not the panel's separate action
    assert b.action == b.caption and b.shot == "wide" and b.character_ids == ["mira", "pip"]  # two characters named: no single focus
    assert any("brief rejected" in w for w in out.warnings) and any("no brief could be written" in w for w in out.warnings)


def test_media_story_prefers_the_beat_file(tmp_path):
    s = story()
    (tmp_path / "story.json").write_text(s.model_dump_json())
    assert len(beats.media_story(tmp_path).panels) == 1
    (tmp_path / beats.BEATS_FILE).write_text(asyncio.run(beats.expand_story(s, Illustrator())).model_dump_json())
    assert len(beats.media_story(tmp_path).panels) == 2


def test_a_moment_about_one_characters_eyes_must_not_be_a_wide_group_shot():
    bible = story().bible
    assert beats.focus_character("Mira closes her eyes, drifting into dreams.", bible) == "mira"
    assert beats.focus_character("Mira and Pip close their eyes.", bible) is None  # two characters named: no single focus
    assert beats.focus_character("The attic glows softly tonight.", bible) is None
    wide = beats._Brief(shot="wide", character_ids=["mira", "pip"], action="Everyone rests in the glowing attic quietly", key_visuals=["glow"])
    assert any("about mira alone" in m for m in beats._check(wide, bible, __import__("engine.original.genres", fromlist=["GENRES"]).GENRES["bedtime"], "Mira closes her eyes."))


def test_pose_requirements_come_from_the_words_not_from_the_model():
    assert beats.pose_keys("Pip closes his eyes, drifting peacefully into dreams while his friends keep watch.") == ["eyes closed", "sleeping"]
    assert beats.pose_keys("Mira yawns and smiles.") == ["yawning", "smiling"]
    assert beats.pose_keys("The attic glows softly.") == []
    out = asyncio.run(beats.expand_story(story(), Illustrator(fail=True)))
    assert "eyes closed" in out.panels[1].key_visuals  # present even when the brief failed


def test_slumber_and_dozing_count_as_sleeping():
    assert beats.pose_keys("He drifts into a peaceful slumber, carried by the hum.") == ["sleeping"]
    assert beats.pose_keys("Pip dozes by the fire.") == ["sleeping"]
