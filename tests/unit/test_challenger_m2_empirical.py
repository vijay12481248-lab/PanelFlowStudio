"""Empirical Challenge & Adversarial Stress Tests for Milestone M2.

Stress-tests:
1. Defringing behavior on high-contrast halo boundaries (bright white fringe on dark silhouettes, multi-color edges).
2. Semi-transparent edge preservation: smooth 0 < alpha < 255 transitions and mathematical color decontamination.
3. Robustness across diverse input formats: PIL Image (RGB, RGBA, L, 1, P, CMYK), raw bytes (PNG, JPEG, WebP),
   paths (Path, str), tiny images (4x4, 8x8), aspect ratio extremes (1x100, 100x1), and large images (2048x2048).
4. Automated mask extraction on single-object vs multi-object canvases with noise filtering and thresholding.
5. ComfyUI workflow registry integrity and offline fallback resilience.
"""
from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
import pytest

from engine.comfyui import ComfyWorkflowRegistry
from engine.original.art import ComfyRunner
from engine.original.rigging import (
    MattingResult,
    defringe_alpha,
    extract_subject_and_prop_masks,
    guided_filter_alpha,
    remove_background,
)


# ============================================================================
# 1. Defringing on High-Contrast Halo Boundaries
# ============================================================================

def test_defringe_bright_white_halo_on_black_silhouette():
    """Adversarial Test: Defringing a severe bright white halo around a pure black silhouette.

    Constructs a pure black foreground silhouette [0, 0, 0] with an artificial high-contrast
    white halo [255, 255, 255] and semi-transparent alpha transition (alpha = 120).
    Verifies that defringe_alpha completely replaces the white fringe with authentic
    black foreground pigment [0, 0, 0] while preserving the exact alpha value.
    """
    h, w = 40, 40
    rgb = np.full((h, w, 3), 255, dtype=np.uint8)  # White background
    alpha = np.zeros((h, w), dtype=np.uint8)

    # Pure black silhouette in center
    rgb[10:30, 10:30] = [0, 0, 0]
    alpha[10:30, 10:30] = 255

    # Artificial severe white halo along the perimeter: alpha=120, RGB=250 (white fringe)
    halo_coords = [
        (9, slice(10, 30)),
        (30, slice(10, 30)),
        (slice(10, 30), 9),
        (slice(10, 30), 30),
    ]
    for r_idx, c_idx in halo_coords:
        rgb[r_idx, c_idx] = [250, 250, 250]
        alpha[r_idx, c_idx] = 120

    decontam_rgb, out_alpha = defringe_alpha(rgb, alpha, threshold=240)

    # 1. Core black silhouette must be completely preserved
    np.testing.assert_array_equal(decontam_rgb[20, 20], [0, 0, 0])
    assert out_alpha[20, 20] == 255

    # 2. Decontaminated halo pixels must have white fringe replaced by pure black foreground
    for r_idx, c_idx in halo_coords:
        halo_slice_rgb = decontam_rgb[r_idx, c_idx]
        np.testing.assert_array_equal(halo_slice_rgb, 0, err_msg="White halo was not eliminated!")
        halo_slice_alpha = out_alpha[r_idx, c_idx]
        np.testing.assert_array_equal(halo_slice_alpha, 120, err_msg="Alpha transition was altered!")

    # 3. Composite over a dark background [15, 15, 15] and verify zero halo luminance spike
    bg = np.full((h, w, 3), 15, dtype=np.float32)
    fg_decontam = decontam_rgb.astype(np.float32)
    a_norm = out_alpha.astype(np.float32)[:, :, None] / 255.0

    comp_decontam = fg_decontam * a_norm + bg * (1.0 - a_norm)
    # At halo coordinate (9, 20): alpha is 120/255 ~= 0.47, so expected color is 0*0.47 + 15*0.53 ~= 8
    expected_halo_val = 15.0 * (1.0 - 120.0 / 255.0)
    assert np.allclose(comp_decontam[9, 20], expected_halo_val, atol=1.0)


