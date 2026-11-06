"""Unit tests for Phase 5 Milestone M1: Orthographic Turnaround Sheets & Rigging Specifications.

Tests structured models, resolution bucketing, Danbooru tag and natural language prompt compilers,
negative prompt constraints, turnaround sheet slicing, and ComfyRunner/offline generation coordination.
"""
from __future__ import annotations

import io
from pathlib import Path
import cv2
import numpy as np
from PIL import Image

import pytest

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.original import art
from engine.original import shotspec as ss
from engine.original.models import Bible, Character, OriginalStory, Premise
from engine.motion.models.enums import LayerType
from engine.motion.models.layers import LayerInstruction, ParallaxPlan
from engine.original.rigging import (
    RIGGING_NEGATIVE,
    DecomposedLayer,
    LayerStack,
    MattingResult,
    RiggingSpec,
    TurnaroundSheet,
    compile_rigging_view_prompt,
    compile_turnaround_prompt,
    decompose_layers,
    defringe_alpha,
    extract_subject_and_prop_masks,
    generate_rigging_views,
    generate_turnaround_sheet,
    guided_filter_alpha,
    inpaint_background_plate,
    remove_background,
    slice_turnaround_sheet,
)


def sample_story(genre: str = "bedtime") -> OriginalStory:
    bible = Bible(
        premise=Premise(title="Starfarer", genre=genre, logline="L", tone="T", setting="S"),
        characters=[
            Character(
                id="lyra",
                name="Lyra",
                role="protagonist",
                age_group="teen",
                gender="female",
                look="silver hair, braided ponytail, mechanical cybernetic arm, teal flight suit",
                personality="determined and curious",
            ),
            Character(
                id="orion",
                name="Orion",
                role="companion",
                age_group="adult",
                gender="male",
                look="short dark hair, trench coat, utility belt, combat boots",
                personality="stoic protector",
            ),
        ],
        locations=[],
    )
    return OriginalStory(bible=bible, scenes=[], panels=[])


