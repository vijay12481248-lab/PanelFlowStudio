"""Unit tests for WP-3.2: Character Turnaround Sheet Splicing and Zero-Drift Consistency."""
import io
from pathlib import Path
from PIL import Image

from engine.original import art, shotspec
from engine.original.models import Bible, Character, OriginalStory, Premise, Panel, Scene
from engine.original.rigging import (
    compile_turnaround_prompt,
    _create_offline_turnaround_image,
    RiggingSpec,
)
from engine.original.story import init_character_turnaround, init_bible_turnarounds


def make_story():
    mira = Character(
        id="mira",
        name="Mira",
        role="protagonist",
        age_group="child",
        look="short brown hair, green eyes, yellow raincoat, red boots",
        personality="curious",
    )
    bible = Bible(
        premise=Premise(title="T", genre="bedtime", logline="L", tone="T", setting="S"),
        characters=[mira],
        locations=[],
    )
    panels = [
        Panel(
            id="p001",
            scene_id="sc01",
            shot="medium",
            angle="eye_level",
            location_id="attic",
            character_ids=["mira"],
            action="Mira stands smiling.",
        )
    ]
    return OriginalStory(
        bible=bible,
        scenes=[
            Scene(
                id="sc01",
                location_id="attic",
                character_ids=["mira"],
                summary="S",
                mood="M",
            )
        ],
        panels=panels,
    )


def test_turnaround_dimensions_multiple_of_16():
    w, h = shotspec.resolve_dimensions("turnaround")
    assert (w, h) == (1536, 768)
    assert w % 16 == 0 and h % 16 == 0
    assert w / h == 2.0  # 2:1 ratio


def test_turnaround_prompt_enforces_clean_white_background():
    s = make_story()
    mira = s.bible.characters[0]
    prompt = compile_turnaround_prompt(mira, s, style_kind="natural")
    assert "clean pure white background" in prompt or "clean white background" in prompt
    assert "zero environment" in prompt or "no environment" in prompt
    assert "no text, no captions, no speech bubbles, no watermark" in prompt.lower()


def test_offline_turnaround_image_pure_white_background():
    s = make_story()
    mira = s.bible.characters[0]
    img = _create_offline_turnaround_image(mira, RiggingSpec(), (1536, 768))
    assert img.size == (1536, 768)
    # Check that canvas corners are pure solid white (255, 255, 255)
    pixels = img.load()
    assert pixels[0, 0] == (255, 255, 255)
    assert pixels[1535, 0] == (255, 255, 255)
    assert pixels[0, 767] == (255, 255, 255)
    assert pixels[1535, 767] == (255, 255, 255)


def test_bible_init_turnaround_automation(tmp_path):
    s = make_story()
    updated = init_bible_turnarounds(s, tmp_path)
    char = updated.bible.characters[0]
    assert char.turnaround_sheet is not None
    assert (tmp_path / char.turnaround_sheet).exists()


def test_generate_art_binds_turnaround_sheet_to_reference(tmp_path):
    class QwenFakeRunner:
        engine = "qwen"
        style = "natural"
        calls = []

        def generate(self, pos, neg, seed, w, h, prefix, reference=None, **kw):
            self.calls.append((prefix, reference))
            buf = io.BytesIO()
            Image.new("RGB", (w, h), "white").save(buf, "PNG")
            return buf.getvalue()

    s = make_story()
    r = QwenFakeRunner()
    art.generate_art(s, tmp_path, r)
    panel_call = next(c for c in r.calls if c[0] == "panel_p001")
    ref_arg = panel_call[1]
    assert ref_arg is not None
    assert "mira_turnaround.png" in str(ref_arg)