def test_defringe_multi_colored_silhouette_boundary_preservation():
    """Adversarial Test: Defringing a silhouette with multiple distinct adjacent colored sections.

    A silhouette has a bright red left section [255, 0, 0] and a bright green right section [0, 255, 0].
    The boundary contains a uniform white halo.
    Verifies that the Euclidean distance transform routes authentic red pigment to the left
    boundary and green pigment to the right boundary with zero cross-bleeding.
    """
    h, w = 30, 40
    rgb = np.full((h, w, 3), 240, dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.uint8)

    # Left solid: Red
    rgb[10:25, 10:20] = [255, 0, 0]
    alpha[10:25, 10:20] = 255

    # Right solid: Green
    rgb[10:25, 20:30] = [0, 255, 0]
    alpha[10:25, 20:30] = 255

    # Top boundary contaminated with white halo [255, 255, 255] and alpha=100
    rgb[9, 10:30] = [255, 255, 255]
    alpha[9, 10:30] = 100

    decontam, out_a = defringe_alpha(rgb, alpha, threshold=240)

    # Near red section (col 12) must receive red [255, 0, 0]
    np.testing.assert_array_equal(decontam[9, 12], [255, 0, 0])
    # Near green section (col 28) must receive green [0, 255, 0]
    np.testing.assert_array_equal(decontam[9, 28], [0, 255, 0])
    # Alpha must be preserved as 100
    assert out_a[9, 12] == 100
    assert out_a[9, 28] == 100


def test_defringe_extreme_thresholds():
    """Adversarial Test: Behavior under extreme thresholds (threshold=1, threshold=255)."""
    h, w = 20, 20
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.uint8)

    rgb[5:15, 5:15] = [50, 100, 150]
    alpha[5:15, 5:15] = 200  # Max alpha is 200, strictly below default 240

    # With default threshold=240, it should fallback to alpha > 0
    decontam_fallback, out_a1 = defringe_alpha(rgb, alpha, threshold=240)
    assert decontam_fallback.shape == rgb.shape
    assert np.array_equal(out_a1, alpha)

    # With threshold=1, all pixels >= 1 are considered solid
    decontam_t1, out_a2 = defringe_alpha(rgb, alpha, threshold=1)
    np.testing.assert_array_equal(decontam_t1[10, 10], [50, 100, 150])

    # With threshold=255, none are >= 255, should fallback cleanly without crash
    decontam_t255, out_a3 = defringe_alpha(rgb, alpha, threshold=255)
    np.testing.assert_array_equal(decontam_t255[10, 10], [50, 100, 150])


def test_defringe_all_transparent_and_all_opaque():
    """Adversarial Test: defringe_alpha on degenerate inputs (all 0 alpha, all 255 alpha)."""
    # All transparent
    rgb_zero = np.full((16, 16, 3), 128, dtype=np.uint8)
    alpha_zero = np.zeros((16, 16), dtype=np.uint8)
    d_rgb1, d_a1 = defringe_alpha(rgb_zero, alpha_zero)
    np.testing.assert_array_equal(d_rgb1, rgb_zero)
    np.testing.assert_array_equal(d_a1, alpha_zero)

    # All opaque
    rgb_full = np.full((16, 16, 3), 42, dtype=np.uint8)
    alpha_full = np.full((16, 16), 255, dtype=np.uint8)
    d_rgb2, d_a2 = defringe_alpha(rgb_full, alpha_full)
    np.testing.assert_array_equal(d_rgb2, rgb_full)
    np.testing.assert_array_equal(d_a2, alpha_full)


# ============================================================================
# 2. Semi-Transparent Edge Preservation & Guided Filter Matting
# ============================================================================

def test_semi_transparent_alpha_monotonicity_and_smoothness():
    """Adversarial Test: Guided Filter smooths coarse transitions into strictly monotonic S-curves."""
    h, w = 32, 32
    # Continuous linear ramp guide image
    ramp = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    guide = np.dstack([ramp, ramp, ramp])

    # Coarse step binary mask at col 16
    raw_mask = np.zeros((h, w), dtype=np.uint8)
    raw_mask[:, 16:] = 255

    refined_alpha = guided_filter_alpha(guide, raw_mask, radius=4, eps=1e-4)

    # Verify output shape and type
    assert refined_alpha.shape == (h, w)
    assert refined_alpha.dtype == np.uint8

    # Extract transition profile across the center row
    profile = refined_alpha[16, :]

    # 1. Monotonicity: transition must be strictly non-decreasing across the boundary
    diffs = np.diff(profile.astype(np.int32))
    assert np.all(diffs >= 0), f"Alpha profile is non-monotonic: {profile}"

    # 2. Intermediate semi-transparent values must exist (smooth anti-aliased transition)
    intermediates = (refined_alpha > 0) & (refined_alpha < 255)
    assert np.count_nonzero(intermediates) > 0, "No semi-transparent intermediate values produced!"

    # 3. Preservation of far interior regions
    assert profile[0] == 0
    assert profile[-1] == 255