class FakeRunner:
    """Deterministic mock ComfyRunner for CI/offline testing."""

    def __init__(self, style: str = "tags"):
        self.style = style
        self.calls: list[dict] = []

    def generate(self, pos: str, neg: str, seed: int, width: int, height: int, prefix: str, **kwargs) -> bytes:
        self.calls.append({
            "pos": pos,
            "neg": neg,
            "seed": seed,
            "width": width,
            "height": height,
            "prefix": prefix,
            "kwargs": kwargs,
        })
        # Produce a valid test turnaround canvas with 4 distinct horizontal regions
        img = Image.new("RGB", (width, height), color=(200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def test_shotspec_rigging_defaults():
    """Verify ShotSpec backward compatibility with default rigging fields."""
    spec = ss.ShotSpec(shot="close")
    assert spec.rigging is None
    assert spec.is_rigging is False
    assert spec.rigging_pose == "a_pose"
    assert spec.turnaround_views == ["front", "three_quarter", "side", "back"]
    assert spec.orthographic is True
    assert spec.limb_separation is True


def test_shotspec_rigging_explicit_fields():
    """Verify ShotSpec serialization with explicit RiggingSpec and custom options."""
    rig_spec = RiggingSpec(
        pose="t_pose",
        views=["front", "side"],
        orthographic=True,
        limb_separation=True,
        visible_joints=True,
    )
    spec = ss.ShotSpec(
        shot="turnaround",
        is_rigging=True,
        rigging=rig_spec,
        rigging_pose="t_pose",
        turnaround_views=["front", "side"],
        orthographic=True,
        limb_separation=True,
    )
    data = spec.model_dump()
    assert data["is_rigging"] is True
    assert data["rigging_pose"] == "t_pose"
    assert data["turnaround_views"] == ["front", "side"]
    assert data["rigging"]["pose"] == "t_pose"


def test_resolve_dimensions_turnaround_and_rigging():
    """Verify resolution bucketing for turnaround and rigging shots."""
    # Turnaround widescreen bucket: 1536x768
    assert ss.resolve_dimensions("turnaround") == (1536, 768)
    assert ss.resolve_dimensions("turnaround_sheet") == (1536, 768)
    # Even if multiple characters are passed, turnaround remains 1536x768
    assert ss.resolve_dimensions("turnaround", num_characters=3) == (1536, 768)
    # Rigging portrait bucket: 832x1216
    assert ss.resolve_dimensions("rigging") == (832, 1216)
    assert ss.resolve_dimensions("rigging_view") == (832, 1216)


def test_compile_turnaround_prompt_tags_a_pose():
    """Verify Danbooru tag turnaround compilation for Animagine XL / SDXL with A-pose."""
    story = sample_story()
    char = story.bible.characters[0]
    spec = RiggingSpec(pose="a_pose")

    pos = compile_turnaround_prompt(char, story, spec=spec, style_kind="tags")
    assert isinstance(pos, str)

    # Core Danbooru tags specified in M1 requirements
    expected_tags = [
        "solo",
        "character sheet",
        "turnaround",
        "model sheet",
        "reference sheet",
        "multiple views",
        "front view",
        "side view",
        "back view",
        "a-pose",
        "orthographic",
        "visible joints",
        "limb separation",
        "simple background",
    ]
    for tag in expected_tags:
        assert tag in pos, f"Expected tag '{tag}' missing from prompt: {pos}"

    # Character-specific attributes
    assert "silver hair" in pos
    assert "mechanical cybernetic arm" in pos


def test_compile_turnaround_prompt_tags_t_pose():
    """Verify Danbooru tag turnaround compilation with T-pose."""
    story = sample_story()
    char = story.bible.characters[0]
    spec = RiggingSpec(pose="t_pose")

    pos = compile_turnaround_prompt(char, story, spec=spec, style_kind="tags")
    assert "t-pose" in pos
    assert "arms outstretched horizontally" in pos
    assert "clean limb separation" in pos


def test_compile_turnaround_prompt_natural_flux():
    """Verify natural language paragraph compilation for FLUX / Qwen sentence followers."""
    story = sample_story()
    char = story.bible.characters[0]
    spec = RiggingSpec(pose="a_pose")

    pos = compile_turnaround_prompt(char, story, spec=spec, style_kind="natural")
    assert isinstance(pos, str)
    assert "Professional 2D animation character turnaround model sheet" in pos
    assert "front view, three-quarter 3/4 view, side profile view, and back rear view" in pos
    assert "A-pose" in pos
    assert "limb separation" in pos
    assert "articulated" in pos
    assert "No text, no captions, no speech bubbles" in pos
    # No booru tags
    assert "masterpiece" not in pos
    assert "absurdres" not in pos


def test_compile_turnaround_prompt_with_negative_kwarg():
    """Verify returning positive and negative prompt tuple when requested."""
    story = sample_story()
    char = story.bible.characters[0]
    spec = RiggingSpec()

    pos, neg = compile_turnaround_prompt(char, story, spec=spec, style_kind="tags", return_negative=True)
    assert isinstance(pos, str)
    assert neg == RIGGING_NEGATIVE


def test_rigging_negative_prompt_rules():
    """Verify RIGGING_NEGATIVE suppresses defects and occlusion but permits turnaround sheets."""
    # Must suppress:
    assert "occluded limbs" in RIGGING_NEGATIVE
    assert "overlapping appendages" in RIGGING_NEGATIVE
    assert "crossed limbs" in RIGGING_NEGATIVE
    assert "hands in pockets" in RIGGING_NEGATIVE
    assert "foreshortening" in RIGGING_NEGATIVE
    assert "background clutter" in RIGGING_NEGATIVE

    # Must NOT suppress turnaround formats (unlike SHEET_NEGATIVE):
    assert "multiple views" not in RIGGING_NEGATIVE
    assert "split screen" not in RIGGING_NEGATIVE
    assert "collage" not in RIGGING_NEGATIVE
    assert "reference sheet" not in RIGGING_NEGATIVE


def test_compile_rigging_views_all_four():
    """Verify prompt compilation for each isolated orthographic rigging view."""
    story = sample_story()
    char = story.bible.characters[0]
    spec = RiggingSpec(pose="a_pose")

    views = ["front", "three_quarter", "side", "back"]
    for v in views:
        pos = compile_rigging_view_prompt(char, v, story, spec=spec, style_kind="tags")
        assert f"{v.replace('_', ' ')} view" in pos or (v == "three_quarter" and "three-quarter view" in pos)
        assert "orthographic" in pos
        assert "a-pose" in pos
        assert "limb separation" in pos


def test_compile_rigging_view_prompt_natural():
    """Verify natural language prompt compilation for a single rigging view."""
    story = sample_story()
    char = story.bible.characters[0]
    pos = compile_rigging_view_prompt(char, "front", story, style_kind="natural")
    assert "Professional 2D animation orthographic rigging reference" in pos
    assert "front view facing directly forward" in pos
    assert "A-pose" in pos


def test_slice_turnaround_sheet():
    """Verify horizontal slicing of a 4-view turnaround canvas into distinct view images."""
    w, h = 1536, 768
    img = Image.new("RGB", (w, h))
    # Fill each quadrant with a distinct test color
    # front: red, three_quarter: green, side: blue, back: yellow
    slice_w = w // 4
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    for i, col in enumerate(colors):
        sub = Image.new("RGB", (slice_w, h), color=col)
        img.paste(sub, (i * slice_w, 0))

    views = ["front", "three_quarter", "side", "back"]
    slices = slice_turnaround_sheet(img, views=views)

    assert set(slices.keys()) == {"front", "three_quarter", "side", "back"}
    for v in views:
        assert slices[v].size == (384, 768)

    # Verify colors match exactly (genuine verification of image manipulation)
    assert slices["front"].getpixel((10, 10)) == (255, 0, 0)
    assert slices["three_quarter"].getpixel((10, 10)) == (0, 255, 0)
    assert slices["side"].getpixel((10, 10)) == (0, 0, 255)
    assert slices["back"].getpixel((10, 10)) == (255, 255, 0)


def test_generate_turnaround_sheet_mock(tmp_path: Path):
    """Verify turnaround sheet generation and slicing with mock ComfyRunner."""
    story = sample_story()
    char = story.bible.characters[0]
    runner = FakeRunner()

    sheet = generate_turnaround_sheet(char, story, tmp_path, runner=runner)

    assert isinstance(sheet, TurnaroundSheet)
    assert sheet.character_id == char.id
    assert sheet.image_path is not None
    assert Path(sheet.image_path).exists()
    assert sheet.pose == "a_pose"
    assert sheet.orthographic is True

    # Check that runner was invoked with 1536x768
    assert len(runner.calls) == 1
    call = runner.calls[0]
    assert call["width"] == 1536
    assert call["height"] == 768
    assert call["neg"] == RIGGING_NEGATIVE

    # Check sliced views
    for v in ["front", "three_quarter", "side", "back"]:
        assert v in sheet.views
        assert Path(sheet.views[v]).exists()

    # Re-running reuses the cached turnaround file
    runner.calls.clear()
    sheet2 = generate_turnaround_sheet(char, story, tmp_path, runner=runner)
    assert len(runner.calls) == 0
    assert sheet2.image_path == sheet.image_path


def test_offline_turnaround_sheet_creation(tmp_path: Path):
    """Verify graceful offline fallback creates a valid orthographic turnaround sheet without ComfyUI."""
    story = sample_story()
    char = story.bible.characters[0]

    sheet = generate_turnaround_sheet(char, story, tmp_path, runner=None)
    assert Path(sheet.image_path).exists()

    with Image.open(sheet.image_path) as im:
        assert im.size == (1536, 768)

    # Verify all sliced view files exist and have dimensions 384x768
    for v in ["front", "three_quarter", "side", "back"]:
        p = Path(sheet.views[v])
        assert p.exists()
        with Image.open(p) as view_im:
            assert view_im.size == (384, 768)


def test_generate_rigging_views(tmp_path: Path):
    """Verify generate_rigging_views helper produces paths for all required views."""
    story = sample_story()
    char = story.bible.characters[0]

    views = generate_rigging_views(char, story, tmp_path, runner=None)
    assert set(views.keys()) == {"front", "three_quarter", "side", "back"}
    for v, p in views.items():
        assert isinstance(p, Path)
        assert p.exists()


def test_data_models_matting_and_layers():
    """Verify data models MattingResult, DecomposedLayer, LayerStack serialize and deserialize."""
    matting = MattingResult(
        rgba_bytes=b"\x89PNG\r\n\x1a\nfake_rgba",
        mask_bytes=b"\x89PNG\r\n\x1a\nfake_mask",
        has_alpha=True,
        halo_free=True,
        width=1024,
        height=1024,
    )
    assert matting.has_alpha is True
    assert matting.halo_free is True

    layer_fg = DecomposedLayer(
        name="character_subject",
        layer_type="foreground_subject",
        image_bytes=b"rgba_data",
        z_index=2,
        depth_estimate=0.8,
    )
    layer_bg = DecomposedLayer(
        name="background_plate",
        layer_type="background_plate",
        image_bytes=b"rgb_data",
        z_index=0,
        depth_estimate=0.1,
    )
    stack = LayerStack(
        panel_id="panel_001",
        width=1344,
        height=768,
        layers=[layer_bg, layer_fg],
    )
    dumped = stack.model_dump()
    assert dumped["panel_id"] == "panel_001"
    assert len(dumped["layers"]) == 2
    assert dumped["layers"][1]["name"] == "character_subject"


def test_art_module_exports():
    """Verify art.py exports all rigging models and utilities for downstream callers."""
    assert hasattr(art, "RIGGING_NEGATIVE")
    assert hasattr(art, "compile_turnaround_prompt")
    assert hasattr(art, "compile_rigging_view_prompt")
    assert hasattr(art, "generate_turnaround_sheet")
    assert hasattr(art, "generate_rigging_views")
    assert hasattr(art, "slice_turnaround_sheet")
    assert hasattr(art, "RiggingSpec")
    assert hasattr(art, "TurnaroundSheet")
    assert hasattr(art, "MattingResult")
    assert hasattr(art, "remove_background")
    assert hasattr(art, "defringe_alpha")
    assert hasattr(art, "guided_filter_alpha")
    assert hasattr(art, "extract_subject_and_prop_masks")
    assert art.RIGGING_NEGATIVE == RIGGING_NEGATIVE


def test_workflow_registry_anime_alpha_matting():
    """Verify anime_alpha_matting is registered, SHA256 verified, and passes patch slot validation."""
    reg = ComfyWorkflowRegistry()
    assert "anime_alpha_matting" in reg._entries

    entry = reg.metadata("anime_alpha_matting")
    assert entry["id"] == "anime_alpha_matting"
    assert entry["purpose"] == "matting"
    assert entry["filename"] == "anime_alpha_matting.api.json"
    assert "birefnet-general.safetensors" in entry["model_files"]

    # Verify required patch slots
    slots = entry["patch_slots"]
    for req in ("prompt", "negative_prompt", "seed", "filename_prefix", "reference_image"):
        assert req in slots, f"Missing required patch slot: {req}"

    # Load workflow and verify node mapping
    wf, checksum = reg.load("anime_alpha_matting")
    assert checksum == entry["sha256"]
    assert len(wf) == 8

    # Preflight without live model should report missing models cleanly
    pre = reg.preflight("anime_alpha_matting")
    assert pre["workflow_id"] == "anime_alpha_matting"
    assert pre["node_count"] == 8
    # When birefnet is not installed on disk, ready is False but missing_nodes is empty
    assert isinstance(pre["ready"], bool)
    assert isinstance(pre["missing_models"], list)


def test_client_discover_models_background_removal():
    """Verify discover_models in client.py includes background_removal category."""
    client = ComfyUIClient()
    models = client.discover_models()
    assert isinstance(models, dict)
    # The method definition in client.py includes background_removal in its category loop
    import inspect
    src = inspect.getsource(client.discover_models)
    assert "background_removal" in src


def test_guided_filter_matting_edge_smoothing():
    """Verify He et al. Guided Filter smooths binary/coarse alpha edges while preserving guide contours."""
    h, w = 40, 40
    # Guide image with a vertical edge at x=20
    guide = np.zeros((h, w, 3), dtype=np.uint8)
    guide[:, 20:] = 240

    # Coarse stepped alpha mask with an imperfect boundary
    alpha = np.zeros((h, w), dtype=np.uint8)
    alpha[:, 20:] = 255
    # Artificial staircasing / noise at edge
    alpha[5:10, 19] = 255
    alpha[15:20, 20] = 0

    refined = guided_filter_alpha(guide, alpha, radius=3, eps=1e-4)

    assert refined.shape == (h, w)
    assert refined.dtype == np.uint8
    # Interior regions remain consistent
    assert refined[20, 5] < 10
    assert refined[20, 35] > 240
    # Along the boundary x=19..21, intermediate values exist (anti-aliased edge)
    boundary_col = refined[:, 20]
    assert np.any((boundary_col > 10) & (boundary_col < 250))


def test_defringe_alpha_color_decontamination():
    """Verify morphological color decontamination eliminates white fringe and halos."""
    h, w = 30, 30
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)  # White background
    alpha = np.zeros((h, w), dtype=np.uint8)

    # Solid blue character in center: RGB (20, 30, 200), Alpha 255
    rgb[10:20, 10:20] = [20, 30, 200]
    alpha[10:20, 10:20] = 255

    # Boundary pixels contaminated with white background blend (fringe):
    # RGB is light blue (140, 150, 230) and Alpha is semi-transparent 128
    rgb[9, 10:20] = [140, 150, 230]
    alpha[9, 10:20] = 128
    rgb[20, 10:20] = [140, 150, 230]
    alpha[20, 10:20] = 128

    decontam_rgb, out_alpha = defringe_alpha(rgb, alpha, threshold=240)

    # Solid interior is completely preserved
    np.testing.assert_array_equal(decontam_rgb[15, 15], [20, 30, 200])
    # Contaminated boundary pixels now contain solid foreground color (zero white fringe!)
    for x in range(10, 20):
        np.testing.assert_array_equal(decontam_rgb[9, x], [20, 30, 200])
        np.testing.assert_array_equal(decontam_rgb[20, x], [20, 30, 200])
    # Alpha mask is preserved
    assert out_alpha[9, 15] == 128
    assert out_alpha[15, 15] == 255


def test_defringe_alpha_edge_cases():
    """Verify defringe_alpha gracefully handles edge cases without crashing."""
    # All zero alpha
    rgb_zero = np.zeros((10, 10, 3), dtype=np.uint8)
    alpha_zero = np.zeros((10, 10), dtype=np.uint8)
    r1, a1 = defringe_alpha(rgb_zero, alpha_zero)
    assert r1.shape == rgb_zero.shape
    assert a1.shape == alpha_zero.shape

    # All solid alpha
    rgb_solid = np.full((10, 10, 3), 100, dtype=np.uint8)
    alpha_solid = np.full((10, 10), 255, dtype=np.uint8)
    r2, a2 = defringe_alpha(rgb_solid, alpha_solid)
    np.testing.assert_array_equal(r2, rgb_solid)

    # 4-channel input array
    rgba_4ch = np.zeros((10, 10, 4), dtype=np.uint8)
    rgba_4ch[3:7, 3:7] = [50, 60, 70, 255]
    r3, a3 = defringe_alpha(rgba_4ch, rgba_4ch[:, :, 3])
    assert r3.shape == (10, 10, 3)
    assert a3.shape == (10, 10)


def test_remove_background_produces_transparent_rgba_png():
    """Verify remove_background outputs valid 4-channel transparent RGBA PNG with halo-free guarantee."""
    # Synthetic character on neutral gray studio background
    w, h = 120, 160
    img = Image.new("RGB", (w, h), color=(180, 180, 180))
    # Draw character head and body
    draw_np = np.array(img)
    cv2.circle(draw_np, (60, 40), 20, (50, 60, 80), -1)
    cv2.rectangle(draw_np, (45, 60), (75, 130), (60, 70, 95), -1)
    test_img = Image.fromarray(draw_np)

    result = remove_background(test_img, runner=None, defringe=True)

    assert isinstance(result, MattingResult)
    assert result.has_alpha is True
    assert result.halo_free is True
    assert result.width == w
    assert result.height == h

    # Verify RGBA PNG bytes
    rgba_img = result.to_image()
    assert rgba_img.size == (w, h)
    assert rgba_img.mode == "RGBA"

    rgba_arr = np.array(rgba_img)
    alpha_ch = rgba_arr[:, :, 3]

    # Background corners should be transparent
    assert alpha_ch[5, 5] < 30
    assert alpha_ch[5, w - 5] < 30
    # Character center should be opaque
    assert alpha_ch[40, 60] > 200
    assert alpha_ch[90, 60] > 200

    # Verify mask image
    mask_img = result.to_mask_image()
    assert mask_img.size == (w, h)
    assert mask_img.mode == "L"


def test_remove_background_with_existing_alpha():
    """Verify remove_background refines pre-existing transparent RGBA images cleanly."""
    w, h = 60, 60
    rgba = np.full((h, w, 4), 255, dtype=np.uint8)
    rgba[:, :, 3] = 0  # fully transparent background
    rgba[15:45, 15:45, :3] = [200, 50, 50]
    rgba[15:45, 15:45, 3] = 255  # solid red box

    pil_rgba = Image.fromarray(rgba, "RGBA")
    res = remove_background(pil_rgba, runner=None, defringe=True)

    assert res.has_alpha is True
    out_arr = np.array(res.to_image())
    assert out_arr.shape == (h, w, 4)
    # Outside transparent
    assert out_arr[5, 5, 3] == 0
    # Inside red and opaque
    assert out_arr[30, 30, 3] > 240
    np.testing.assert_array_equal(out_arr[30, 30, :3], [200, 50, 50])


def test_remove_background_accepts_bytes_and_path(tmp_path: Path):
    """Verify remove_background accepts bytes, file Path, and string paths."""
    w, h = 80, 80
    img = Image.new("RGB", (w, h), (180, 180, 180))
    img_np = np.array(img)
    cv2.circle(img_np, (40, 40), 18, (40, 50, 60), -1)
    test_img = Image.fromarray(img_np)

    # Save to disk
    img_file = tmp_path / "char_test.png"
    test_img.save(img_file, format="PNG")
    raw_bytes = img_file.read_bytes()

    # Pass Path
    res1 = remove_background(img_file)
    assert res1.width == w and res1.height == h
    assert res1.has_alpha is True

    # Pass bytes
    res2 = remove_background(raw_bytes)
    assert res2.width == w and res2.height == h
    assert res2.has_alpha is True

    # Pass str
    res3 = remove_background(str(img_file))
    assert res3.width == w and res3.height == h
    assert res3.has_alpha is True


def test_extract_subject_and_prop_masks():
    """Verify automated mask extraction separates primary subject, interactive props, and background plate."""
    w, h = 200, 150
    base = np.full((h, w, 3), 180, dtype=np.uint8)  # Studio background

    # Primary Character Subject (large ellipse in center-left)
    cv2.ellipse(base, (70, 75), (35, 55), 0, 0, 360, (50, 60, 80), -1)

    # Detached Prop (sword / floating orb in upper-right)
    cv2.circle(base, (160, 45), 18, (180, 50, 50), -1)

    masks = extract_subject_and_prop_masks(Image.fromarray(base))

    assert "subject" in masks
    assert "prop" in masks
    assert "background" in masks
    assert "foreground" in masks

    for name, mask_im in masks.items():
        assert isinstance(mask_im, Image.Image)
        assert mask_im.mode == "L"
        assert mask_im.size == (w, h)

    subj_np = np.array(masks["subject"])
    prop_np = np.array(masks["prop"])
    bg_np = np.array(masks["background"])

    # Subject is active in the character region
    assert subj_np[75, 70] > 128
    assert prop_np[75, 70] == 0

    # Prop is active in the prop region
    assert prop_np[45, 160] > 128
    assert subj_np[45, 160] == 0

    # Background is active at the corners
    assert bg_np[10, 10] > 200
    assert subj_np[10, 10] == 0
    assert prop_np[10, 10] == 0

    # Subject and prop do not overlap
    overlap = np.bitwise_and(subj_np > 50, prop_np > 50)
    assert np.count_nonzero(overlap) == 0


def test_extract_subject_and_prop_masks_no_prop():
    """Verify mask extraction when scene has a subject but no separate prop."""
    w, h = 100, 100
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    cv2.circle(base, (50, 50), 25, (40, 50, 60), -1)

    masks = extract_subject_and_prop_masks(Image.fromarray(base))
    assert isinstance(masks["subject"], Image.Image)
    assert isinstance(masks["prop"], Image.Image)
    assert isinstance(masks["background"], Image.Image)

    prop_np = np.array(masks["prop"])
    # Prop mask should be empty (all 0s)
    assert np.count_nonzero(prop_np) == 0
    # Subject mask has pixels
    subj_np = np.array(masks["subject"])
    assert np.count_nonzero(subj_np) > 0


def test_comfy_runner_remove_background_offline_fallback():
    """Verify ComfyRunner falls back cleanly to local matting engine when offline."""
    w, h = 64, 64
    img = Image.new("RGB", (w, h), (180, 180, 180))
    img_np = np.array(img)
    cv2.circle(img_np, (32, 32), 16, (40, 50, 60), -1)
    test_img = Image.fromarray(img_np)

    # Fake runner with matting_wf = None
    runner = FakeRunner()
    runner.matting_wf = None

    # Call rigging.remove_background with runner
    res = remove_background(test_img, runner=runner, defringe=True)
    assert isinstance(res, MattingResult)
    assert res.has_alpha is True
    assert res.width == w
    assert res.height == h


def test_comfy_runner_remove_background_mocked_workflow(monkeypatch):
    """Verify ComfyRunner.remove_background invokes workflow when ready and defringes output."""
    w, h = 60, 60
    # Pre-generate synthetic RGBA PNG returned by mock ComfyUI
    rgba = np.full((h, w, 4), 255, dtype=np.uint8)
    rgba[:20, :, 3] = 0
    raw_pil = Image.fromarray(rgba, "RGBA")
    buf = io.BytesIO()
    raw_pil.save(buf, format="PNG")
    mock_png_bytes = buf.getvalue()

    class MockComfyClient:
        base_url = "http://127.0.0.1:8188/"
        def submit_prompt(self, wf):
            return "mock_prompt_123"
        def history(self, pid):
            return {pid: {"outputs": {"5": {"images": [{"filename": "out.png", "subfolder": "", "type": "output"}]}}}}
        def download_output(self, filename, subfolder, kind):
            return mock_png_bytes

    class MockRunner:
        def __init__(self):
            self.client = MockComfyClient()
            reg = ComfyWorkflowRegistry()
            self.matting_wf = (reg.load("anime_alpha_matting")[0], reg.metadata("anime_alpha_matting"))
        def _resolve_upload(self, item):
            return "uploaded_input.png"

    # Attach remove_background method to MockRunner
    mock_runner = MockRunner()
    mock_runner.remove_background = art.ComfyRunner.remove_background.__get__(mock_runner, MockRunner)

    result_bytes = mock_runner.remove_background(raw_pil, defringe=True)
    assert isinstance(result_bytes, bytes)
    out_im = Image.open(io.BytesIO(result_bytes))
    assert out_im.mode == "RGBA"
    assert out_im.size == (w, h)


def test_inpaint_background_plate_offline_telea():
    """Verify inpaint_background_plate infills occluded regions without alpha holes using local OpenCV Telea."""
    w, h = 80, 80
    # Green background (50, 180, 50)
    base = np.full((h, w, 3), [50, 180, 50], dtype=np.uint8)
    # Red character circle at center (40, 40) with radius 14
    cv2.circle(base, (40, 40), 14, (200, 30, 30), -1)
    base_img = Image.fromarray(base)

    # Occlusion mask: 255 on character circle, 0 on background
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (40, 40), 14, 255, -1)
    mask_img = Image.fromarray(mask, "L")

    infilled = inpaint_background_plate(base_img, mask_img, runner=None, dilation_px=12)

    assert isinstance(infilled, Image.Image)
    assert infilled.size == (w, h)
    assert infilled.mode == "RGB"

    infilled_np = np.array(infilled)
    # The formerly red center (40, 40) is now infilled with green
    center_pixel = infilled_np[40, 40]
    assert center_pixel[0] < 120
    assert center_pixel[1] > 100

    # Corners remain the original background color
    np.testing.assert_array_equal(infilled_np[5, 5], [50, 180, 50])
    np.testing.assert_array_equal(infilled_np[75, 75], [50, 180, 50])


