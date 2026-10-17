"""
Unit tests for CaptionRenderer and EffectRenderer (Milestone 7).
Verifies subtitle word wrapping, contrast pill positioning, and cinematic visual effects.
"""
from PIL import Image, ImageStat
import numpy as np
import pytest

from engine.motion.models.cues import CaptionCue
from engine.motion.models.effects import EffectInstruction
from engine.motion.models.enums import EffectType
from engine.render.composer import CaptionRenderer, EffectRenderer


def test_caption_rendering_active_interval():
    renderer = CaptionRenderer()
    canvas = Image.new("RGB", (1920, 1080), color=(150, 150, 150))

    caption = CaptionCue(
        cue_id="cap_01",
        shot_id="shot_01",
        text="The shattered crystal hummed with ancient energy.",
        start_time=1.0,
        end_time=3.0,
        speaker_id="char_elena",
    )

    # 1. Before interval: unchanged
    before = renderer.render_captions(canvas, [caption], timestamp_sec=0.5, target_w=1920, target_h=1080)
    assert np.array_equal(np.array(canvas), np.array(before))

    # 2. Inside interval: rendered caption pill in bottom region
    during = renderer.render_captions(canvas, [caption], timestamp_sec=2.0, target_w=1920, target_h=1080)
    arr_during = np.array(during)
    # The bottom region (around y=900 to 1000) should contain the dark contrast pill
    bottom_crop = arr_during[880:980, 700:1220, :]
    assert bottom_crop.mean() < 120.0  # Darkened by semi-transparent dark pill

    # 3. After interval: unchanged
    after = renderer.render_captions(canvas, [caption], timestamp_sec=3.5, target_w=1920, target_h=1080)
    assert np.array_equal(np.array(canvas), np.array(after))


def test_caption_word_wrapping():
    renderer = CaptionRenderer()
    canvas = Image.new("RGB", (1920, 1080), color=(100, 100, 100))

    # Long text exceeding single-line width
    long_text = "This is an exceptionally long dialogue sequence where the protagonist explains the intricate metaphysical workings of the crystal resonance engine in great detail without taking a single breath."
    caption = CaptionCue(
        cue_id="cap_02",
        shot_id="shot_01",
        text=long_text,
        start_time=0.0,
        end_time=5.0,
    )

    rendered = renderer.render_captions(canvas, [caption], timestamp_sec=1.0, target_w=1920, target_h=1080)
    arr = np.array(rendered)
    # Text was rendered successfully and canvas size maintained
    assert rendered.size == (1920, 1080)
    assert not np.array_equal(np.array(canvas), arr)


def test_effect_impact_shake():
    renderer = EffectRenderer()
    canvas = Image.new("RGB", (1920, 1080), color=(100, 100, 100))
    # Add high-contrast vertical line to detect horizontal shift
    for y in range(1080):
        canvas.putpixel((960, y), (255, 255, 255))

    effect = EffectInstruction(
        effect_id="eff_shake",
        effect_type=EffectType.IMPACT_SHAKE,
        start_time=1.0,
        end_time=2.0,
        intensity=1.0,
        parameters={"amplitude_px": 20.0, "frequency_hz": 24.0},
    )

    # At start + 0.01s (non-zero sinusoidal offset)
    shaken = renderer.apply_effects(canvas, [effect], timestamp_sec=1.01, target_w=1920, target_h=1080)
    arr_orig = np.array(canvas)
    arr_shaken = np.array(shaken)

    # Pixel diff should be non-zero due to horizontal/vertical shift
    assert np.abs(arr_orig.astype(float) - arr_shaken.astype(float)).sum() > 0


def test_effect_flash():
    renderer = EffectRenderer()
    canvas = Image.new("RGB", (1920, 1080), color=(50, 50, 50))

    effect = EffectInstruction(
        effect_id="eff_flash",
        effect_type=EffectType.FLASH,
        start_time=1.0,
        end_time=2.0,
        intensity=0.8,
    )

    # At start of flash (t=1.05s)
    flashed = renderer.apply_effects(canvas, [effect], timestamp_sec=1.05, target_w=1920, target_h=1080)

    stat_orig = ImageStat.Stat(canvas)
    stat_flash = ImageStat.Stat(flashed)

    # Luminance should increase substantially during flash
    assert stat_flash.mean[0] > stat_orig.mean[0] + 50.0


def test_effect_vignette():
    renderer = EffectRenderer()
    canvas = Image.new("RGB", (1920, 1080), color=(180, 180, 180))

    effect = EffectInstruction(
        effect_id="eff_vignette",
        effect_type=EffectType.VIGNETTE,
        start_time=0.0,
        end_time=3.0,
        intensity=0.7,
    )

    vignetted = renderer.apply_effects(canvas, [effect], timestamp_sec=1.0, target_w=1920, target_h=1080)
    arr = np.array(vignetted)

    # Center pixel luminance should be higher than corner pixel luminance
    center_lum = arr[540, 960, 0]
    corner_lum = arr[10, 10, 0]
    assert corner_lum < center_lum