def test_alpha_channel_immutability_during_defringing():
    """Adversarial Test: defringe_alpha guarantees 100% bit-exact alpha immutability."""
    h, w = 25, 25
    rgb = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    # Semi-transparent gradient alpha with diverse values
    alpha = np.linspace(0, 255, h * w, dtype=np.uint8).reshape((h, w))

    decontam_rgb, out_alpha = defringe_alpha(rgb, alpha)

    # Alpha must be 100% identical in every single pixel
    np.testing.assert_array_equal(out_alpha, alpha)


def test_guided_filter_numerical_stability():
    """Adversarial Test: Guided filter under extreme parameters (radius=0, radius=50, eps=1e-8, eps=1.0)."""
    h, w = 20, 20
    guide = np.full((h, w, 3), 128, dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.uint8)
    alpha[5:15, 5:15] = 255

    # radius=0 (boxFilter ksize 1x1)
    res_r0 = guided_filter_alpha(guide, alpha, radius=0, eps=1e-4)
    assert res_r0.shape == (h, w)
    assert not np.isnan(res_r0).any()

    # radius=50 (larger than image dimensions 20x20)
    res_r50 = guided_filter_alpha(guide, alpha, radius=50, eps=1e-4)
    assert res_r50.shape == (h, w)
    assert not np.isnan(res_r50).any()

    # eps=1e-8 (near zero)
    res_eps_tiny = guided_filter_alpha(guide, alpha, radius=4, eps=1e-8)
    assert not np.isnan(res_eps_tiny).any()

    # eps=1.0 (large regularization)
    res_eps_large = guided_filter_alpha(guide, alpha, radius=4, eps=1.0)
    assert not np.isnan(res_eps_large).any()


# ============================================================================
# 3. Robustness on Diverse Input Formats & Dimensions
# ============================================================================

@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L", "1", "P", "CMYK"])
def test_remove_background_pil_modes(mode: str):
    """Adversarial Test: remove_background handles all standard PIL modes seamlessly."""
    w, h = 64, 64
    base = Image.new(mode, (w, h))
    # If mode is RGBA, add transparency to test refinement path
    if mode == "RGBA":
        arr = np.zeros((h, w, 4), dtype=np.uint8)
        arr[16:48, 16:48] = [200, 100, 50, 255]
        base = Image.fromarray(arr, "RGBA")

    res = remove_background(base, runner=None, defringe=True)
    assert isinstance(res, MattingResult)
    assert res.width == w
    assert res.height == h
    assert res.has_alpha is True
    assert res.halo_free is True

    # Validate output RGBA image
    out_im = res.to_image()
    assert out_im.size == (w, h)
    assert out_im.mode == "RGBA"

    # Validate mask image
    mask_im = res.to_mask_image()
    assert mask_im.size == (w, h)
    assert mask_im.mode == "L"


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_remove_background_raw_bytes(fmt: str):
    """Adversarial Test: remove_background accepts encoded raw bytes in multiple image codecs."""
    w, h = 48, 48
    im = Image.new("RGB", (w, h), (180, 180, 180))
    draw_np = np.array(im)
    cv2.circle(draw_np, (24, 24), 12, (50, 60, 70), -1)
    test_im = Image.fromarray(draw_np)

    buf = io.BytesIO()
    test_im.save(buf, format=fmt)
    raw_bytes = buf.getvalue()

    res = remove_background(raw_bytes, runner=None, defringe=True)
    assert res.width == w
    assert res.height == h
    assert res.has_alpha is True


