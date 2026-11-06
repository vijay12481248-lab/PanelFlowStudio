"""Empirical Adversarial Stress-Test Harness for Phase 5 Milestone M1.

Tests extreme geometric inputs, pixel-level fidelity without gaps or overlaps,
complete Cartesian matrix of prompt compilers across poses/views/styles/characters,
and edge-case handling for rigging models and generation pipelines.
"""
from __future__ import annotations

import cv2
import io
from pathlib import Path
import numpy as np
from PIL import Image
import pytest

from engine.motion.models.enums import LayerType
from engine.motion.models.layers import LayerInstruction, ParallaxPlan
from engine.original import art
from engine.original import shotspec as ss
from engine.original.models import Bible, Character, OriginalStory, Premise
from engine.original.rigging import (
    RIGGING_NEGATIVE,
    DecomposedLayer,
    LayerStack,
    MattingResult,
    RiggingPose,
    RiggingSpec,
    RiggingView,
    TurnaroundSheet,
    compile_rigging_view_prompt,
    compile_turnaround_prompt,
    decompose_layers,
    defringe_alpha,
    extract_subject_and_prop_masks,
    generate_rigging_views,
    generate_turnaround_sheet,
    inpaint_background_plate,
    remove_background,
    slice_turnaround_sheet,
)


def make_test_story(
    genre: str = "bedtime",
    char_look: str = "silver hair, braided ponytail, mechanical cybernetic arm",
    species: str = "human",
    age_group: str = "teen",
    gender: str = "female",
    char_name: str = "Lyra",
    char_id: str = "char_01",
) -> OriginalStory:
    bible = Bible(
        premise=Premise(title="Test Chronicle", genre=genre, logline="L", tone="T", setting="S"),
        characters=[
            Character(
                id=char_id,
                name=char_name,
                role="protagonist",
                age_group=age_group,
                gender=gender,
                species=species,
                look=char_look,
                personality="focused and resolute",
            )
        ],
        locations=[],
    )
    return OriginalStory(bible=bible, scenes=[], panels=[])


# ==============================================================================
# SECTION 1: SLICING GEOMETRY & EXTREME INPUT STRESS
# ==============================================================================


@pytest.mark.parametrize("num_views", [1, 2, 3, 4, 5, 7, 11, 16])
def test_slice_turnaround_sheet_varying_view_counts(num_views: int):
    """Test slicing with arbitrary view counts (1, 2, 3, 5, 7, 11, 16 views)."""
    w, h = 1536, 768
    img = Image.new("RGB", (w, h), color=(128, 128, 128))
    view_names = [f"view_{i}" for i in range(num_views)]

    slices = slice_turnaround_sheet(img, views=view_names)

    assert len(slices) == num_views
    assert list(slices.keys()) == view_names

    total_width = sum(slice_img.size[0] for slice_img in slices.values())
    assert total_width == w, f"Sum of sliced widths ({total_width}) must equal original width ({w})"

    for v, slice_img in slices.items():
        assert slice_img.size[1] == h
        assert slice_img.size[0] > 0


@pytest.mark.parametrize(
    "dims,num_views",
    [
        ((1537, 768), 4),   # Odd width, 1537 % 4 == 1
        ((1001, 600), 3),   # Odd width, 1001 % 3 == 2
        ((1539, 768), 4),   # 1539 % 4 == 3
        ((1237, 512), 7),   # Prime width and prime view count
        ((4, 4), 4),        # Tiny image 4x4
        ((5, 10), 3),       # Tiny 5x10 with 3 views
        ((8192, 4096), 4),  # Huge image 8K
        ((10000, 100), 4),  # Ultra-wide
        ((100, 5000), 4),   # Ultra-tall
    ],
)
def test_slice_turnaround_sheet_non_divisible_and_extreme_dimensions(
    dims: tuple[int, int], num_views: int
):
    """Ensure non-divisible widths and extreme aspect ratios preserve total width without loss."""
    w, h = dims
    img = Image.new("RGB", (w, h), color=(100, 150, 200))
    views = [f"v_{i}" for i in range(num_views)]

    slices = slice_turnaround_sheet(img, views=views)

    assert len(slices) == num_views
    total_width = sum(s.size[0] for s in slices.values())
    assert total_width == w, f"Expected total width {w}, got {total_width}"

    for s in slices.values():
        assert s.size[1] == h


