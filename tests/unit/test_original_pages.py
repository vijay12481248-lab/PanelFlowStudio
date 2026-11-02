import pytest
from PIL import Image

from engine.original import lettering, pages
from engine.original.models import Bible, Character, Line, Location, OriginalStory, Panel, Premise, Scene


def story(n=7):
    chars = [Character(id=i, name=n_, role=r, age_group="child", look="a, b, c, d", personality="p")
             for i, n_, r in (("mira", "Mira", "protagonist"), ("pip", "Pip", "other"))]
    b = Bible(premise=Premise(title="Mira and the Moon", genre="bedtime", logline="A girl helps the moon sleep.", tone="t", setting="s"),
              characters=chars, locations=[Location(id="attic", name="Attic", look="a, b, c, d")])
    ps = [Panel(id=f"p{i + 1:03d}", scene_id="sc01", shot="medium", angle="eye_level", location_id="attic", character_ids=["mira", "pip"],
                action="two friends", caption="The moon is very quiet tonight and everyone is sleepy now. They wait.",
                dialogue=[Line(speaker_id="mira", text="Do you think the moon is lonely tonight, Pip?"),
                          Line(speaker_id="pip", text="Hoo hoo, maybe we can keep it company until the morning.")], sfx=["whoosh"])
          for i in range(n)]
    return OriginalStory(bible=b, scenes=[Scene(id="sc01", location_id="attic", character_ids=["mira"], summary="s", mood="m")], panels=ps)


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_balloons_stay_inside_and_do_not_overlap_each_other():
    s = story(1)
    img, boxes = lettering.letter_panel(Image.new("RGB", (1520, 740), "skyblue"), s.panels[0], s)
    assert len(boxes) == 3  # two balloons + the narrator box
    for b in boxes:
        assert 0 <= b[0] < b[2] <= 1520 and 0 <= b[1] < b[3] <= 740
    assert not overlap(boxes[0], boxes[1])  # left speaker and right speaker
    assert img.getpixel((boxes[0][0] + 20, (boxes[0][1] + boxes[0][3]) // 2)) in {(255, 255, 255), (0, 0, 0)}  # balloon was actually painted over the art


def test_same_speaker_balloons_stack_instead_of_overlapping():
    s = story(1)
    s.panels[0].dialogue = [Line(speaker_id="mira", text="First line here."), Line(speaker_id="mira", text="Second line goes below it.")]
    _, boxes = lettering.letter_panel(Image.new("RGB", (1520, 740), "white"), s.panels[0], s, caption=False)
    assert not overlap(boxes[0], boxes[1]) and boxes[1][1] > boxes[0][3]


def test_short_caption_limits_words_and_ends_cleanly():
    t = "First sentence is short. Second sentence runs a bit longer than the first one. Third sentence ends it all now."
    c = lettering.short_caption(t, 12)
    assert len(c.split()) <= 12 and c.endswith((".", "…"))
    assert lettering.short_caption("One.", 12) == "One."


def test_pages_are_three_panels_each_with_cover_and_pdf(tmp_path):
    s = story(7)
    (tmp_path / "panels").mkdir()
    for p in s.panels:
        Image.new("RGB", (1344, 768), "gray").save(tmp_path / "panels" / f"{p.id}.png")
    out = pages.build_pages(s, tmp_path)
    assert out["pages"] == 1 + 3 and out["missing_panels"] == []  # cover + ceil(7/3)
    for i in range(4):
        assert Image.open(tmp_path / "pages" / f"page_{i:03d}.png").size == (1600, 2400)
    assert (tmp_path / "comic.pdf").read_bytes().startswith(b"%PDF") and (tmp_path / "comic.pdf").read_bytes().count(b"/Type /Page") >= 4


def test_missing_images_are_reported_and_none_is_an_error(tmp_path):
    s = story(2)
    (tmp_path / "panels").mkdir()
    Image.new("RGB", (1344, 768), "gray").save(tmp_path / "panels" / "p001.png")
    assert pages.build_pages(s, tmp_path)["missing_panels"] == ["p002"]
    with pytest.raises(ValueError):
        pages.build_pages(s, tmp_path / "none")


def test_fit_slot_crops_wide_art_and_letterboxes_short_art():
    assert pages.fit_slot(Image.new("RGB", (1344, 768))).size == (pages.SLOT_W, pages.SLOT_H)
    assert pages.fit_slot(Image.new("RGB", (3000, 600))).size == (pages.SLOT_W, pages.SLOT_H)