def test_remove_background_paths(tmp_path: Path):
    """Adversarial Test: remove_background accepts both Path and str paths."""
    w, h = 40, 40
    im = Image.new("RGB", (w, h), (180, 180, 180))
    p = tmp_path / "test_path_char.png"
    im.save(p, format="PNG")

    # pathlib.Path
    res_path = remove_background(p)
    assert res_path.width == w

    # str
    res_str = remove_background(str(p))
    assert res_str.width == w


@pytest.mark.parametrize("dims", [(4, 4), (8, 8), (1, 64), (64, 1), (128, 128)])
def test_remove_background_extreme_dimensions(dims: tuple[int, int]):
    """Adversarial Test: remove_background survives extreme aspect ratios and tiny scales."""
    w, h = dims
    im = Image.new("RGB", (w, h), (160, 160, 160))
    res = remove_background(im, runner=None, defringe=True)
    assert res.width == w
    assert res.height == h
    assert res.has_alpha is True


def test_remove_background_large_dimension_performance():
    """Adversarial Test: remove_background on large 2048x2048 canvas executes stably without OOM."""
    w, h = 2048, 2048
    im = Image.new("RGB", (w, h), (180, 180, 180))
    res = remove_background(im, runner=None, defringe=True)
    assert res.width == w
    assert res.height == h
    assert res.has_alpha is True
    assert len(res.rgba_bytes) > 0


def test_remove_background_invalid_input_type():
    """Adversarial Test: remove_background raises TypeError on non-image types."""
    with pytest.raises(TypeError, match="Unsupported image type"):
        remove_background(12345)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Unsupported image type"):
        remove_background(["not_an_image"])  # type: ignore[arg-type]


# ============================================================================
# 4. Automated Mask Extraction on Single-Object vs Multi-Object Canvases
# ============================================================================

def test_mask_extraction_single_object():
    """Adversarial Test: Single-object canvas cleanly isolates subject with empty prop mask."""
    w, h = 100, 100
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    cv2.circle(arr, (50, 50), 25, (255, 0, 0, 255), -1)
    im = Image.fromarray(arr, "RGBA")

    masks = extract_subject_and_prop_masks(im)
    assert set(masks.keys()) == {"subject", "prop", "background", "foreground"}

    subj_np = np.array(masks["subject"])
    prop_np = np.array(masks["prop"])
    bg_np = np.array(masks["background"])

    # Subject must contain foreground
    assert np.count_nonzero(subj_np > 127) > 1500
    # Prop must be completely empty
    assert np.count_nonzero(prop_np) == 0
    # Background must be active outside the subject
    assert bg_np[5, 5] == 255
    assert bg_np[50, 50] == 0


def test_mask_extraction_multi_object_multiple_props():
    """Adversarial Test: Canvas with primary character and 3 distinct props."""
    w, h = 200, 200
    arr = np.zeros((h, w, 4), dtype=np.uint8)

    # 1. Character (largest component: circle r=40, area ~5000 px)
    cv2.circle(arr, (60, 100), 40, (255, 0, 0, 255), -1)

    # 2. Prop 1: Sword (bar 10x80, area ~800 px)
    cv2.rectangle(arr, (130, 20), (140, 100), (0, 255, 0, 255), -1)

    # 3. Prop 2: Shield (circle r=15, area ~700 px)
    cv2.circle(arr, (160, 140), 15, (0, 0, 255, 255), -1)

    # 4. Prop 3: Floating orb (circle r=10, area ~314 px)
    cv2.circle(arr, (180, 50), 10, (255, 255, 0, 255), -1)

    im = Image.fromarray(arr, "RGBA")
    masks = extract_subject_and_prop_masks(im)

    subj_np = np.array(masks["subject"])
    prop_np = np.array(masks["prop"])
    bg_np = np.array(masks["background"])

    # Character is subject
    assert np.count_nonzero(subj_np > 127) > 4000
    # Center of character has subject=255 and prop=0
    assert subj_np[100, 60] == 255
    assert prop_np[100, 60] == 0

    # All three props are captured in prop mask
    assert prop_np[60, 135] > 200   # Sword (anti-aliased foreground)
    assert prop_np[140, 160] > 200  # Shield
    assert prop_np[50, 180] > 200   # Orb

    # Zero overlap between subject and prop
    overlap = np.logical_and(subj_np > 127, prop_np > 127)
    assert np.count_nonzero(overlap) == 0

    # Background is active at borders
    assert bg_np[10, 10] == 255


