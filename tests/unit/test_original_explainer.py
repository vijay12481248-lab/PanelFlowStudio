import pytest

from engine.original import explainer as ex
from engine.original import video as v
from engine.original.models import Scene

HEAD = """title: Why Do We Yawn? The Contagious Mystery
slug: vox_test_yawn
logline: Maya yawns in a meeting and wonders why.
thumb: CATCHING | p002
"""
S1 = "scene: s1 | living_room | funny | The yawn | Maya yawns on the sofa.\n"
S2 = "scene: s2 | diagram | curious | The theories | Three ideas.\n"


def beat(shot="medium", loc="living_room", chars="maya", narr="Maya yawns so wide that the whole room seems to blink twice.",
         vis="Maya on the sofa with a huge yawn, eyes squeezed shut, hand over her mouth.", keys="a big yawn", at=""):
    return f"beat{at}: {shot} | {loc} | {chars} | {narr} | {vis} | {keys}\n"


TWO = HEAD + S1 + beat() + beat(chars="maya,biscuit", narr="Maya looks at Biscuit and Biscuit looks away from the yawning.")


def test_builds_a_story_with_ids_scenes_and_meta():
    s = ex.build_story(TWO)
    assert [p.id for p in s.panels] == ["p001", "p002"]
    assert s.meta["thumb_text"] == "CATCHING" and s.meta["thumb_panel"] == "p002"
    assert s.scenes[0].title == "The yawn" and s.scenes[0].character_ids == ["biscuit", "maya"]
    assert [c.id for c in s.bible.characters] == ["maya", "biscuit"]


def test_zero_character_close_shot_becomes_wide():
    s = ex.build_story(HEAD + S1 + beat() + S2 + beat(shot="close", loc="diagram", chars="",
                       narr="Scientists have a few ideas about why a yawn spreads between people.",
                       vis="A glowing blue brain shape on the plain navy backdrop."))
    assert s.panels[1].shot == "wide" and s.panels[1].scene_id == "s2"


def test_every_problem_is_reported_at_once():
    bad = HEAD + S1 + beat(narr="Too short.") + beat(chars="maya", narr="Dev walks in and Maya stands up to greet him warmly today.") + \
        beat(vis="Maya crying with red wet eyes and tears.") + beat(chars="maya,biscuit,dev") + beat(chars="ghost") + beat(shot="zoom")
    with pytest.raises(ValueError) as e:
        ex.build_story(bad)
    msg = str(e.value)
    for needle in ("must be 6-24", "names Dev", "blood", "at most 2", "unknown character 'ghost'", "shot 'zoom'"):
        assert needle in msg, needle


def test_explicit_beat_ids_keep_other_ids_stable():
    s = ex.build_story(HEAD + S1 + beat() + beat(at="@p001a", narr="Maya gasps at a second huge yawn from nowhere at all.") +
                       beat(narr="The cat sits next to Maya and watches without moving at all."))
    assert [p.id for p in s.panels] == ["p001", "p001a", "p002"]


def test_thumbnail_words_must_not_repeat_the_title():
    with pytest.raises(ValueError, match="repeat the title"):
        ex.build_story(TWO.replace("CATCHING", "CONTAGIOUS"))


def test_runtime_estimate_matches_the_measured_pace():
    s = ex.build_story(TWO)
    assert ex.estimate_seconds(s) == pytest.approx(sum(len(p.caption.split()) for p in s.panels) * ex.SECONDS_PER_WORD)
    assert any("floor" in w for w in ex.lint(s))


def test_chapter_labels_use_the_scene_title():
    s = ex.build_story(TWO)
    s.scenes += [Scene(id="s2", location_id="kitchen", character_ids=[], summary="x", mood="m"),
                 Scene(id="s3", location_id="kitchen", character_ids=[], summary="y", mood="m")]
    tl = {"entries": [{"scene_id": "s1", "start": 0.0}, {"scene_id": "s2", "start": 30.0}, {"scene_id": "s3", "start": 60.0}]}
    assert v.chapters(s, tl)[0] == ("0:00", "The yawn")


def test_thumbnail_text_goes_on_the_quiet_side(tmp_path):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1344, 768), "#335577")
    d = ImageDraw.Draw(img)
    for x in range(700, 1344, 12):  # a busy right side
        d.line((x, 0, x, 768), fill="#ffffff" if (x // 12) % 2 else "#000000", width=6)
    src = tmp_path / "p.png"
    img.save(src)
    out = v.thumbnail_with_text(src, "NOT WEAK", tmp_path / "t.jpg")
    t = Image.open(out)
    assert t.size == (1280, 720)
    light = sum(1 for x in range(0, 560, 4) for y in range(0, 720, 4) if min(t.getpixel((x, y))) > 235)
    assert light > 150  # the white word landed on the calm left side