def test_inpaint_background_plate_dilation_eliminates_boundary_halo():
    """Verify +12px dilation covers edge fringe and halo surrounding the occlusion hole."""
    w, h = 100, 100
    base = np.full((h, w, 3), [60, 160, 60], dtype=np.uint8)  # Green background
    # White edge halo at radius 15..20
    cv2.circle(base, (50, 50), 20, (250, 250, 250), -1)
    # Inner subject at radius <= 14
    cv2.circle(base, (50, 50), 14, (30, 30, 200), -1)
    base_img = Image.fromarray(base)

    # Mask only covers the inner subject (radius 14), NOT the white halo
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, (50, 50), 14, 255, -1)
    mask_img = Image.fromarray(mask, "L")

    # With dilation_px=12, the inpaint mask expands to radius ~26, subsuming the halo
    infilled_dilated = inpaint_background_plate(base_img, mask_img, runner=None, dilation_px=12)
    infilled_np = np.array(infilled_dilated)

    # Pixel at (50, 68), which was radius 18 inside the white halo [250, 250, 250]
    halo_pixel = infilled_np[68, 50]
    assert halo_pixel[0] < 180 and halo_pixel[1] > 90

    # Without dilation (dilation_px=0), the halo at radius 18 would remain white
    infilled_no_dil = inpaint_background_plate(base_img, mask_img, runner=None, dilation_px=0)
    no_dil_np = np.array(infilled_no_dil)
    np.testing.assert_array_equal(no_dil_np[68, 50], [250, 250, 250])