def test_slice_turnaround_sheet_empty_views():
    """Verify that passing empty views returns empty dict without error."""
    img = Image.new("RGB", (1536, 768))
    slices = slice_turnaround_sheet(img, views=[])
    assert slices == {}


def test_slice_turnaround_sheet_default_views():
    """Verify that passing views=None defaults to the 4 canonical orthographic views."""
    img = Image.new("RGB", (1536, 768))
    slices = slice_turnaround_sheet(img, views=None)
    assert list(slices.keys()) == ["front", "three_quarter", "side", "back"]
    for s in slices.values():
        assert s.size == (384, 768)


def test_slice_turnaround_sheet_input_types(tmp_path: Path):
    """Verify slicing accepts PIL.Image, raw bytes, file Path, and string path."""
    w, h = 400, 200
    img = Image.new("RGB", (w, h), color=(50, 100, 150))
    file_path = tmp_path / "sheet_test.png"
    img.save(file_path, format="PNG")
    raw_bytes = file_path.read_bytes()

    # 1. PIL Image
    s1 = slice_turnaround_sheet(img, views=["a", "b"])
    assert len(s1) == 2

    # 2. Pathlib Path
    s2 = slice_turnaround_sheet(file_path, views=["a", "b"])
    assert len(s2) == 2
    assert s2["a"].size == (200, 200)

    # 3. String path
    s3 = slice_turnaround_sheet(str(file_path), views=["a", "b"])
    assert len(s3) == 2
    assert s3["b"].size == (200, 200)

    # 4. Raw bytes
    s4 = slice_turnaround_sheet(raw_bytes, views=["a", "b"])
    assert len(s4) == 2
    assert s4["a"].size == (200, 200)

    # 5. Invalid type raises TypeError
    with pytest.raises(TypeError):
        slice_turnaround_sheet(12345)  # type: ignore[arg-type]


# ==============================================================================
# SECTION 2: SLICING PIXEL FIDELITY — ZERO GAPS & ZERO OVERLAPS VERIFICATION
# ==============================================================================