def test_mask_extraction_subthreshold_noise_filtering():
    """Adversarial Test: Noise speckles (< 50 px) are filtered out of both subject and prop."""
    w, h = 100, 100
    arr = np.zeros((h, w, 4), dtype=np.uint8)

    # Main subject
    cv2.circle(arr, (50, 50), 30, (255, 0, 0, 255), -1)

    # Noise speckle 1: 3x3 box (9 px < 50 px)
    cv2.rectangle(arr, (5, 5), (8, 8), (255, 255, 255, 255), -1)

    # Noise speckle 2: 4x4 box (16 px < 50 px)
    cv2.rectangle(arr, (90, 90), (94, 94), (255, 255, 255, 255), -1)

    im = Image.fromarray(arr, "RGBA")
    masks = extract_subject_and_prop_masks(im)

    subj_np = np.array(masks["subject"])
    prop_np = np.array(masks["prop"])
    bg_np = np.array(masks["background"])

    # Main subject is captured
    assert subj_np[50, 50] == 255

    # Noise speckles are absent from subject AND prop
    assert subj_np[6, 6] == 0
    assert prop_np[6, 6] == 0
    assert subj_np[92, 92] == 0
    assert prop_np[92, 92] == 0

    # Noise speckles are treated as background
    assert bg_np[6, 6] == 255
    assert bg_np[92, 92] == 255


def test_mask_extraction_blank_canvas_zero_foreground():
    """Adversarial Test: extract_subject_and_prop_masks handles zero-foreground canvas gracefully."""
    w, h = 60, 60
    # Fully transparent canvas
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    im = Image.fromarray(arr, "RGBA")

    masks = extract_subject_and_prop_masks(im)
    assert isinstance(masks, dict)
    assert set(masks.keys()) == {"subject", "prop", "background", "foreground"}

    subj_np = np.array(masks["subject"])
    prop_np = np.array(masks["prop"])
    bg_np = np.array(masks["background"])

    assert np.count_nonzero(subj_np) == 0
    assert np.count_nonzero(prop_np) == 0
    assert np.count_nonzero(bg_np) == w * h


# ============================================================================
# 5. ComfyUI Workflow Registry & Offline Fallback Rigor
# ============================================================================

def test_comfyui_matting_workflow_structure_and_patch_slots():
    """Adversarial Test: Validates anime_alpha_matting workflow file and registry contracts."""
    reg = ComfyWorkflowRegistry()
    assert "anime_alpha_matting" in reg._entries

    entry = reg.metadata("anime_alpha_matting")
    assert entry["sha256"] == "444c649f842ca35929a9a6f8ca425106c73779e4f2423b3c3d11d2b90cf9ecd2"

    wf, checksum = reg.load("anime_alpha_matting")
    assert checksum == entry["sha256"]
    assert "1" in wf  # LoadImage
    assert "2" in wf  # LoadBackgroundRemovalModel
    assert "3" in wf  # RemoveBackground
    assert "4" in wf  # JoinImageWithAlpha
    assert "5" in wf  # SaveImage

    # Verify model file matches declaration
    assert wf["2"]["inputs"]["bg_removal_name"] == "birefnet-general.safetensors"


def test_comfy_runner_offline_matting_integration():
    """Adversarial Test: ComfyRunner falls back seamlessly to local engine without live ComfyUI."""
    runner = ComfyRunner(engine="sdxl")
    # Runner preflight marks matting_wf as None when offline or models absent
    assert runner.matting_wf is None
    assert runner.matting_ready is False

    # Test remove_background execution through runner
    test_im = Image.new("RGB", (64, 64), (180, 180, 180))
    draw_np = np.array(test_im)
    cv2.circle(draw_np, (32, 32), 16, (50, 60, 70), -1)
    test_im = Image.fromarray(draw_np)

    res_bytes = runner.remove_background(test_im, defringe=True)
    assert isinstance(res_bytes, bytes)
    out_im = Image.open(io.BytesIO(res_bytes))
    assert out_im.mode == "RGBA"
    assert out_im.size == (64, 64)