def test_inpaint_background_plate_mock_runner():
    """Verify inpaint_background_plate coordinates with runner.inpaint when available."""
    w, h = 64, 64
    base_img = Image.new("RGB", (w, h), (100, 100, 100))
    mask_img = Image.new("L", (w, h), 0)
    draw_np = np.array(mask_img)
    draw_np[20:40, 20:40] = 255
    mask_img = Image.fromarray(draw_np, "L")

    class MockInpaintRunner:
        def __init__(self):
            self.calls = []
        def inpaint(self, base_image, mask_image, prompt, neg, seed, **kwargs):
            self.calls.append({"prompt": prompt, "seed": seed})
            out = Image.new("RGB", (w, h), (30, 70, 190))
            buf = io.BytesIO()
            out.save(buf, format="PNG")
            return buf.getvalue()

    runner = MockInpaintRunner()
    res = inpaint_background_plate(base_img, mask_img, runner=runner, dilation_px=6, prompt_hint="serene forest")

    assert len(runner.calls) == 1
    assert "serene forest" in runner.calls[0]["prompt"]
    assert res.size == (w, h)
    assert res.getpixel((30, 30)) == (30, 70, 190)


def test_decompose_layers_three_planes():
    """Verify decompose_layers segments character subject, prop, and infilled background plate."""
    w, h = 200, 150
    base = np.full((h, w, 3), 180, dtype=np.uint8)  # Studio background

    # Primary Character Subject (center-left)
    cv2.ellipse(base, (70, 75), (35, 55), 0, 0, 360, (50, 60, 80), -1)

    # Detached Prop (sword/orb in upper-right)
    cv2.circle(base, (160, 45), 18, (180, 50, 50), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="panel_test_01")

    assert isinstance(stack, LayerStack)
    assert stack.panel_id == "panel_test_01"
    assert stack.width == w
    assert stack.height == h
    assert len(stack.layers) == 3

    # Layer ordering by z_index
    assert stack.layers[0].name == "background_plate"
    assert stack.layers[0].layer_type == "background_plate"
    assert stack.layers[0].z_index == 0
    assert stack.layers[0].depth_estimate == 0.1

    assert stack.layers[1].name == "prop_1"
    assert stack.layers[1].layer_type == "prop"
    assert stack.layers[1].z_index == 15
    assert stack.layers[1].depth_estimate == 0.6

    assert stack.layers[2].name == "foreground_subject"
    assert stack.layers[2].layer_type == "foreground_subject"
    assert stack.layers[2].z_index == 20
    assert stack.layers[2].depth_estimate == 0.8

    # Check convenience accessors
    assert stack.background == stack.layers[0]
    assert stack.get_layer("background_plate") == stack.layers[0]
    assert stack.get_layer("prop_1") == stack.layers[1]
    assert stack.foreground_subject == stack.layers[2]
    assert len(stack.props) == 1
    assert stack.props[0] == stack.layers[1]

    # Verify layer image decodings
    bg_img = stack.background.to_image()
    assert bg_img.size == (w, h)
    assert bg_img.mode == "RGB"

    subj_img = stack.foreground_subject.to_image()
    assert subj_img.size == (w, h)
    assert subj_img.mode == "RGBA"
    subj_np = np.array(subj_img)
    assert subj_np[75, 70, 3] > 180
    assert subj_np[45, 160, 3] == 0

    prop_img = stack.props[0].to_image()
    assert prop_img.size == (w, h)
    assert prop_img.mode == "RGBA"
    prop_np = np.array(prop_img)
    assert prop_np[45, 160, 3] > 180
    assert prop_np[75, 70, 3] == 0

    subj_mask = stack.foreground_subject.to_mask_image()
    assert subj_mask is not None
    assert subj_mask.mode == "L"