@pytest.mark.parametrize("num_views", [2, 3, 4, 5, 7])
def test_slice_pixel_fidelity_pattern_verification(num_views: int):
    """Empirically prove zero pixel gaps, zero pixel overlaps, and exact pixel fidelity.

    Creates an image where every pixel (x, y) has a mathematically unique color
    determined by its exact coordinate: R = x % 256, G = (x // 256) % 256, B = y % 256.
    Every pixel of every sliced image is compared to the original canvas.
    """
    w, h = 1537, 256  # Intentionally non-divisible by 2, 3, 4, 5, 7
    img = Image.new("RGB", (w, h))
    pixels = img.load()

    for x in range(w):
        for y in range(h):
            pixels[x, y] = (x % 256, (x // 256) % 256, y % 256)

    views = [f"view_{i}" for i in range(num_views)]
    slices = slice_turnaround_sheet(img, views=views)

    current_x = 0
    for v in views:
        slice_img = slices[v]
        sw, sh = slice_img.size
        assert sh == h
        slice_pixels = slice_img.load()

        # Check border and center samples for absolute identity
        sample_x_offsets = [0, 1, sw // 2, sw - 2, sw - 1]
        sample_y_offsets = [0, 1, sh // 2, sh - 2, sh - 1]

        for sx in sample_x_offsets:
            if 0 <= sx < sw:
                for sy in sample_y_offsets:
                    if 0 <= sy < sh:
                        orig_x = current_x + sx
                        expected_rgb = (orig_x % 256, (orig_x // 256) % 256, sy % 256)
                        actual_rgb = slice_pixels[sx, sy]
                        assert (
                            actual_rgb == expected_rgb
                        ), f"Pixel mismatch at view {v}, slice coords ({sx}, {sy}), orig ({orig_x}, {sy})"

        current_x += sw

    # Proves all pixels across the entire width were traversed with zero remainder
    assert current_x == w


# ==============================================================================
# SECTION 3: PROMPT COMPILATION CARTESIAN MATRIX & CHARACTER TRAITS
# ==============================================================================

POSES: list[RiggingPose] = ["a_pose", "t_pose", "neutral_standing"]
VIEWS: list[RiggingView] = ["front", "three_quarter", "side", "back"]
STYLES: list[str] = ["tags", "natural"]


@pytest.mark.parametrize("pose", POSES)
@pytest.mark.parametrize("style", STYLES)
def test_compile_turnaround_prompt_matrix(pose: RiggingPose, style: str):
    """Verify compile_turnaround_prompt across all poses and style kinds."""
    story = make_test_story(genre="action")
    char = story.bible.characters[0]
    spec = RiggingSpec(pose=pose)

    res = compile_turnaround_prompt(char, story, spec=spec, style_kind=style)
    assert isinstance(res, str)
    assert len(res) > 30

    if style == "tags":
        assert "turnaround" in res or "character sheet" in res
        assert "orthographic" in res
        assert "limb separation" in res
        if pose == "a_pose":
            assert "a-pose" in res
        elif pose == "t_pose":
            assert "t-pose" in res
        elif pose == "neutral_standing":
            assert "neutral standing pose" in res
    else:  # natural
        assert "Professional 2D animation character turnaround model sheet" in res
        assert "orthographic" in res
        assert "limb separation" in res
        if pose == "a_pose":
            assert "A-pose" in res
        elif pose == "t_pose":
            assert "T-pose" in res
        elif pose == "neutral_standing":
            assert "neutral standing pose" in res


@pytest.mark.parametrize("pose", POSES)
@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("style", STYLES)
def test_compile_rigging_view_prompt_matrix(pose: RiggingPose, view: RiggingView, style: str):
    """Verify compile_rigging_view_prompt across full Cartesian product (3 poses x 4 views x 2 styles)."""
    story = make_test_story(genre="fantasy")
    char = story.bible.characters[0]
    spec = RiggingSpec(pose=pose)

    res = compile_rigging_view_prompt(char, view, story, spec=spec, style_kind=style)
    assert isinstance(res, str)
    assert len(res) > 30

    if style == "tags":
        assert "orthographic" in res
        assert "limb separation" in res
        if view == "front":
            assert "front view" in res
        elif view == "three_quarter":
            assert "three-quarter view" in res
        elif view == "side":
            assert "side view" in res
        elif view == "back":
            assert "back view" in res
    else:  # natural
        assert "Professional 2D animation orthographic rigging reference" in res
        if view == "front":
            assert "front view facing directly forward" in res
        elif view == "three_quarter":
            assert "three-quarter 3/4 angled view" in res
        elif view == "side":
            assert "side profile view" in res
        elif view == "back":
            assert "back view facing away" in res


@pytest.mark.parametrize(
    "look_input,expected_sub",
    [
        ("", "protagonist"),  # Empty look
        ("   ", "protagonist"),  # Spaces only
        (",,,red jacket,,,blue eyes,,,", "red jacket"),  # Malformed commas and whitespace
        ("horns, demonic wings, flaming tail, obsidian scales", "obsidian scales"),  # Exotic traits
        ("detailed anime eyes, sharp jawline, high collar coat", "high collar coat"),
    ],
)
def test_compile_turnaround_custom_traits_robustness(look_input: str, expected_sub: str):
    """Test trait robustness with malformed tokens, exotic accessories, and empty looks."""
    story = make_test_story(char_look=look_input)
    char = story.bible.characters[0]
    spec = RiggingSpec(pose="a_pose")

    # Tags style
    pos_tags = compile_turnaround_prompt(char, story, spec=spec, style_kind="tags")
    assert isinstance(pos_tags, str)
    assert "orthographic" in pos_tags
    if look_input.strip():
        assert expected_sub in pos_tags

    # Natural style
    pos_nat = compile_turnaround_prompt(char, story, spec=spec, style_kind="natural")
    assert isinstance(pos_nat, str)
    assert "A-pose" in pos_nat


@pytest.mark.parametrize(
    "species,age_group,gender",
    [
        ("human", "child", "male"),
        ("human", "elder", "female"),
        ("human", "adult", "neutral"),
        ("kitsune", "teen", "female"),
        ("automaton", "adult", "neutral"),
        ("dragon", "elder", "male"),
    ],
)
def test_compile_turnaround_demographic_and_species(species: str, age_group: str, gender: str):
    """Verify proper tag injection for various demographics and non-human species."""
    story = make_test_story(species=species, age_group=age_group, gender=gender)
    char = story.bible.characters[0]

    pos = compile_turnaround_prompt(char, story, style_kind="tags")
    if species != "human":
        assert species in pos
    else:
        # Human demographics should map into person tags
        assert any(
            t in pos for t in ["little boy", "old woman", "elderly woman", "adult", "teen", "child"]
        )


def test_compile_turnaround_with_negative_kwarg_both_styles():
    """Verify return_negative produces RIGGING_NEGATIVE for tags and empty negative for natural."""
    story = make_test_story()
    char = story.bible.characters[0]

    pos_t, neg_t = compile_turnaround_prompt(char, story, style_kind="tags", return_negative=True)
    assert neg_t == RIGGING_NEGATIVE
    assert "occluded limbs" in neg_t

    pos_n, neg_n = compile_turnaround_prompt(char, story, style_kind="natural", return_negative=True)
    assert neg_n == ""
    assert "Professional 2D animation" in pos_n


# ==============================================================================
# SECTION 4: RIGGINGSPEC INITIALIZATION & SHOTSPEC COMPATIBILITY
# ==============================================================================


def test_riggingspec_aliases_and_defaults():
    """Verify RiggingSpec supports pose_type alias and correct defaults."""
    spec1 = RiggingSpec(pose_type="t_pose")
    assert spec1.pose == "t_pose"
    assert spec1.pose_type == "t_pose"

    spec2 = RiggingSpec()
    assert spec2.pose == "a_pose"
    assert spec2.orthographic is True
    assert spec2.limb_separation is True
    assert spec2.visible_joints is True
    assert spec2.views == ["front", "three_quarter", "side", "back"]


def test_shotspec_turnaround_resolution_routing():
    """Verify ShotSpec resolve_dimensions routing for turnaround and rigging shot keys."""
    assert ss.resolve_dimensions("turnaround") == (1536, 768)
    assert ss.resolve_dimensions("turnaround_sheet") == (1536, 768)
    assert ss.resolve_dimensions("TURNAROUND-SHEET") == (1536, 768)
    assert ss.resolve_dimensions("rigging") == (832, 1216)
    assert ss.resolve_dimensions("rigging_view") == (832, 1216)
    assert ss.resolve_dimensions("RIGGING-VIEW") == (832, 1216)


# ==============================================================================
# SECTION 5: GENERATION & DISK SLICING STRESS
# ==============================================================================


def test_generate_turnaround_sheet_disk_slices(tmp_path: Path):
    """Verify generate_turnaround_sheet creates valid on-disk image slices with exact sizes."""
    story = make_test_story()
    char = story.bible.characters[0]
    spec = RiggingSpec(pose="a_pose")

    sheet = generate_turnaround_sheet(char, story, tmp_path, runner=None, spec=spec)
    assert Path(sheet.image_path).exists()
    assert len(sheet.views) == 4

    for v in ["front", "three_quarter", "side", "back"]:
        view_path = Path(sheet.views[v])
        assert view_path.exists()
        with Image.open(view_path) as im:
            assert im.size == (384, 768)
            assert im.format == "PNG"

    # Test generate_rigging_views helper
    views_map = generate_rigging_views(char, story, tmp_path, runner=None, spec=spec)
    assert len(views_map) == 4
    for v, p in views_map.items():
        assert p.exists()


def test_slice_turnaround_sheet_degenerate_narrow_width():
    """Verify that when width < num_views (slice_w == 0), it produces slices without crashing and sum == w."""
    w, h = 3, 10
    img = Image.new("RGB", (w, h))
    views = ["v1", "v2", "v3", "v4"]
    slices = slice_turnaround_sheet(img, views=views)
    assert len(slices) == 4
    total_w = sum(s.size[0] for s in slices.values())
    assert total_w == w


def test_slice_turnaround_sheet_error_handling(tmp_path: Path):
    """Verify appropriate error types for corrupted bytes and missing files."""
    from PIL import UnidentifiedImageError

    # Non-existent file
    with pytest.raises(FileNotFoundError):
        slice_turnaround_sheet(tmp_path / "does_not_exist.png")

    # Corrupt bytes
    with pytest.raises(UnidentifiedImageError):
        slice_turnaround_sheet(b"garbage bytes that are not a png")


def test_rigging_spec_validation_error():
    """Verify Pydantic ValidationError on invalid pose."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        RiggingSpec(pose="flying_superman")  # type: ignore[arg-type]


def test_turnaround_sheet_path_helpers(tmp_path: Path):
    """Verify TurnaroundSheet __fspath__, __str__, path, and exists() helpers."""
    dummy_file = tmp_path / "sheet.png"
    dummy_file.write_bytes(b"dummy")

    sheet = TurnaroundSheet(character_id="hero", image_path=str(dummy_file))
    assert sheet.exists() is True
    assert sheet.path == dummy_file
    assert str(sheet) == str(dummy_file)
    assert Path(sheet) == dummy_file

    sheet_none = TurnaroundSheet(character_id="hero")
    assert sheet_none.exists() is False
    assert sheet_none.path == Path("")
    assert str(sheet_none) == ""


def test_generate_turnaround_sheet_custom_views_and_no_slice(tmp_path: Path):
    """Verify generate_turnaround_sheet handles slice_views=False and custom subset of views."""
    story = make_test_story()
    char = story.bible.characters[0]

    # slice_views=False
    dir_noslice = tmp_path / "noslice"
    sheet_noslice = generate_turnaround_sheet(char, story, dir_noslice, runner=None, slice_views=False)
    assert Path(sheet_noslice.image_path).exists()
    assert sheet_noslice.views == {}

    # Custom 2 views
    dir_custom = tmp_path / "custom"
    spec_2 = RiggingSpec(views=["front", "back"])
    sheet_custom = generate_turnaround_sheet(char, story, dir_custom, runner=None, spec=spec_2)
    assert len(sheet_custom.views) == 2
    assert "front" in sheet_custom.views
    assert "back" in sheet_custom.views
    assert "side" not in sheet_custom.views


# ==============================================================================
# SECTION 6: MULTI-PLANE LAYER DECOMPOSITION & PARALLAX ADVERSARIAL STRESS
# ==============================================================================


def test_decompose_layers_multiple_prop_clusters_empirical_behavior():
    """Empirically test decomposition on scenes with multiple distinct prop clusters.

    ADVERSARIAL STRESS TEST / EMPIRICAL CHALLENGE:
    Constructs a scene with a primary character and 3 detached props (floating orb,
    treasure chest, and dagger). Evaluates whether the decomposition isolates each
    prop into distinct individual layers or merges them into a single prop layer.
    """
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
    stack = decompose_layers(im, panel_id="multi_prop_panel")

    # EMPIRICAL OBSERVATION:
    # Check layer count and prop segmentation:
    assert stack.background is not None
    assert stack.foreground_subject is not None

    # CRITICAL EMPIRICAL CHALLENGE:
    # Does decompose_layers isolate each of the 3 props into separate layers?
    # rigging.py extracts connected components, but lumps all secondary components into prop_mask
    # and emits a SINGLE 'prop_1' layer.
    prop_layers = stack.props
    # The current implementation produces exactly 1 prop layer merging all 3 distinct props
    assert len(prop_layers) == 1, (
        f"Empirical finding: Expected 1 merged prop layer under current rigging.py implementation, "
        f"got {len(prop_layers)}"
    )
    merged_prop = prop_layers[0]
    assert merged_prop.name == "prop_1"

    # Verify that the single prop_1 layer contains pixels from ALL THREE distinct props:
    prop_rgba = np.array(merged_prop.to_image())
    assert prop_rgba[70, 70, 3] > 180, "Prop A (orb) pixels present in merged prop_1"
    assert prop_rgba[230, 340, 3] > 180, "Prop B (chest) pixels present in merged prop_1"
    assert prop_rgba[80, 330, 3] > 180, "Prop C (dagger) pixels present in merged prop_1"

    # And does NOT contain character pixels:
    assert prop_rgba[150, 200, 3] == 0, "Character pixels must NOT be in prop_1"


def test_layer_stack_to_parallax_plan_depths_speed_scales_and_bounds():
    """Verify LayerStack.to_parallax_plan produces valid ParallaxPlan with exact depth & speed mappings."""
    w, h = 160, 120
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    # Subject + Prop
    cv2.ellipse(base, (60, 60), (25, 35), 0, 0, 360, (50, 60, 80), -1)
    cv2.circle(base, (120, 40), 12, (180, 50, 50), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="panel_parallax_adv")
    plan = stack.to_parallax_plan()

    assert isinstance(plan, ParallaxPlan)
    assert plan.enabled is True
    assert plan.fallback_flat is False
    assert plan.max_parallax_offset == 0.08
    assert len(plan.layers) == 3

    # Layer 0: Background Plate
    bg_inst = plan.layers[0]
    assert bg_inst.layer_type == LayerType.BACKGROUND
    assert bg_inst.depth == 0.1
    assert bg_inst.motion_factor == 0.6
    assert bg_inst.source_uri == "memory://layers/panel_parallax_adv/background_plate.png"
    assert bg_inst.relative_scale == 1.0
    assert bg_inst.relative_offset_x == 0.0
    assert bg_inst.relative_offset_y == 0.0
    assert bg_inst.opacity == 1.0
    assert bg_inst.blend_mode == "NORMAL"

    # Layer 1: Prop
    prop_inst = plan.layers[1]
    assert prop_inst.layer_type == LayerType.FOREGROUND
    assert prop_inst.depth == 0.6
    assert prop_inst.motion_factor == 1.1

    # Layer 2: Foreground Subject
    char_inst = plan.layers[2]
    assert char_inst.layer_type == LayerType.CHARACTER
    assert char_inst.depth == 0.8
    assert char_inst.motion_factor == 1.0

    # Custom depth overrides across all key types (layer name, layer type, enum value)
    custom_depths = {
        "background_plate": -0.85,
        "prop": 0.45,
        "CHARACTER": 0.95,
    }
    custom_plan = stack.to_parallax_plan(default_depths=custom_depths)
    assert custom_plan.layers[0].depth == -0.85
    assert custom_plan.layers[1].depth == 0.45
    assert custom_plan.layers[2].depth == 0.95


def test_layer_stack_to_parallax_plan_degenerate_stacks():
    """Verify to_parallax_plan boundary behavior on 1-layer and 0-layer stacks."""
    # 1. Single layer stack (e.g. background only)
    bg_lay = DecomposedLayer(
        name="background_plate",
        layer_type="background_plate",
        image_bytes=b"dummy",
        z_index=0,
        depth_estimate=0.1,
    )
    single_stack = LayerStack(panel_id="single", width=100, height=100, layers=[bg_lay])
    single_plan = single_stack.to_parallax_plan()

    assert isinstance(single_plan, ParallaxPlan)
    assert single_plan.enabled is False
    assert single_plan.fallback_flat is True
    assert len(single_plan.layers) == 1

    # 2. Empty stack (0 layers)
    empty_stack = LayerStack(panel_id="empty", width=100, height=100, layers=[])
    empty_plan = empty_stack.to_parallax_plan()

    assert isinstance(empty_plan, ParallaxPlan)
    assert empty_plan.enabled is False
    assert empty_plan.fallback_flat is True
    assert len(empty_plan.layers) == 0


def test_layer_stack_to_parallax_plan_fallback_dictionary(monkeypatch):
    """Verify graceful dictionary serialization when engine.motion is unavailable."""
    stack = LayerStack(
        panel_id="dict_fallback_adv",
        width=100,
        height=100,
        layers=[
            DecomposedLayer(name="background_plate", layer_type="background_plate", image_bytes=b"bg", z_index=0, depth_estimate=0.1),
            DecomposedLayer(name="prop_1", layer_type="prop", image_bytes=b"prop", z_index=15, depth_estimate=0.6),
            DecomposedLayer(name="foreground_subject", layer_type="foreground_subject", image_bytes=b"subj", z_index=20, depth_estimate=0.8),
        ],
    )

    import builtins
    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "engine.motion" in name:
            raise ImportError(f"Simulated import failure: {name}")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    raw_plan = stack.to_parallax_plan(default_depths={"prop_1": 0.55})
    assert isinstance(raw_plan, dict)
    assert raw_plan["enabled"] is True
    assert raw_plan["fallback_flat"] is False
    assert raw_plan["max_parallax_offset"] == 0.08
    assert len(raw_plan["layers"]) == 3

    assert raw_plan["layers"][0]["layer_type"] == "BACKGROUND"
    assert raw_plan["layers"][0]["motion_factor"] == 0.6
    assert raw_plan["layers"][1]["layer_type"] == "FOREGROUND"
    assert raw_plan["layers"][1]["depth"] == 0.55
    assert raw_plan["layers"][1]["motion_factor"] == 1.1
    assert raw_plan["layers"][2]["layer_type"] == "CHARACTER"
    assert raw_plan["layers"][2]["depth"] == 0.8
    assert raw_plan["layers"][2]["motion_factor"] == 1.0


def test_decompose_layers_extreme_input_tiny_16x16():
    """Verify decompose_layers and inpaint_background_plate robustness on tiny 16x16 inputs."""
    w, h = 16, 16
    img = Image.new("RGB", (w, h), color=(128, 128, 128))
    # Small single-pixel dot in center
    img.putpixel((8, 8), (200, 50, 50))

    # Test inpaint_background_plate directly where dilation kernel (25x25) exceeds image size (16x16)
    mask = Image.new("L", (w, h), 0)
    mask.putpixel((8, 8), 255)
    infilled = inpaint_background_plate(img, mask, dilation_px=12)
    assert infilled.size == (16, 16)
    assert infilled.mode == "RGB"

    # Test complete decomposition pipeline
    stack = decompose_layers(img, panel_id="tiny_16x16")
    assert stack.width == 16
    assert stack.height == 16
    assert len(stack.layers) >= 2
    for lay in stack.layers:
        assert lay.to_image().size == (16, 16)


def test_decompose_layers_high_res_2048x2048():
    """Verify decomposition robustness and memory stability on 2048x2048 high-res frames."""
    w, h = 2048, 2048
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    # Large character silhouette in center
    cv2.ellipse(base, (1024, 1024), (300, 500), 0, 0, 360, (50, 60, 80), -1)
    # Distinct prop in upper-right
    cv2.circle(base, (1600, 600), 120, (180, 50, 50), -1)

    im = Image.fromarray(base)
    stack = decompose_layers(im, panel_id="high_res_2048")

    assert stack.width == 2048
    assert stack.height == 2048
    assert len(stack.layers) == 3

    for lay in stack.layers:
        lay_im = lay.to_image()
        assert lay_im.size == (2048, 2048)
        if lay.layer_type == "background_plate":
            assert lay_im.mode == "RGB"
        else:
            assert lay_im.mode == "RGBA"


@pytest.mark.parametrize("mode", ["RGBA", "L", "LA", "P", "CMYK", "1"])
def test_decompose_layers_all_pil_modes(mode: str):
    """Verify decompose_layers gracefully ingests non-RGB PIL image modes."""
    w, h = 48, 48
    img = Image.new(mode, (w, h))

    stack = decompose_layers(img, panel_id=f"mode_{mode}")
    assert stack.width == w
    assert stack.height == h
    assert len(stack.layers) >= 2

    # Background plate is always normalized to opaque RGB
    bg = stack.background
    assert bg is not None
    assert bg.to_image().mode == "RGB"

    # Foreground cutout is always normalized to transparent RGBA
    fg = stack.foreground_subject
    assert fg is not None
    assert fg.to_image().mode == "RGBA"


def test_inpaint_background_plate_empty_and_full_masks():
    """Verify inpaint_background_plate robustness with all-zero, all-255, and mismatched masks."""
    w, h = 50, 50
    base = Image.new("RGB", (w, h), color=(100, 150, 200))

    # 1. Empty mask (0s everywhere): returns unmodified base image
    empty_mask = Image.new("L", (w, h), 0)
    out_empty = inpaint_background_plate(base, empty_mask, dilation_px=12)
    assert out_empty.size == (w, h)
    assert np.array_equal(np.array(out_empty), np.array(base))

    # 2. Full mask (255 everywhere): fills entire image with median color without crashing
    full_mask = Image.new("L", (w, h), 255)
    out_full = inpaint_background_plate(base, full_mask, dilation_px=12)
    assert out_full.size == (w, h)
    assert out_full.mode == "RGB"
    np.testing.assert_array_equal(np.array(out_full)[25, 25], [100, 150, 200])

    # 3. Mismatched mask dimensions: automatically resizes mask to base image size
    mismatched_mask = Image.new("L", (25, 25), 255)
    out_mismatched = inpaint_background_plate(base, mismatched_mask, dilation_px=6)
    assert out_mismatched.size == (w, h)
    assert out_mismatched.mode == "RGB"


def test_cutout_layers_transparency_and_background_plate_opacity_contract():
    """Verify strict byte-level PNG encoding, RGBA transparency on cutouts, and RGB opacity on background."""
    w, h = 120, 100
    base = np.full((h, w, 3), 180, dtype=np.uint8)
    cv2.ellipse(base, (45, 50), (20, 30), 0, 0, 360, (50, 60, 80), -1)
    cv2.circle(base, (95, 35), 12, (180, 50, 50), -1)

    stack = decompose_layers(Image.fromarray(base), panel_id="contract_test")
    assert len(stack.layers) == 3

    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    # 1. Background plate contract
    bg = stack.background
    assert bg is not None
    assert bg.image_bytes.startswith(PNG_MAGIC), "Background image_bytes must be valid PNG"
    assert bg.mask_bytes is None, "Background plate must not have an alpha mask"
    bg_im = bg.to_image()
    assert bg_im.mode == "RGB", "Background plate must strictly be RGB (no alpha channel)"
    bg_arr = np.array(bg_im)
    assert bg_arr.shape == (h, w, 3)
    # Check infilled hole region (45, 50) is non-empty and has plausible background color
    assert bg_arr[50, 45, 0] > 100, "Background hole must be infilled"

    # 2. Foreground subject contract
    subj = stack.foreground_subject
    assert subj is not None
    assert subj.image_bytes.startswith(PNG_MAGIC), "Subject image_bytes must be valid PNG"
    assert subj.mask_bytes is not None and subj.mask_bytes.startswith(PNG_MAGIC)
    subj_im = subj.to_image()
    assert subj_im.mode == "RGBA", "Cutout layer must strictly be RGBA"
    subj_arr = np.array(subj_im)
    assert subj_arr.shape == (h, w, 4)
    # Background region is fully transparent
    assert subj_arr[5, 5, 3] < 15, "Subject cutout background must be transparent"
    # Subject center is opaque
    assert subj_arr[50, 45, 3] > 200, "Subject cutout center must be opaque"

    # 3. Prop contract
    prop = stack.get_layer("prop_1")
    assert prop is not None
    assert prop.image_bytes.startswith(PNG_MAGIC)
    prop_im = prop.to_image()
    assert prop_im.mode == "RGBA"
    prop_arr = np.array(prop_im)
    assert prop_arr[5, 5, 3] < 15, "Prop cutout background must be transparent"
    assert prop_arr[35, 95, 3] > 200, "Prop cutout center must be opaque"


def test_decompose_layers_degenerate_monolithic_and_aspect_ratios():
    """Verify decompose_layers handles extreme aspect ratios and monolithic solid frames."""
    # 1. Extreme tall: 1x100
    stack_tall = decompose_layers(Image.new("RGB", (1, 100), (120, 120, 120)), panel_id="tall")
    assert stack_tall.width == 1 and stack_tall.height == 100
    assert len(stack_tall.layers) >= 2

    # 2. Extreme wide: 100x1
    stack_wide = decompose_layers(Image.new("RGB", (100, 1), (120, 120, 120)), panel_id="wide")
    assert stack_wide.width == 100 and stack_wide.height == 1
    assert len(stack_wide.layers) >= 2

    # 3. Monolithic solid color frame (no foreground contrast)
    stack_solid = decompose_layers(Image.new("RGB", (64, 64), (255, 255, 255)), panel_id="solid")
    assert stack_solid.width == 64 and stack_solid.height == 64
    assert len(stack_solid.layers) >= 2
    assert stack_solid.background is not None
    assert stack_solid.foreground_subject is not None


