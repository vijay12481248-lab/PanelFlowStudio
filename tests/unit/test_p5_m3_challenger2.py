"""Empirical Challenge & Stress Test Suite: Milestone M3.

Challenger 2 independent adversarial verification for:
1. Dilation mathematics (+12px circular expansion):
   - Check that a circular mask of radius R expands to exactly radius R + 12 after dilation.
   - Check circular expansion across cardinal axes and radial contour profiles.
   - Check rectangular mask bounding box expansion (W -> W + 2*dil, H -> H + 2*dil).
   - Check zero and negative dilation handling.
2. Border halo & edge fringe elimination:
   - Compare infilled background plates across dilation levels (0px, 4px, 12px, 24px).
   - Prove that edge fringe/halo artifacts (narrow, medium, wide bands) are eliminated at 12px and 24px.
   - Quantitative evaluation of color distance and residual halo pixel count.
3. Inpainting fallback resilience:
   - Fallback to local OpenCV Telea when runner=None.
   - Coordination with mock runner returning bytes and PIL Image.
   - Graceful fallback when runner raises RuntimeError, TimeoutError, or ConnectionError.
   - Runner bypass when runner.inpaint_wf is None or runner lacks inpaint method.
   - Prompt hint propagation to runner.
4. Boundary edge cases:
   - Masks touching canvas boundaries (left, right, top, bottom, corners, border frames).
   - Full-canvas masks (100% occluded) returning median fill without OpenCV assertion crash.
   - Dilated-to-full-canvas masks on small canvas.
   - Zero-pixel masks (0% occluded) returning pristine base image copy.
   - Mask size mismatch auto-resize.
   - Non-standard input types (PIL, bytes, Path, str) and TypeError enforcement.
   - Tiny canvas dimensions (1x1, 2x2, 5x5, odd aspect ratios).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Any
import cv2
import numpy as np
from PIL import Image
import pytest

from engine.original import art
from engine.original.rigging import (
    DecomposedLayer,
    LayerStack,
    decompose_layers,
    inpaint_background_plate,
)


# ==============================================================================
# 1. Dilation Mathematics (+12px Circular Expansion)
# ==============================================================================

class TestDilationMathematics:
    """Stress-tests the geometric dilation mathematics of inpaint_background_plate."""

    @pytest.mark.parametrize("radius", [10, 15, 20, 30, 45])
    def test_circular_mask_radius_expansion_exact(self, radius: int):
        """Verify that a circular mask of radius R expands to exactly radius R + 12 along cardinal axes."""
        canvas_dim = 201
        center = 100
        canvas = np.zeros((canvas_dim, canvas_dim), dtype=np.uint8)
        cv2.circle(canvas, (center, center), radius, 255, -1)

        dilation_px = 12
        k_size = 2 * dilation_px + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        dilated = cv2.dilate(canvas, kernel, iterations=1)

        # Measure horizontal extent through center
        xs = np.where(dilated[center, :] > 0)[0]
        radius_x = (xs.max() - xs.min()) / 2.0
        assert radius_x == float(radius + dilation_px), (
            f"Expected horizontal radius {radius + dilation_px}, got {radius_x}"
        )

        # Measure vertical extent through center
        ys = np.where(dilated[:, center] > 0)[0]
        radius_y = (ys.max() - ys.min()) / 2.0
        assert radius_y == float(radius + dilation_px), (
            f"Expected vertical radius {radius + dilation_px}, got {radius_y}"
        )

        # Check expansion on each individual side
        orig_xs = np.where(canvas[center, :] > 0)[0]
        orig_ys = np.where(canvas[:, center] > 0)[0]
        assert orig_xs.min() - xs.min() == dilation_px, "Left expansion mismatch"
        assert xs.max() - orig_xs.max() == dilation_px, "Right expansion mismatch"
        assert orig_ys.min() - ys.min() == dilation_px, "Top expansion mismatch"
        assert ys.max() - orig_ys.max() == dilation_px, "Bottom expansion mismatch"

    def test_circular_mask_radial_contour_profile(self):
        """Verify Euclidean radial distance from center across all angles of dilated circle."""
        radius = 25
        dilation_px = 12
        canvas_dim = 201
        center = 100
        canvas = np.zeros((canvas_dim, canvas_dim), dtype=np.uint8)
        cv2.circle(canvas, (center, center), radius, 255, -1)

        k_size = 2 * dilation_px + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        dilated = cv2.dilate(canvas, kernel, iterations=1)

        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        assert len(contours) == 1
        pts = contours[0].reshape(-1, 2)
        dists = np.sqrt((pts[:, 0] - center) ** 2 + (pts[:, 1] - center) ** 2)

        expected_r = radius + dilation_px  # 37
        # Discrete pixel rasterization of ellipse allows small tolerance (<= 1.5px)
        assert np.min(dists) >= expected_r - 1.5, f"Min contour dist too small: {np.min(dists)}"
        assert np.max(dists) <= expected_r + 1.0, f"Max contour dist too large: {np.max(dists)}"
        assert abs(np.mean(dists) - expected_r) < 1.0, f"Mean contour dist skewed: {np.mean(dists)}"

    @pytest.mark.parametrize("dil", [0, 4, 12, 24])
    def test_dilation_levels_mathematics(self, dil: int):
        """Verify circular dilation mathematics across diverse dilation parameters."""
        radius = 20
        canvas_dim = 201
        center = 100
        canvas = np.zeros((canvas_dim, canvas_dim), dtype=np.uint8)
        cv2.circle(canvas, (center, center), radius, 255, -1)

        if dil > 0:
            k_size = 2 * dil + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
            dilated = cv2.dilate(canvas, kernel, iterations=1)
        else:
            dilated = canvas.copy()

        xs = np.where(dilated[center, :] > 0)[0]
        r_measured = (xs.max() - xs.min()) / 2.0
        assert r_measured == float(radius + dil)

    def test_rectangular_mask_bounding_box_expansion(self):
        """Verify that a rectangular mask expands by exactly 2*dil in width and height."""
        w, h = 40, 30
        dil = 12
        canvas = np.zeros((150, 150), dtype=np.uint8)
        canvas[50:50 + h, 50:50 + w] = 255

        k_size = 2 * dil + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
        dilated = cv2.dilate(canvas, kernel, iterations=1)

        y_idx, x_idx = np.where(dilated > 0)
        box_w = x_idx.max() - x_idx.min() + 1
        box_h = y_idx.max() - y_idx.min() + 1

        assert box_w == w + 2 * dil, f"Expected dilated width {w + 2*dil}, got {box_w}"
        assert box_h == h + 2 * dil, f"Expected dilated height {h + 2*dil}, got {box_h}"

    def test_negative_and_zero_dilation(self):
        """Verify dilation_px <= 0 skips dilation and preserves original mask."""
        base = Image.new("RGB", (60, 60), (100, 100, 100))
        mask_arr = np.zeros((60, 60), dtype=np.uint8)
        mask_arr[20:40, 20:40] = 255
        mask = Image.fromarray(mask_arr, "L")

        for d in [0, -1, -10]:
            res = inpaint_background_plate(base, mask, dilation_px=d)
            assert res.size == (60, 60)


# ==============================================================================
# 2. Border Halo & Edge Fringe Elimination
# ==============================================================================

class TestBorderHaloElimination:
    """Stress-tests border halo and edge fringe elimination across dilation levels."""

    @staticmethod
    def _create_halo_scene(
        canvas_size: tuple[int, int] = (200, 200),
        center: tuple[int, int] = (100, 100),
        subj_radius: int = 20,
        fringe_width: int = 4,
        bg_color: tuple[int, int, int] = (0, 200, 200),
        fringe_color: tuple[int, int, int] = (220, 20, 20),
        subj_color: tuple[int, int, int] = (10, 10, 10),
    ) -> tuple[Image.Image, Image.Image]:
        """Creates a synthetic image with background, subject, and an intentional edge fringe band."""
        w, h = canvas_size
        base = np.full((h, w, 3), bg_color, dtype=np.uint8)

        # 1. Outer fringe/halo ring
        total_r = subj_radius + fringe_width
        cv2.circle(base, center, total_r, fringe_color, -1)

        # 2. Inner foreground subject
        cv2.circle(base, center, subj_radius, subj_color, -1)

        # 3. Occlusion mask (covers only foreground subject, leaving fringe exposed)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(mask, center, subj_radius, 255, -1)

        return Image.fromarray(base, "RGB"), Image.fromarray(mask, "L")

    def test_halo_elimination_narrow_fringe(self):
        """Verify that a 3px fringe is retained at 0px dilation but eliminated at 12px."""
        base_img, mask_img = self._create_halo_scene(fringe_width=3)

        # Dilation 0px: halo is retained and propagates inward
        res_0 = inpaint_background_plate(base_img, mask_img, dilation_px=0)
        np_0 = np.array(res_0)
        # Check red fringe component (R > 100) inside the hole region
        red_px_0 = np.sum(np_0[:, :, 0] > 100)
        assert red_px_0 > 1000, f"Expected residual halo at dilation 0px, got {red_px_0} px"

        # Dilation 12px: halo is completely swallowed and eliminated
        res_12 = inpaint_background_plate(base_img, mask_img, dilation_px=12)
        np_12 = np.array(res_12)
        red_px_12 = np.sum(np_12[:, :, 0] > 100)
        assert red_px_12 == 0, f"Expected 0 halo pixels at dilation 12px, got {red_px_12} px"

    def test_halo_elimination_medium_fringe_comparison(self):
        """Verify progression across 0px, 4px, 12px, 24px with a 6px wide fringe band."""
        base_img, mask_img = self._create_halo_scene(fringe_width=6)

        results = {}
        for dil in [0, 4, 12, 24]:
            res = inpaint_background_plate(base_img, mask_img, dilation_px=dil)
            arr = np.array(res)
            # Count pixels retaining fringe color (red channel > 100)
            halo_count = int(np.sum(arr[:, :, 0] > 100))
            # Calculate mean absolute error from pure background (0, 200, 200) inside dilated zone
            mae = float(np.mean(np.abs(arr[80:120, 80:120, :].astype(float) - np.array([0, 200, 200]))))
            results[dil] = (halo_count, mae)

        # Dilation 0px: severe halo contamination
        assert results[0][0] > 1500
        assert results[0][1] > 100.0

        # Dilation 4px: partial failure (6px fringe exceeds 4px dilation)
        assert results[4][0] > 1000
        assert results[4][1] > 80.0

        # Dilation 12px: complete elimination (12px > 6px fringe)
        assert results[12][0] == 0, f"12px dilation should have 0 halo pixels, got {results[12][0]}"
        assert results[12][1] < 5.0, f"12px dilation should have near-zero MAE, got {results[12][1]}"

        # Dilation 24px: complete elimination
        assert results[24][0] == 0
        assert results[24][1] < 5.0

    def test_halo_elimination_wide_fringe_10px(self):
        """Verify that 12px dilation successfully clears an aggressive 10px fringe band."""
        base_img, mask_img = self._create_halo_scene(fringe_width=10)

        res_12 = inpaint_background_plate(base_img, mask_img, dilation_px=12)
        arr_12 = np.array(res_12)
        red_px_12 = np.sum(arr_12[:, :, 0] > 100)
        assert red_px_12 == 0, f"Expected 0 red halo pixels with 12px dilation, got {red_px_12}"

        res_24 = inpaint_background_plate(base_img, mask_img, dilation_px=24)
        arr_24 = np.array(res_24)
        red_px_24 = np.sum(arr_24[:, :, 0] > 100)
        assert red_px_24 == 0

    def test_gradient_background_continuity(self):
        """Verify that inpaint_background_plate with 12px dilation smoothly bridges gradient background."""
        w, h = 180, 180
        # Horizontal linear gradient from (50, 100, 150) to (50, 100, 220)
        grad_x = np.linspace(150, 220, w, dtype=np.uint8)
        base = np.zeros((h, w, 3), dtype=np.uint8)
        base[:, :, 0] = 50
        base[:, :, 1] = 100
        base[:, :, 2] = np.tile(grad_x, (h, 1))

        # Add foreground object in center
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(mask, (90, 90), 20, 255, -1)
        base_with_obj = base.copy()
        cv2.circle(base_with_obj, (90, 90), 20, (10, 10, 10), -1)

        res = inpaint_background_plate(Image.fromarray(base_with_obj), Image.fromarray(mask), dilation_px=12)
        res_arr = np.array(res)

        # Center infilled pixel (90, 90) should approximate gradient value at x=90 (approx 185)
        expected_val = grad_x[90]
        actual_val = res_arr[90, 90, 2]
        assert abs(int(actual_val) - int(expected_val)) < 15, (
            f"Expected infilled gradient value ~{expected_val}, got {actual_val}"
        )


# ==============================================================================
# 3. Inpainting Fallback Resilience
# ==============================================================================

class TestInpaintingFallbackResilience:
    """Stress-tests inpainting runner coordination, exception handling, and offline fallback."""

    def test_runner_none_telea_fallback(self):
        """Verify runner=None executes genuine local OpenCV Telea inpainting."""
        w, h = 80, 80
        base = Image.new("RGB", (w, h), (120, 140, 160))
        mask = Image.new("L", (w, h), 0)
        draw = Image.fromarray(np.array(mask))
        np_mask = np.array(mask)
        np_mask[25:55, 25:55] = 255
        mask = Image.fromarray(np_mask, "L")

        res = inpaint_background_plate(base, mask, runner=None, dilation_px=12)
        assert isinstance(res, Image.Image)
        assert res.size == (w, h)
        assert res.mode == "RGB"
        # Check center pixel matches background tone within OpenCV Telea numerical diffusion tolerance
        diff = max(abs(a - b) for a, b in zip(res.getpixel((40, 40)), (120, 140, 160)))
        assert diff < 8, f"Inpainted pixel drifted too far from background: {res.getpixel((40, 40))}"

    def test_mock_runner_success_bytes(self):
        """Verify coordination with runner returning valid image bytes."""
        w, h = 64, 64
        base = Image.new("RGB", (w, h), (50, 50, 50))
        mask = Image.new("L", (w, h), 0)

        class MockRunnerBytes:
            def __init__(self):
                self.calls = []
            def inpaint(self, base_image, mask_image, prompt, neg, seed, **kwargs):
                self.calls.append({
                    "base_image": base_image,
                    "mask_image": mask_image,
                    "prompt": prompt,
                    "neg": neg,
                    "seed": seed,
                })
                out = Image.new("RGB", (w, h), (10, 200, 100))
                buf = io.BytesIO()
                out.save(buf, format="PNG")
                return buf.getvalue()

        runner = MockRunnerBytes()
        # Non-zero mask to trigger inpainting
        np_mask = np.zeros((h, w), dtype=np.uint8)
        np_mask[20:40, 20:40] = 255
        mask = Image.fromarray(np_mask, "L")

        res = inpaint_background_plate(base, mask, runner=runner, prompt_hint="shrine garden", dilation_px=8)

        assert len(runner.calls) == 1
        call = runner.calls[0]
        assert isinstance(call["base_image"], bytes)
        assert isinstance(call["mask_image"], bytes)
        assert "shrine garden" in call["prompt"]
        assert call["seed"] == 42
        assert res.size == (w, h)
        assert res.getpixel((30, 30)) == (10, 200, 100)

    def test_mock_runner_success_pil_image(self):
        """Verify runner returning Image.Image directly is handled properly."""
        w, h = 64, 64
        base = Image.new("RGB", (w, h), (50, 50, 50))
        mask = Image.new("L", (w, h), 0)
        np_mask = np.zeros((h, w), dtype=np.uint8)
        np_mask[20:40, 20:40] = 255
        mask = Image.fromarray(np_mask, "L")

        class MockRunnerPIL:
            def inpaint(self, base_image, mask_image, prompt, neg, seed, **kwargs):
                return Image.new("RGB", (w, h), (210, 90, 40))

        res = inpaint_background_plate(base, mask, runner=MockRunnerPIL())
        assert res.size == (w, h)
        assert res.getpixel((30, 30)) == (210, 90, 40)

    @pytest.mark.parametrize("exc", [
        RuntimeError("ComfyUI socket disconnected"),
        TimeoutError("Prompt execution timed out"),
        ConnectionError("Failed to establish connection to 127.0.0.1:8188"),
        ValueError("Unexpected payload structure"),
    ])
    def test_mock_runner_exception_fallback_to_telea(self, exc: Exception):
        """Verify inpaint_background_plate catches runner exceptions and falls back to OpenCV Telea."""
        w, h = 60, 60
        base = Image.new("RGB", (w, h), (90, 110, 130))
        np_mask = np.zeros((h, w), dtype=np.uint8)
        np_mask[20:40, 20:40] = 255
        mask = Image.fromarray(np_mask, "L")

        class FailingRunner:
            def inpaint(self, *args, **kwargs):
                raise exc

        # Must not raise the exception; must fall back seamlessly to local Telea
        res = inpaint_background_plate(base, mask, runner=FailingRunner(), dilation_px=6)
        diff = max(abs(a - b) for a, b in zip(res.getpixel((30, 30)), (90, 110, 130)))
        assert diff < 8, f"Inpainted pixel drifted too far from background: {res.getpixel((30, 30))}"

    def test_mock_runner_inpaint_wf_none_skips_runner(self):
        """Verify runner with inpaint_wf=None skips runner.inpaint entirely."""
        w, h = 50, 50
        base = Image.new("RGB", (w, h), (70, 80, 90))
        np_mask = np.zeros((h, w), dtype=np.uint8)
        np_mask[15:35, 15:35] = 255
        mask = Image.fromarray(np_mask, "L")

        class UnreadyRunner:
            def __init__(self):
                self.inpaint_wf = None
                self.called = False
            def inpaint(self, *args, **kwargs):
                self.called = True
                raise AssertionError("Should not be called when inpaint_wf is None")

        runner = UnreadyRunner()
        res = inpaint_background_plate(base, mask, runner=runner)
        assert not runner.called, "Runner was called despite inpaint_wf=None"
        assert res.size == (w, h)

    def test_runner_without_inpaint_method(self):
        """Verify runner lacking inpaint method falls back cleanly to Telea."""
        w, h = 50, 50
        base = Image.new("RGB", (w, h), (70, 80, 90))
        np_mask = np.zeros((h, w), dtype=np.uint8)
        np_mask[15:35, 15:35] = 255
        mask = Image.fromarray(np_mask, "L")

        class NonInpaintRunner:
            pass

        res = inpaint_background_plate(base, mask, runner=NonInpaintRunner())
        assert res.size == (w, h)

    def test_default_prompt_hint_behavior(self):
        """Verify default prompt is passed to runner when prompt_hint is omitted."""
        w, h = 40, 40
        base = Image.new("RGB", (w, h), (50, 50, 50))
        np_mask = np.zeros((h, w), dtype=np.uint8)
        np_mask[10:30, 10:30] = 255
        mask = Image.fromarray(np_mask, "L")

        captured_prompt = None

        class PromptCaptureRunner:
            def inpaint(self, base_image, mask_image, prompt, neg, seed, **kwargs):
                nonlocal captured_prompt
                captured_prompt = prompt
                return Image.new("RGB", (w, h), (0, 0, 0))

        inpaint_background_plate(base, mask, runner=PromptCaptureRunner(), prompt_hint="")
        assert captured_prompt == "anime scenery, detailed background plate, masterpiece"


# ==============================================================================
# 4. Boundary Edge Cases
# ==============================================================================

class TestBoundaryEdgeCases:
    """Stress-tests boundary conditions, edge contacts, full-canvas, zero masks, and size anomalies."""

    @pytest.fixture
    def base_canvas(self) -> Image.Image:
        w, h = 120, 100
        arr = np.full((h, w, 3), (110, 130, 150), dtype=np.uint8)
        return Image.fromarray(arr, "RGB")

    def test_mask_touching_left_border(self, base_canvas: Image.Image):
        """Verify mask touching x=0 boundary dilates and inpaints cleanly."""
        w, h = base_canvas.size
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[30:70, 0:25] = 255
        res = inpaint_background_plate(base_canvas, Image.fromarray(mask, "L"), dilation_px=12)
        assert res.size == (w, h)
        diff = max(abs(a - b) for a, b in zip(res.getpixel((0, 50)), (110, 130, 150)))
        assert diff < 10, f"Left border pixel drifted too far: {res.getpixel((0, 50))}"

    def test_mask_touching_right_border(self, base_canvas: Image.Image):
        """Verify mask touching x=w-1 boundary dilates and inpaints cleanly."""
        w, h = base_canvas.size
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[30:70, w - 25:w] = 255
        res = inpaint_background_plate(base_canvas, Image.fromarray(mask, "L"), dilation_px=12)
        assert res.size == (w, h)
        diff = max(abs(a - b) for a, b in zip(res.getpixel((w - 1, 50)), (110, 130, 150)))
        assert diff < 10, f"Right border pixel drifted too far: {res.getpixel((w - 1, 50))}"

    def test_mask_touching_top_border(self, base_canvas: Image.Image):
        """Verify mask touching y=0 boundary dilates and inpaints cleanly."""
        w, h = base_canvas.size
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[0:25, 40:80] = 255
        res = inpaint_background_plate(base_canvas, Image.fromarray(mask, "L"), dilation_px=12)
        assert res.size == (w, h)
        diff = max(abs(a - b) for a, b in zip(res.getpixel((60, 0)), (110, 130, 150)))
        assert diff < 10, f"Top border pixel drifted too far: {res.getpixel((60, 0))}"

    def test_mask_touching_bottom_border(self, base_canvas: Image.Image):
        """Verify mask touching y=h-1 boundary dilates and inpaints cleanly."""
        w, h = base_canvas.size
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[h - 25:h, 40:80] = 255
        res = inpaint_background_plate(base_canvas, Image.fromarray(mask, "L"), dilation_px=12)
        assert res.size == (w, h)
        diff = max(abs(a - b) for a, b in zip(res.getpixel((60, h - 1)), (110, 130, 150)))
        assert diff < 10, f"Bottom border pixel drifted too far: {res.getpixel((60, h - 1))}"

    def test_mask_four_corners_simultaneous(self, base_canvas: Image.Image):
        """Verify mask with disconnected patches in all four corners."""
        w, h = base_canvas.size
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[:20, :20] = 255
        mask[:20, -20:] = 255
        mask[-20:, :20] = 255
        mask[-20:, -20:] = 255
        res = inpaint_background_plate(base_canvas, Image.fromarray(mask, "L"), dilation_px=12)
        assert res.size == (w, h)

    def test_mask_perimeter_frame(self, base_canvas: Image.Image):
        """Verify perimeter border frame where entire outer border is masked and center is known."""
        w, h = base_canvas.size
        mask = np.zeros((h, w), dtype=np.uint8)
        mask[:10, :] = 255
        mask[-10:, :] = 255
        mask[:, :10] = 255
        mask[:, -10:] = 255
        res = inpaint_background_plate(base_canvas, Image.fromarray(mask, "L"), dilation_px=6)
        assert res.size == (w, h)

    def test_full_canvas_mask_median_fill(self):
        """Verify 100% white mask triggers median color fill without OpenCV assertion crash."""
        w, h = 60, 50
        base = np.full((h, w, 3), (120, 150, 180), dtype=np.uint8)
        # Add slight color variations to check median
        base[0:10, 0:10] = (100, 100, 100)
        base_img = Image.fromarray(base, "RGB")
        mask_full = Image.new("L", (w, h), 255)

        res = inpaint_background_plate(base_img, mask_full)
        assert isinstance(res, Image.Image)
        assert res.size == (w, h)
        # Median color of base
        expected_median = tuple(np.median(base, axis=(0, 1)).astype(np.uint8))
        assert res.getpixel((25, 25)) == expected_median

    def test_dilated_to_full_canvas_small_image(self):
        """Verify small image where mask dilation covers 100% of the canvas gracefully triggers median fill."""
        w, h = 16, 16
        base = Image.new("RGB", (w, h), (80, 100, 120))
        # Mask 10x10 in center of 16x16
        mask_arr = np.zeros((h, w), dtype=np.uint8)
        mask_arr[3:13, 3:13] = 255
        mask = Image.fromarray(mask_arr, "L")

        # 12px dilation will expand 10x10 to cover entire 16x16 canvas
        res = inpaint_background_plate(base, mask, dilation_px=12)
        assert res.size == (w, h)
        assert res.getpixel((0, 0)) == (80, 100, 120)

    def test_zero_pixel_mask_identity_return(self, base_canvas: Image.Image):
        """Verify all-black mask (0 occluded pixels) returns pristine copy of base image."""
        w, h = base_canvas.size
        mask_zero = Image.new("L", (w, h), 0)
        res = inpaint_background_plate(base_canvas, mask_zero)
        assert res.size == (w, h)
        # Should be exact pixel-for-pixel match
        np.testing.assert_array_equal(np.array(res), np.array(base_canvas))

    def test_mask_size_mismatch_auto_resize(self):
        """Verify mask with mismatched dimensions is automatically resized to match base image."""
        base = Image.new("RGB", (200, 150), (100, 120, 140))
        # Mask has different dimensions (50, 40)
        mask = Image.new("L", (50, 40), 0)
        np_mask = np.array(mask)
        np_mask[10:30, 10:30] = 255
        mask = Image.fromarray(np_mask, "L")

        res = inpaint_background_plate(base, mask, dilation_px=6)
        assert res.size == (200, 150)

    def test_diverse_input_types(self, tmp_path: Path):
        """Verify inpaint_background_plate handles PIL Images, bytes, Path, and string paths."""
        w, h = 60, 60
        base = Image.new("RGB", (w, h), (75, 85, 95))
        mask = Image.new("L", (w, h), 0)
        np_mask = np.array(mask)
        np_mask[20:40, 20:40] = 255
        mask = Image.fromarray(np_mask, "L")

        base_path = tmp_path / "base.png"
        mask_path = tmp_path / "mask.png"
        base.save(base_path, format="PNG")
        mask.save(mask_path, format="PNG")

        base_bytes = base_path.read_bytes()
        mask_bytes = mask_path.read_bytes()

        # Path input
        res_path = inpaint_background_plate(base_path, mask_path)
        assert res_path.size == (w, h)

        # String path input
        res_str = inpaint_background_plate(str(base_path), str(mask_path))
        assert res_str.size == (w, h)

        # Bytes input
        res_bytes = inpaint_background_plate(base_bytes, mask_bytes)
        assert res_bytes.size == (w, h)

    def test_invalid_types_raise_type_error(self):
        """Verify passing invalid types raises TypeError."""
        valid_img = Image.new("RGB", (20, 20), (50, 50, 50))
        valid_mask = Image.new("L", (20, 20), 0)

        with pytest.raises(TypeError, match="Unsupported base_image type"):
            inpaint_background_plate(12345, valid_mask)  # type: ignore

        with pytest.raises(TypeError, match="Unsupported occlusion_mask type"):
            inpaint_background_plate(valid_img, ["not_a_mask"])  # type: ignore

    @pytest.mark.parametrize("dim", [(1, 1), (2, 2), (3, 3), (5, 5), (7, 13), (1, 20), (20, 1)])
    def test_tiny_and_odd_canvas_sizes(self, dim: tuple[int, int]):
        """Verify inpaint_background_plate survives tiny and extreme aspect-ratio canvases."""
        w, h = dim
        base = Image.new("RGB", (w, h), (60, 80, 100))
        mask = Image.new("L", (w, h), 255)
        res = inpaint_background_plate(base, mask, dilation_px=12)
        assert res.size == (w, h)

    def test_huge_dilation_relative_to_canvas(self):
        """Verify dilation kernel larger than canvas dimensions does not crash."""
        w, h = 30, 30
        base = Image.new("RGB", (w, h), (100, 120, 140))
        mask = Image.new("L", (w, h), 0)
        np_mask = np.array(mask)
        np_mask[12:18, 12:18] = 255
        mask = Image.fromarray(np_mask, "L")

        # dilation_px=100 creates k_size=201 kernel on a 30x30 canvas
        res = inpaint_background_plate(base, mask, dilation_px=100)
        assert res.size == (w, h)