def test_decompose_layers_two_planes_no_prop():
    """Verify decompose_layers creates 2 planes when no distinct prop is detected."""
    w, h = 100, 100
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    cv2.circle(base, (50, 50), 25, (40, 50, 60), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="panel_no_prop")
    assert len(stack.layers) == 2
    assert stack.background is not None
    assert stack.foreground_subject is not None
    assert stack.props == []
    assert stack.get_layer("prop_1") is None


def test_layer_stack_to_parallax_plan_integration():
    """Verify LayerStack.to_parallax_plan bridges directly to ParallaxPlan and LayerInstruction models."""
    w, h = 120, 90
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    cv2.ellipse(base, (45, 45), (20, 30), 0, 0, 360, (50, 60, 80), -1)
    cv2.circle(base, (95, 30), 10, (180, 50, 50), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="panel_parallax_test")
    plan = stack.to_parallax_plan()

    assert isinstance(plan, ParallaxPlan)
    assert plan.enabled is True
    assert plan.fallback_flat is False
    assert plan.max_parallax_offset == 0.08
    assert len(plan.layers) == 3

    bg_inst = plan.layers[0]
    assert isinstance(bg_inst, LayerInstruction)
    assert bg_inst.layer_type == LayerType.BACKGROUND
    assert bg_inst.depth == 0.1
    assert bg_inst.motion_factor == 0.6
    assert "panel_parallax_test" in (bg_inst.source_uri or "")

    prop_inst = plan.layers[1]
    assert isinstance(prop_inst, LayerInstruction)
    assert prop_inst.layer_type == LayerType.FOREGROUND
    assert prop_inst.depth == 0.6
    assert prop_inst.motion_factor == 1.1

    subj_inst = plan.layers[2]
    assert isinstance(subj_inst, LayerInstruction)
    assert subj_inst.layer_type == LayerType.CHARACTER
    assert subj_inst.depth == 0.8
    assert subj_inst.motion_factor == 1.0


def test_layer_stack_to_parallax_plan_custom_depths():
    """Verify to_parallax_plan applies caller-specified depth mappings."""
    w, h = 80, 80
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    cv2.circle(base, (40, 40), 16, (40, 50, 60), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="panel_custom_depths")
    custom_depths = {
        "background_plate": -0.65,
        "foreground_subject": 0.25,
    }
    plan = stack.to_parallax_plan(default_depths=custom_depths)

    assert plan.layers[0].depth == -0.65
    assert plan.layers[1].depth == 0.25


def test_layer_stack_to_parallax_plan_fallback_dict(monkeypatch):
    """Verify graceful fallback to dictionary when engine.motion is not importable."""
    w, h = 60, 60
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    cv2.circle(base, (30, 30), 12, (40, 50, 60), -1)
    stack = decompose_layers(Image.fromarray(base), panel_id="panel_dict_fallback")

    import builtins
    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "engine.motion" in name:
            raise ImportError(f"Simulated missing {name}")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    raw_plan = stack.to_parallax_plan()
    assert isinstance(raw_plan, dict)
    assert raw_plan["enabled"] is True
    assert raw_plan["fallback_flat"] is False
    assert "layers" in raw_plan
    assert len(raw_plan["layers"]) == 2
    assert raw_plan["layers"][0]["layer_type"] == "BACKGROUND"
    assert raw_plan["layers"][1]["layer_type"] == "CHARACTER"


def test_art_module_m3_exports():
    """Verify art module exports decompose_layers, inpaint_background_plate, DecomposedLayer, LayerStack."""
    assert hasattr(art, "decompose_layers")
    assert hasattr(art, "inpaint_background_plate")
    assert hasattr(art, "DecomposedLayer")
    assert hasattr(art, "LayerStack")
    assert art.decompose_layers is decompose_layers
    assert art.inpaint_background_plate is inpaint_background_plate
    assert art.DecomposedLayer is DecomposedLayer
    assert art.LayerStack is LayerStack

    assert hasattr(art.ComfyRunner, "decompose_layers")
    assert hasattr(art.ComfyRunner, "inpaint_background_plate")


def test_decompose_layers_bytes_and_path_input(tmp_path: Path):
    """Verify decompose_layers accepts file Path, string paths, and raw PNG bytes."""
    w, h = 60, 60
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    cv2.circle(base, (30, 30), 12, (40, 50, 60), -1)
    img = Image.fromarray(base)

    img_file = tmp_path / "panel_input.png"
    img.save(img_file, format="PNG")
    raw_bytes = img_file.read_bytes()

    stack_path = decompose_layers(img_file, panel_id="p_path")
    assert stack_path.panel_id == "p_path"
    assert len(stack_path.layers) >= 2

    stack_str = decompose_layers(str(img_file), panel_id="p_str")
    assert stack_str.panel_id == "p_str"
    assert len(stack_str.layers) >= 2

    stack_bytes = decompose_layers(raw_bytes, panel_id="p_bytes")
    assert stack_bytes.panel_id == "p_bytes"
    assert len(stack_bytes.layers) >= 2


# ==============================================================================
# Milestone M4: Comprehensive Acceptance Criteria Test Matrix & Polish
# ==============================================================================

def test_m4_multi_prop_extraction_individual_masks():
    """Verify extract_subject_and_prop_masks extracts individual masks for each discrete prop."""
    w, h = 400, 300
    base = np.full((h, w, 3), 180, dtype=np.uint8)  # Studio background

    # 1. Primary character subject (center, area ~12500 px)
    cv2.ellipse(base, (200, 150), (45, 75), 0, 0, 360, (50, 60, 80), -1)

    # 2. Prop A: floating orb (top-left, area ~1250 px)
    cv2.circle(base, (70, 70), 20, (200, 40, 40), -1)

    # 3. Prop B: treasure chest (bottom-right, area ~3600 px)
    cv2.rectangle(base, (310, 200), (370, 260), (40, 180, 50), -1)

    # 4. Prop C: dagger (top-right, area ~1200 px)
    cv2.rectangle(base, (320, 50), (340, 110), (180, 180, 30), -1)

    im = Image.fromarray(base)
    masks = extract_subject_and_prop_masks(im)

    # Verify standard contract keys
    assert "subject" in masks
    assert "prop" in masks
    assert "background" in masks
    assert "foreground" in masks

    # Verify multi-prop individual masks and props list
    assert hasattr(masks, "props")
    assert len(masks.props) == 3
    assert "prop_1" in masks
    assert "prop_2" in masks
    assert "prop_3" in masks

    # Verify all items in masks.items() are valid PIL Images in mode 'L'
    for k, v in masks.items():
        assert isinstance(v, Image.Image), f"Mask key '{k}' must be PIL Image"
        assert v.mode == "L"
        assert v.size == (w, h)

    # Verify pixel exclusivity across props
    # The connected components are sorted descending by area:
    # Chest (~3600 px) -> prop_1, Orb (~1250 px) -> prop_2, Dagger (~1200 px) -> prop_3
    p1_arr = np.array(masks["prop_1"])
    p2_arr = np.array(masks["prop_2"])
    p3_arr = np.array(masks["prop_3"])
    subj_arr = np.array(masks["subject"])

    # No character pixels in any prop
    assert p1_arr[150, 200] == 0
    assert p2_arr[150, 200] == 0
    assert p3_arr[150, 200] == 0
    assert subj_arr[150, 200] > 180

    # Verify each discrete prop is isolated into exactly one prop mask
    # Chest location (340, 230), Orb location (70, 70), Dagger location (330, 80)
    all_prop_masks = [p1_arr, p2_arr, p3_arr]
    chest_hits = [p[230, 340] > 180 for p in all_prop_masks]
    orb_hits = [p[70, 70] > 180 for p in all_prop_masks]
    dagger_hits = [p[80, 330] > 180 for p in all_prop_masks]

    assert sum(chest_hits) == 1, "Chest must be in exactly one prop mask"
    assert sum(orb_hits) == 1, "Orb must be in exactly one prop mask"
    assert sum(dagger_hits) == 1, "Dagger must be in exactly one prop mask"
    assert chest_hits != orb_hits, "Chest and orb must be in different prop masks"
    assert chest_hits != dagger_hits, "Chest and dagger must be in different prop masks"
    assert orb_hits != dagger_hits, "Orb and dagger must be in different prop masks"

    # Combined prop mask contains all three
    prop_comb = np.array(masks["prop"])
    assert prop_comb[230, 340] > 180
    assert prop_comb[70, 70] > 180
    assert prop_comb[80, 330] > 180


def test_m4_multi_prop_layer_decomposition_isolated_planes():
    """Verify decompose_layers with isolate_props=True produces discrete prop planes."""
    w, h = 400, 300
    base = np.full((h, w, 3), 180, dtype=np.uint8)

    # Character + 3 Props
    cv2.ellipse(base, (200, 150), (45, 75), 0, 0, 360, (50, 60, 80), -1)
    cv2.circle(base, (70, 70), 20, (200, 40, 40), -1)
    cv2.rectangle(base, (310, 200), (370, 260), (40, 180, 50), -1)
    cv2.rectangle(base, (320, 50), (340, 110), (180, 180, 30), -1)

    im = Image.fromarray(base)
    stack = decompose_layers(im, panel_id="multi_iso_panel", isolate_props=True)

    assert isinstance(stack, LayerStack)
    assert len(stack.layers) == 5  # 1 background + 3 props + 1 character
    assert len(stack.props) == 3

    # Layer ordering by z_index
    assert stack.layers[0].name == "background_plate"
    assert stack.layers[0].z_index == 0
    assert stack.layers[0].depth_estimate == 0.1

    assert stack.layers[1].name == "prop_1"
    assert stack.layers[2].name == "prop_2"
    assert stack.layers[3].name == "prop_3"

    assert stack.layers[4].name == "foreground_subject"
    assert stack.layers[4].z_index == 20
    assert stack.layers[4].depth_estimate == 0.8

    # Verify distinct z_indices and depth estimates for all props
    prop_z_indices = [p.z_index for p in stack.props]
    prop_depths = [p.depth_estimate for p in stack.props]

    assert len(set(prop_z_indices)) == 3, "Each prop must have a distinct z_index"
    assert len(set(prop_depths)) == 3, "Each prop must have a distinct depth_estimate"
    assert all(0 < z < 20 for z in prop_z_indices), "Props must be between background (0) and subject (20)"
    assert all(0.1 < d < 0.8 for d in prop_depths), "Props must be between background (0.1) and subject (0.8)"

    # Check convenience getters
    assert stack.get_layer("prop_1") == stack.props[0]
    assert stack.get_layer("prop_2") == stack.props[1]
    assert stack.get_layer("prop_3") == stack.props[2]
    assert stack.get_layer("prop") == stack.props[0]  # Fallback for single-prop callers
    assert stack.prop == stack.props[0]

    # Verify transparent RGBA decodings
    for prop_lay in stack.props:
        p_img = prop_lay.to_image()
        assert p_img.mode == "RGBA"
        assert p_img.size == (w, h)
        p_mask = prop_lay.to_mask_image()
        assert p_mask is not None
        assert p_mask.mode == "L"

    # Background plate must be opaque RGB without alpha holes
    bg_img = stack.background.to_image()
    assert bg_img.mode == "RGB"
    assert bg_img.size == (w, h)


def test_m4_multi_prop_to_parallax_plan_distinct_speed_scales():
    """Verify to_parallax_plan assigns distinct depths and speed scales (motion_factor) to discrete props."""
    w, h = 400, 300
    base = np.full((h, w, 3), 180, dtype=np.uint8)

    cv2.ellipse(base, (200, 150), (45, 75), 0, 0, 360, (50, 60, 80), -1)
    cv2.circle(base, (70, 70), 20, (200, 40, 40), -1)
    cv2.rectangle(base, (310, 200), (370, 260), (40, 180, 50), -1)
    cv2.rectangle(base, (320, 50), (340, 110), (180, 180, 30), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="multi_parallax_panel", isolate_props=True)
    plan = stack.to_parallax_plan()

    assert isinstance(plan, ParallaxPlan)
    assert plan.enabled is True
    assert plan.fallback_flat is False
    assert len(plan.layers) == 5

    # Check layer types and speeds
    bg_inst = plan.layers[0]
    assert bg_inst.layer_type == LayerType.BACKGROUND
    assert bg_inst.motion_factor == 0.6
    assert bg_inst.depth == 0.1

    p1_inst = plan.layers[1]
    p2_inst = plan.layers[2]
    p3_inst = plan.layers[3]

    assert p1_inst.layer_type == LayerType.FOREGROUND
    assert p2_inst.layer_type == LayerType.FOREGROUND
    assert p3_inst.layer_type == LayerType.FOREGROUND

    # Motion factors: 1.10 for prop_1, 1.15 for prop_2, 1.20 for prop_3
    assert p1_inst.motion_factor == 1.10
    assert p2_inst.motion_factor == 1.15
    assert p3_inst.motion_factor == 1.20

    # Distinct depths
    assert p1_inst.depth != p2_inst.depth
    assert p2_inst.depth != p3_inst.depth

    char_inst = plan.layers[4]
    assert char_inst.layer_type == LayerType.CHARACTER
    assert char_inst.motion_factor == 1.0
    assert char_inst.depth == 0.8

    # Test custom depth override per prop name
    custom_depths = {
        "prop_2": 0.55,
        "CHARACTER": 0.92,
    }
    custom_plan = stack.to_parallax_plan(default_depths=custom_depths)
    assert custom_plan.layers[2].depth == 0.55
    assert custom_plan.layers[4].depth == 0.92

    # Test dictionary serialization
    plan_dict = custom_plan.model_dump() if hasattr(custom_plan, "model_dump") else custom_plan.dict()
    assert plan_dict["enabled"] is True
    assert len(plan_dict["layers"]) == 5
    assert plan_dict["layers"][1]["motion_factor"] == 1.10
    assert plan_dict["layers"][2]["motion_factor"] == 1.15
    assert plan_dict["layers"][3]["motion_factor"] == 1.20


def test_m4_multi_prop_backward_compatibility_merged():
    """Verify decompose_layers with isolate_props=False maintains single merged prop_1 layer."""
    w, h = 400, 300
    base = np.full((h, w, 3), 180, dtype=np.uint8)

    cv2.ellipse(base, (200, 150), (45, 75), 0, 0, 360, (50, 60, 80), -1)
    cv2.circle(base, (70, 70), 20, (200, 40, 40), -1)
    cv2.rectangle(base, (310, 200), (370, 260), (40, 180, 50), -1)
    cv2.rectangle(base, (320, 50), (340, 110), (180, 180, 30), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="multi_compat_panel", isolate_props=False)
    assert len(stack.layers) == 3
    assert len(stack.props) == 1
    assert stack.props[0].name == "prop_1"
    assert stack.props[0].z_index == 15
    assert stack.props[0].depth_estimate == 0.6

    plan = stack.to_parallax_plan()
    assert len(plan.layers) == 3
    assert plan.layers[1].motion_factor == 1.10


def test_m4_r1_turnaround_all_poses_and_views_acceptance_matrix():
    """Verify R1 acceptance matrix: all RiggingPose and RiggingView prompt compilations."""
    story = sample_story()
    char = story.bible.characters[0]

    poses: list[ss.RiggingPose] = ["a_pose", "t_pose", "neutral_standing"]
    views: list[ss.RiggingView] = ["front", "three_quarter", "side", "back"]

    for pose in poses:
        spec = RiggingSpec(pose=pose, orthographic=True, limb_separation=True, visible_joints=True)

        # 1. Turnaround prompt compilation (Danbooru tags for SDXL)
        prompt_tags = compile_turnaround_prompt(char, story, spec, style_kind="tags")
        assert "full body" in prompt_tags
        assert "orthographic" in prompt_tags
        assert "background" in prompt_tags
        assert ("a-pose" in prompt_tags or "t-pose" in prompt_tags or "standing" in prompt_tags)
        assert "limb separation" in prompt_tags

        # 2. Turnaround prompt compilation (Natural language for FLUX/Qwen)
        prompt_nat = compile_turnaround_prompt(char, story, spec, style_kind="natural")
        assert "turnaround model sheet" in prompt_nat
        assert "orthographic" in prompt_nat
        assert "limb separation" in prompt_nat
        assert "unobstructed silhouette" in prompt_nat

        # 3. Individual view prompt compilation
        for view in views:
            v_tags = compile_rigging_view_prompt(char, view, story, spec, style_kind="tags")
            assert "full body" in v_tags
            assert "orthographic" in v_tags

            v_nat = compile_rigging_view_prompt(char, view, story, spec, style_kind="natural")
            assert "orthographic rigging reference" in v_nat

    # Verify negative prompt constraints
    assert "cropped" in RIGGING_NEGATIVE
    assert "bad anatomy" in RIGGING_NEGATIVE
    assert "overlapping limbs" in RIGGING_NEGATIVE
    assert "complex background" in RIGGING_NEGATIVE


def test_m4_r2_neural_alpha_matting_and_defringe_matrix():
    """Verify R2 acceptance matrix: clean alpha, Guided Filter smoothing, EDT color decontamination."""
    w, h = 100, 100
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.uint8)

    # Interior foreground: bright green (0, 255, 0), alpha 255
    cv2.circle(rgb, (50, 50), 30, (0, 255, 0), -1)
    cv2.circle(alpha, (50, 50), 30, 255, -1)

    # Contaminated boundary ring: dirty gray background color (180, 180, 180) with semi-transparent alpha
    cv2.circle(rgb, (50, 50), 34, (180, 180, 180), 3)
    cv2.circle(alpha, (50, 50), 34, 120, 3)

    # 1. Test Guided Filter edge anti-aliasing
    smoothed_alpha = guided_filter_alpha(rgb, alpha, radius=4, eps=1e-3)
    assert smoothed_alpha.shape == (h, w)
    assert smoothed_alpha.dtype == np.uint8
    # Interior must remain high opacity
    assert smoothed_alpha[50, 50] == 255
    # Exterior must remain transparent
    assert smoothed_alpha[5, 5] == 0

    # 2. Test Voronoi/EDT color decontamination
    clean_rgb, clean_alpha = defringe_alpha(rgb, smoothed_alpha)
    assert clean_rgb.shape == (h, w, 3)
    assert clean_alpha.shape == (h, w)

    # The dirty gray border at boundary (r ~ 32) should be replaced with green interior color
    sample_boundary_color = clean_rgb[50, 82]  # x=82 is ~32px from center (50)
    assert sample_boundary_color[1] > sample_boundary_color[0], "Boundary pixel must be decontaminated to green"
    assert sample_boundary_color[1] > sample_boundary_color[2], "Boundary pixel must be decontaminated to green"

    # 3. Test remove_background returns valid transparent 4-channel RGBA PNG
    rgba_in = np.dstack([rgb, alpha])
    res = remove_background(rgba_in, runner=None, defringe=True)
    assert isinstance(res, MattingResult)
    assert res.has_alpha is True
    assert res.halo_free is True
    assert res.rgba_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    res_im = res.to_image()
    assert res_im.mode == "RGBA"
    assert res_im.size == (w, h)


def test_m4_r3_layer_decomposition_and_inpaint_dilation_matrix():
    """Verify R3 acceptance matrix: clean infilled background plate with +12px dilation."""
    w, h = 120, 120
    base_arr = np.zeros((h, w, 3), dtype=np.uint8)
    base_arr[:, :] = [160, 170, 180]
    cv2.circle(base_arr, (60, 60), 20, (30, 40, 50), -1)

    base_im = Image.fromarray(base_arr)
    mask_arr = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask_arr, (60, 60), 20, 255, -1)
    mask_im = Image.fromarray(mask_arr, "L")

    infilled_bg = inpaint_background_plate(base_im, mask_im, runner=None, dilation_px=12)

    assert infilled_bg.size == (w, h)
    assert infilled_bg.mode == "RGB"

    infilled_np = np.array(infilled_bg)
    center_color = infilled_np[60, 60]
    assert center_color[0] > 100
    assert center_color[1] > 100
    assert center_color[2] > 100


def test_m4_r4_comfyui_workflow_registry_and_preflight_matrix():
    """Verify R4 acceptance matrix: registry entry, SHA256 integrity, required slots, and model discovery."""
    import json
    import hashlib

    reg_file = Path("engine/comfyui/workflow_registry.json")
    assert reg_file.exists(), "workflow_registry.json must exist"

    with open(reg_file, "r", encoding="utf-8") as f:
        registry = json.load(f)

    matches = [item for item in registry if item.get("id") == "anime_alpha_matting"]
    assert len(matches) == 1, "anime_alpha_matting must be registered in workflow_registry.json"
    entry = matches[0]

    assert entry["filename"] == "anime_alpha_matting.api.json"
    wf_path = Path("engine/comfyui/workflows") / entry["filename"]
    assert wf_path.exists(), f"Workflow file {wf_path} must exist on disk"

    expected_sha = hashlib.sha256(wf_path.read_bytes()).hexdigest()
    assert entry["sha256"] == expected_sha, "Registry SHA256 must match workflow JSON exactly"

    slots = entry.get("patch_slots", {})
    assert "reference_image" in slots, "reference_image patch slot is required"
    assert ("filename_prefix" in slots or "prefix" in slots), "prefix patch slot is required"

    client = ComfyUIClient()
    models = client.discover_models()
    assert "background_removal" in models, "discover_models must include 'background_removal'"


def test_m4_r5_generic_design_and_local_first_operation():
    """Verify R5 acceptance matrix: generic design without chapter hacks and local-first execution."""
    import inspect
    from engine.original import rigging

    source = inspect.getsource(rigging)

    banned_terms = ["chapter_1", "chapter_2", "episode_1", "test_panel", "specific_hack"]
    for term in banned_terms:
        assert term not in source, f"rigging.py must not contain story/chapter hack '{term}'"

    w, h = 64, 64
    base = np.full((h, w, 3), 150, dtype=np.uint8)
    cv2.circle(base, (32, 32), 15, (50, 60, 70), -1)

    mat_res = remove_background(base, runner=None)
    assert mat_res.has_alpha is True

    infilled = inpaint_background_plate(base, mat_res.to_mask_image(), runner=None)
    assert infilled.size == (w, h)

    stack = decompose_layers(base, panel_id="generic_panel", runner=None)
    assert len(stack.layers) >= 2
    plan = stack.to_parallax_plan()
    assert plan.enabled is True



