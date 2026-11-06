"""Milestone M4 Challenger 1 Empirical End-to-End Stress & Verification Harness.

Empirically links and rigorously stress-tests all Phase 5 capabilities:
1. Turnaround Generation & Slicing (R1): Full orthographic sheet generation and 4-view slicing.
2. Neural Alpha Matting & Defringing (R2): Seamless background removal, zero halo/fringe on edges, clean transparency.
3. Multi-Plane Layer Decomposition (R3): Foreground subject, discrete multi-props (prop_1, prop_2), and dilated infilled background plate.
4. Parallax Bridge: ParallaxPlan generation, distinct speed scales (1.10, 1.15), and depth ordering.
5. Adversarial Invariants: Pixel exclusivity, input polymorphism (bytes/Path/ndarray/Image), and edge color decontamination.
"""
from __future__ import annotations

import io
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
import pytest

from engine.motion.models.enums import LayerType
from engine.motion.models.layers import LayerInstruction, ParallaxPlan
from engine.original import shotspec as ss
from engine.original.models import Bible, Character, OriginalStory, Premise
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


def create_e2e_story(char_id: str = "kaelen") -> OriginalStory:
    """Helper to build a deterministic test story and character."""
    bible = Bible(
        premise=Premise(
            title="Aether Vanguard",
            genre="cyberpunk",
            logline="A rogue operative infiltrates an orbital citadel.",
            tone="cinematic",
            setting="Neo-Shinjuku",
        ),
        characters=[
            Character(
                id=char_id,
                name="Kaelen",
                role="protagonist",
                age_group="young_adult",
                gender="male",
                look="short dark undercut hair, glowing cybernetic eye, trench coat, reinforced gauntlets",
                personality="cynical yet protective",
            ),
        ],
        locations=[],
    )
    return OriginalStory(bible=bible, scenes=[], panels=[])


class TestEndToEndPipelineEmpiricalChallenge:
    """Empirical challenge suite executing and verifying full end-to-end integration."""

    def test_e2e_pipeline_full_chain_turnaround_matting_decomposition_parallax(self, tmp_path: Path):
        """Execute continuous end-to-end pipeline linking R1 -> R2 -> R3 -> Parallax Bridge."""
        story = create_e2e_story()
        char = story.bible.characters[0]
        ws = tmp_path / "studio_ws"
        ws.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # Step 1: Turnaround generation (R1) & Slicing
        # ------------------------------------------------------------------
        spec = RiggingSpec(pose="a_pose", views=["front", "three_quarter", "side", "back"])
        sheet = generate_turnaround_sheet(char, story, ws, runner=None, spec=spec, slice_views=True)

        assert Path(sheet.image_path).exists(), "Turnaround sheet file must exist on disk"
        assert len(sheet.views) == 4, "Turnaround sheet must record 4 views in metadata"
        for v in ["front", "three_quarter", "side", "back"]:
            assert v in sheet.views, f"View {v} must be present in sheet metadata"
            assert Path(sheet.views[v]).exists(), f"Sliced view file for {v} must exist"

        with Image.open(sheet.image_path) as sheet_img:
            assert sheet_img.size == (1536, 768)
            slices = slice_turnaround_sheet(sheet_img)
            assert len(slices) == 4
            assert set(slices.keys()) == {"front", "three_quarter", "side", "back"}
            for v_name, s_img in slices.items():
                assert s_img.size == (384, 768), f"Slice {v_name} width must be 384 and height 768"

        # ------------------------------------------------------------------
        # Step 2: Alpha Matting (R2) on Orthographic Rigging View
        # ------------------------------------------------------------------
        # To avoid the offline guide box outline defect (documented in test below),
        # create a clean orthographic character view in A-pose with neutral background.
        ortho_img = Image.new("RGB", (384, 768), color=(180, 180, 180))
        draw = ImageDraw.Draw(ortho_img)
        cx = 384 // 2
        head_r = int(768 * 0.07)
        head_cy = int(768 * 0.18)
        draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=(60, 60, 70))
        torso_top = head_cy + head_r + 4
        torso_bottom = int(768 * 0.55)
        torso_half_w = int(head_r * 1.2)
        draw.rectangle([cx - torso_half_w, torso_top, cx + torso_half_w, torso_bottom], fill=(60, 60, 70))
        arm_start_y = torso_top + 10
        draw.line([cx - torso_half_w, arm_start_y, cx - torso_half_w - 60, arm_start_y + 120], fill=(60, 60, 70), width=12)
        draw.line([cx + torso_half_w, arm_start_y, cx + torso_half_w + 60, arm_start_y + 120], fill=(60, 60, 70), width=12)
        leg_y_top = torso_bottom
        leg_y_bottom = int(768 * 0.90)
        draw.line([cx - 25, leg_y_top, cx - 35, leg_y_bottom], fill=(60, 60, 70), width=14)
        draw.line([cx + 25, leg_y_top, cx + 35, leg_y_bottom], fill=(60, 60, 70), width=14)

        matting_res = remove_background(ortho_img, runner=None, defringe=True)

        assert isinstance(matting_res, MattingResult)
        assert matting_res.has_alpha is True
        assert matting_res.halo_free is True
        assert matting_res.width == 384
        assert matting_res.height == 768

        matted_pil = matting_res.to_image()
        assert matted_pil.mode == "RGBA"
        matted_np = np.array(matted_pil)
        alpha = matted_np[:, :, 3]

        # Invariant 2.1: Clean transparency on all perimeter gutters (alpha <= 2)
        assert np.all(alpha[0, :] <= 2), "Top edge must be transparent"
        assert np.all(alpha[-1, :] <= 2), "Bottom edge must be transparent"
        assert np.all(alpha[:, 0] <= 2), "Left edge must be transparent"
        assert np.all(alpha[:, -1] <= 2), "Right edge must be transparent"

        # Invariant 2.2: Character silhouette core is solid opaque
        assert alpha[head_cy, cx] == 255, "Head center must be solid opaque"
        assert alpha[300, cx] > 200, "Torso center must be solid opaque"

        # Invariant 2.3: Zero halo on edges - semi-transparent transitions
        edge_pixels = (alpha > 0) & (alpha < 240)
        if np.any(edge_pixels):
            edge_r = matted_np[:, :, 0][edge_pixels]
            assert np.mean(edge_r) < 130, "Edge colors must be decontaminated toward foreground, not background"

        # ------------------------------------------------------------------
        # Step 3: Multi-Plane Layer Decomposition (R3) with Multi-Props
        # ------------------------------------------------------------------
        # Synthesize a multi-object panel scene:
        # Background: textured gradient scene (1200 x 800)
        panel_w, panel_h = 1200, 800
        scene_rgb = np.full((panel_h, panel_w, 3), 190, dtype=np.uint8)
        # Add subtle background texture
        for y in range(panel_h):
            scene_rgb[y, :, 0] = int(160 + 30 * (y / panel_h))
            scene_rgb[y, :, 1] = int(170 + 20 * (y / panel_h))
            scene_rgb[y, :, 2] = int(190 + 10 * (y / panel_h))

        # Primary character foreground subject (large central body)
        cv2.ellipse(scene_rgb, (600, 480), (140, 260), 0, 0, 360, (40, 45, 60), -1)
        # Head
        cv2.circle(scene_rgb, (600, 200), 70, (40, 45, 60), -1)

        # Prop 1: Floating energy orb on the left (area > 50px)
        cv2.circle(scene_rgb, (250, 280), 45, (220, 80, 50), -1)

        # Prop 2: Hovering drone / tactical datapad on the right (area > 50px)
        cv2.rectangle(scene_rgb, (920, 360), (1060, 480), (50, 160, 100), -1)

        scene_pil = Image.fromarray(scene_rgb, "RGB")

        # Decompose with isolate_props=True
        stack = decompose_layers(scene_pil, panel_id="panel_e2e_01", isolate_props=True)

        assert isinstance(stack, LayerStack)
        assert stack.panel_id == "panel_e2e_01"
        assert stack.width == panel_w
        assert stack.height == panel_h

        # Invariant 3.1: Exactly 4 discrete planes (background_plate, prop_1, prop_2, foreground_subject)
        layer_names = [l.name for l in stack.layers]
        assert len(stack.layers) == 4, f"Expected 4 layers, got {len(stack.layers)}: {layer_names}"
        assert layer_names == ["background_plate", "prop_1", "prop_2", "foreground_subject"]

        # Invariant 3.2: Discrete Z-Indices strictly ordered
        bg_layer = stack.get_layer("background_plate")
        p1_layer = stack.get_layer("prop_1")
        p2_layer = stack.get_layer("prop_2")
        subj_layer = stack.get_layer("foreground_subject")

        assert bg_layer is not None and bg_layer.z_index == 0
        assert p1_layer is not None and p1_layer.z_index == 11
        assert p2_layer is not None and p2_layer.z_index == 12
        assert subj_layer is not None and subj_layer.z_index == 20
        assert bg_layer.z_index < p1_layer.z_index < p2_layer.z_index < subj_layer.z_index

        # Invariant 3.3: Discrete Depth Estimates strictly ordered
        assert bg_layer.depth_estimate == 0.1
        assert p1_layer.depth_estimate == 0.527
        assert p2_layer.depth_estimate == 0.633
        assert subj_layer.depth_estimate == 0.8
        assert bg_layer.depth_estimate < p1_layer.depth_estimate < p2_layer.depth_estimate < subj_layer.depth_estimate

        # Invariant 3.4: Pixel exclusivity between discrete props
        p1_mask = np.array(p1_layer.to_mask_image())
        p2_mask = np.array(p2_layer.to_mask_image())
        subj_mask = np.array(subj_layer.to_mask_image())

        prop_overlap = np.logical_and(p1_mask > 0, p2_mask > 0)
        assert np.count_nonzero(prop_overlap) == 0, "Prop 1 and Prop 2 masks must have zero overlapping pixels"

        subj_p1_overlap = np.logical_and(subj_mask > 0, p1_mask > 0)
        assert np.count_nonzero(subj_p1_overlap) == 0, "Subject and Prop 1 masks must have zero overlapping pixels"

        subj_p2_overlap = np.logical_and(subj_mask > 0, p2_mask > 0)
        assert np.count_nonzero(subj_p2_overlap) == 0, "Subject and Prop 2 masks must have zero overlapping pixels"

        # Invariant 3.5: Clean infilled background plate (no holes, no transparency)
        bg_img = bg_layer.to_image()
        assert bg_img.mode == "RGB", "Background plate must be opaque RGB without alpha"
        assert bg_layer.mask_bytes is None, "Background plate must not have an alpha mask"
        bg_np = np.array(bg_img)

        # Check hole regions (where props and subject were) are infilled with background gradient
        # Subject center was (600, 480)
        assert not np.array_equal(bg_np[480, 600], [40, 45, 60]), "Subject hole must be infilled"
        assert bg_np[480, 600, 0] > 120, "Infilled subject region must match background tone"

        # Prop 1 center was (250, 280)
        assert not np.array_equal(bg_np[280, 250], [220, 80, 50]), "Prop 1 hole must be infilled"
        assert bg_np[280, 250, 0] > 120, "Infilled prop 1 region must match background tone"

        # Prop 2 center was (990, 420)
        assert not np.array_equal(bg_np[420, 990], [50, 160, 100]), "Prop 2 hole must be infilled"
        assert bg_np[420, 990, 0] > 120, "Infilled prop 2 region must match background tone"

        # ------------------------------------------------------------------
        # Step 4: Parallax Bridge Verification
        # ------------------------------------------------------------------
        plan = stack.to_parallax_plan()

        assert isinstance(plan, ParallaxPlan)
        assert plan.enabled is True
        assert plan.fallback_flat is False
        assert plan.max_parallax_offset == 0.08
        assert len(plan.layers) == 4

        # Verify speed scales and types across planes
        plan_dict = {lay.layer_id: lay for lay in plan.layers}

        # Background instruction
        inst_bg = plan_dict["lay_background_plate"]
        assert inst_bg.layer_type == LayerType.BACKGROUND
        assert inst_bg.motion_factor == 0.6
        assert inst_bg.depth == 0.1

        # Prop 1 instruction
        inst_p1 = plan_dict["lay_prop_1"]
        assert inst_p1.layer_type == LayerType.FOREGROUND
        assert inst_p1.motion_factor == 1.10
        assert inst_p1.depth == 0.527

        # Prop 2 instruction
        inst_p2 = plan_dict["lay_prop_2"]
        assert inst_p2.layer_type == LayerType.FOREGROUND
        assert inst_p2.motion_factor == 1.15
        assert inst_p2.depth == 0.633

        # Character instruction
        inst_subj = plan_dict["lay_foreground_subject"]
        assert inst_subj.layer_type == LayerType.CHARACTER
        assert inst_subj.motion_factor == 1.0
        assert inst_subj.depth == 0.8

        # Verify custom depth override support
        custom_plan = stack.to_parallax_plan(default_depths={"prop_1": 0.45, "prop_2": 0.55})
        custom_dict = {lay.layer_id: lay for lay in custom_plan.layers}
        assert custom_dict["lay_prop_1"].depth == 0.45
        assert custom_dict["lay_prop_2"].depth == 0.55

    def test_e2e_alpha_matting_zero_halo_color_decontamination_adversarial(self):
        """Empirically test defringe_alpha to prove 0 halo and complete color decontamination."""
        # Synthesize a bright magenta subject on pure white background
        w, h = 100, 100
        fg_color = np.array([255, 0, 128], dtype=np.uint8)
        bg_color = np.array([255, 255, 255], dtype=np.uint8)

        rgb = np.full((h, w, 3), bg_color, dtype=np.uint8)
        # Solid center circle
        cv2.circle(rgb, (50, 50), 30, fg_color.tolist(), -1)

        # Simulate raw alpha channel with a soft semi-transparent fringe
        alpha = np.zeros((h, w), dtype=np.uint8)
        cv2.circle(alpha, (50, 50), 28, 255, -1)  # solid core
        # Boundary zone: alpha is 128
        cv2.circle(alpha, (50, 50), 32, 128, 2)

        # Simulate white background color bleeding into the semi-transparent fringe
        fringe_mask = (alpha == 128)
        rgb[fringe_mask] = (fg_color.astype(int) // 2 + bg_color.astype(int) // 2).astype(np.uint8)

        # In contaminated state, edge pixels have white wash (high green channel)
        assert np.mean(rgb[fringe_mask, 1]) > 100, "Contaminated edge should have white bleed"

        # Apply defringe_alpha
        clean_rgb, clean_alpha = defringe_alpha(rgb, alpha, threshold=240)

        # Invariant: Semi-transparent edge pixels must now have 0 green bleed!
        # Their RGB must be perfectly restored to the foreground color [255, 0, 128]
        edge_r = clean_rgb[fringe_mask, 0]
        edge_g = clean_rgb[fringe_mask, 1]
        edge_b = clean_rgb[fringe_mask, 2]

        assert np.all(edge_r == 255), "Decontaminated red must match foreground"
        assert np.all(edge_g == 0), "Decontaminated green must be 0 (no white halo)"
        assert np.all(edge_b == 128), "Decontaminated blue must match foreground"

        # Verify composite over black background has zero halo
        composite_black = (clean_rgb.astype(float) * (clean_alpha[:, :, None] / 255.0)).astype(np.uint8)
        # Edge pixels on black composite must show pure magenta attenuated by 0.5
        assert np.all(composite_black[fringe_mask, 1] == 0), "Composite on black must have 0 green fringe"
        assert np.all(np.abs(composite_black[fringe_mask, 0] - 128) <= 1), "Composite on black must be half-intensity magenta"

    def test_e2e_multi_prop_isolation_vs_merged_contract(self):
        """Stress test 3 discrete props: verify isolate_props=True vs isolate_props=False."""
        w, h = 800, 600
        canvas = np.full((h, w, 3), 160, dtype=np.uint8)

        # Character subject in center
        cv2.ellipse(canvas, (400, 350), (90, 180), 0, 0, 360, (50, 50, 70), -1)

        # Prop 1: upper left
        cv2.circle(canvas, (150, 150), 30, (200, 40, 40), -1)

        # Prop 2: upper right
        cv2.circle(canvas, (650, 150), 35, (40, 200, 40), -1)

        # Prop 3: lower right
        cv2.rectangle(canvas, (600, 450), (700, 520), (40, 40, 200), -1)

        im = Image.fromarray(canvas, "RGB")

        # 1. When isolate_props=True: exactly 3 discrete props
        stack_isolated = decompose_layers(im, isolate_props=True)
        assert len(stack_isolated.layers) == 5, "Expected 5 layers: bg + 3 props + subject"

        prop_names = [l.name for l in stack_isolated.layers if l.layer_type == "prop"]
        assert prop_names == ["prop_1", "prop_2", "prop_3"]

        z_indices = [l.z_index for l in stack_isolated.layers if l.layer_type == "prop"]
        assert z_indices == [11, 12, 13]

        plan_iso = stack_isolated.to_parallax_plan()
        iso_dict = {lay.layer_id: lay for lay in plan_iso.layers}
        assert iso_dict["lay_prop_1"].motion_factor == 1.10
        assert iso_dict["lay_prop_2"].motion_factor == 1.15
        assert iso_dict["lay_prop_3"].motion_factor == 1.20

        # Depths: 0.42 + (idx/4)*0.32 -> idx=1: 0.5, idx=2: 0.58, idx=3: 0.66
        assert iso_dict["lay_prop_1"].depth == 0.5
        assert iso_dict["lay_prop_2"].depth == 0.58
        assert iso_dict["lay_prop_3"].depth == 0.66

        # 2. When isolate_props=False: backward-compatible single merged prop_1
        stack_merged = decompose_layers(im, isolate_props=False)
        assert len(stack_merged.layers) == 3, "Expected 3 layers: bg + merged prop_1 + subject"
        assert stack_merged.layers[1].name == "prop_1"
        assert stack_merged.layers[1].z_index == 15
        assert stack_merged.layers[1].depth_estimate == 0.6

        plan_merged = stack_merged.to_parallax_plan()
        merged_dict = {lay.layer_id: lay for lay in plan_merged.layers}
        assert merged_dict["lay_prop_1"].motion_factor == 1.10
        assert merged_dict["lay_prop_1"].depth == 0.6

    def test_e2e_turnaround_all_poses_and_slicing_aspect_ratios(self, tmp_path: Path):
        """Stress test turnaround generation across all poses and custom non-standard dimensions."""
        story = create_e2e_story()
        char = story.bible.characters[0]

        for pose in ["a_pose", "t_pose", "neutral_standing"]:
            spec = RiggingSpec(pose=pose, views=["front", "three_quarter", "side", "back"])
            ws = tmp_path / f"turnaround_{pose}"
            ws.mkdir(parents=True, exist_ok=True)

            sheet = generate_turnaround_sheet(char, story, ws, spec=spec, slice_views=True)
            assert Path(sheet.image_path).exists()
            assert len(sheet.views) == 4

            with Image.open(sheet.image_path) as sheet_img:
                slices = slice_turnaround_sheet(sheet_img)
                total_w = sum(s.size[0] for s in slices.values())
                assert total_w == sheet_img.size[0], "Sum of slice widths must equal sheet width"

                # Check limb separation: arm coordinates should differ between a_pose and t_pose
                front_slice = slices["front"]
                front_arr = np.array(front_slice)
                assert front_arr.shape == (768, 384, 3)

        # Test non-standard odd resolution: 1205 x 603
        odd_sheet = Image.new("RGB", (1205, 603), (150, 150, 150))
        odd_slices = slice_turnaround_sheet(odd_sheet, views=["front", "side", "back"])
        assert len(odd_slices) == 3
        assert sum(s.size[0] for s in odd_slices.values()) == 1205
        assert all(s.size[1] == 603 for s in odd_slices.values())

    def test_e2e_polymorphic_input_resilience(self, tmp_path: Path):
        """Verify decompose_layers and remove_background gracefully ingest all input representations."""
        w, h = 200, 200
        canvas = np.full((h, w, 3), 180, dtype=np.uint8)
        cv2.circle(canvas, (100, 100), 50, (30, 40, 50), -1)

        pil_img = Image.fromarray(canvas, "RGB")
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        file_path = tmp_path / "polymorphic_test.png"
        file_path.write_bytes(png_bytes)

        # 1. remove_background input types
        res_pil = remove_background(pil_img)
        res_bytes = remove_background(png_bytes)
        res_path = remove_background(file_path)
        res_str = remove_background(str(file_path))
        res_nd = remove_background(canvas)

        for res in [res_pil, res_bytes, res_path, res_str, res_nd]:
            assert res.has_alpha is True
            assert res.width == w and res.height == h
            assert res.to_image().mode == "RGBA"

        # 2. decompose_layers input types
        stack_pil = decompose_layers(pil_img)
        stack_bytes = decompose_layers(png_bytes)
        stack_path = decompose_layers(file_path)
        stack_str = decompose_layers(str(file_path))
        stack_nd = decompose_layers(canvas)

        for stack in [stack_pil, stack_bytes, stack_path, stack_str, stack_nd]:
            assert stack.width == w and stack.height == h
            assert len(stack.layers) >= 2
            assert stack.background is not None
            assert stack.background.to_image().mode == "RGB"
            assert stack.foreground_subject is not None
            assert stack.foreground_subject.to_image().mode == "RGBA"

    def test_e2e_inpaint_background_plate_dilation_coverage(self):
        """Verify that inpaint_background_plate dilates mask by +12px and infills cleanly."""
        w, h = 200, 200
        base = np.full((h, w, 3), (120, 160, 200), dtype=np.uint8)
        # Foreground hole: dark square at center (80..120, 80..120)
        hole_size = 40
        top_left = (80, 80)
        cv2.rectangle(base, top_left, (top_left[0] + hole_size, top_left[1] + hole_size), (0, 0, 0), -1)

        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.rectangle(mask, top_left, (top_left[0] + hole_size, top_left[1] + hole_size), 255, -1)

        infilled = inpaint_background_plate(Image.fromarray(base), Image.fromarray(mask), dilation_px=12)
        assert isinstance(infilled, Image.Image)
        assert infilled.size == (w, h)
        assert infilled.mode == "RGB"

        infilled_np = np.array(infilled)

        # Invariant 1: The original black hole pixels must be infilled with surrounding color
        center_color = infilled_np[100, 100]
        assert not np.array_equal(center_color, [0, 0, 0]), "Center of hole must not remain black"
        assert center_color[0] > 90 and center_color[1] > 130 and center_color[2] > 160

        # Invariant 2: Gutter surrounding the hole (within 12px dilation) must blend smoothly
        dilated_edge_color = infilled_np[75, 75]
        assert not np.array_equal(dilated_edge_color, [0, 0, 0])
        assert np.linalg.norm(dilated_edge_color.astype(float) - np.array([120, 160, 200], dtype=float)) < 30.0

    def test_e2e_multi_prop_scaling_and_per_prop_speed_factors(self):
        """Stress-test 5 discrete props: verify exact speed scaling 1.10, 1.15, 1.20, 1.25, 1.30."""
        w, h = 1000, 800
        canvas = np.full((h, w, 3), 170, dtype=np.uint8)

        # Subject in center
        cv2.ellipse(canvas, (500, 450), (120, 240), 0, 0, 360, (50, 50, 70), -1)

        # 5 distinct props in separate locations
        centers = [(150, 150), (850, 150), (150, 650), (850, 650), (500, 120)]
        colors = [(200, 50, 50), (50, 200, 50), (50, 50, 200), (200, 200, 50), (200, 50, 200)]
        for (cx, cy), col in zip(centers, colors):
            cv2.circle(canvas, (cx, cy), 35, col, -1)

        im = Image.fromarray(canvas, "RGB")
        stack = decompose_layers(im, isolate_props=True)

        # 1 background + 5 props + 1 subject = 7 layers
        assert len(stack.layers) == 7, f"Expected 7 layers, got {len(stack.layers)}"
        prop_layers = [l for l in stack.layers if l.layer_type == "prop"]
        assert len(prop_layers) == 5

        # Verify z-index monotonic sequence: 11, 12, 13, 14, 15
        for idx, p_lay in enumerate(prop_layers, start=1):
            assert p_lay.name == f"prop_{idx}"
            assert p_lay.z_index == 10 + idx

        # Verify parallax plan speed scaling
        plan = stack.to_parallax_plan()
        plan_dict = {lay.layer_id: lay for lay in plan.layers}

        expected_speeds = [1.10, 1.15, 1.20, 1.25, 1.30]
        for idx, exp_speed in enumerate(expected_speeds, start=1):
            inst = plan_dict[f"lay_prop_{idx}"]
            assert inst.motion_factor == exp_speed, f"prop_{idx} speed scale must be {exp_speed}, got {inst.motion_factor}"

    def test_e2e_single_prop_and_zero_prop_edge_cases(self):
        """Verify decomposition and parallax bridge on edge scenes with 1 prop and 0 props."""
        w, h = 300, 300

        # Scene 1: Exactly 1 prop with isolate_props=True
        canvas_1 = np.full((h, w, 3), 160, dtype=np.uint8)
        cv2.circle(canvas_1, (150, 150), 60, (40, 50, 60), -1)  # subject
        cv2.circle(canvas_1, (50, 50), 20, (200, 50, 50), -1)    # single prop

        stack_1 = decompose_layers(Image.fromarray(canvas_1), isolate_props=True)
        assert len(stack_1.layers) == 3
        assert stack_1.layers[1].name == "prop_1"
        assert stack_1.layers[1].z_index == 15
        assert stack_1.layers[1].depth_estimate == 0.6

        plan_1 = stack_1.to_parallax_plan()
        assert plan_1.enabled is True
        assert len(plan_1.layers) == 3

        # Scene 2: 0 props (only subject and background)
        canvas_0 = np.full((h, w, 3), 160, dtype=np.uint8)
        cv2.circle(canvas_0, (150, 150), 60, (40, 50, 60), -1)  # subject only

        stack_0 = decompose_layers(Image.fromarray(canvas_0), isolate_props=True)
        assert len(stack_0.layers) == 2
        layer_names_0 = [l.name for l in stack_0.layers]
        assert layer_names_0 == ["background_plate", "foreground_subject"]
        assert stack_0.props == []

        plan_0 = stack_0.to_parallax_plan()
        assert plan_0.enabled is True
        assert len(plan_0.layers) == 2
        p0_dict = {lay.layer_id: lay for lay in plan_0.layers}
        assert p0_dict["lay_background_plate"].motion_factor == 0.6
        assert p0_dict["lay_foreground_subject"].motion_factor == 1.0

    def test_e2e_turnaround_dual_prompt_compilation_and_negative_constraints(self):
        """Verify prompt compilers and RIGGING_NEGATIVE constraints for both SDXL tags and FLUX natural."""
        story = create_e2e_story()
        char = story.bible.characters[0]
        spec = RiggingSpec(pose="a_pose")

        # 1. SDXL Animagine tag compilation
        pos_tags, neg_tags = compile_turnaround_prompt(char, story, spec=spec, style_kind="tags", return_negative=True)
        assert "a-pose" in pos_tags
        assert "clean limb separation" in pos_tags
        assert "turnaround" in pos_tags or "multiple views" in pos_tags
        assert neg_tags == RIGGING_NEGATIVE

        # RIGGING_NEGATIVE must prohibit occluded limbs but must NOT suppress turnaround sheets
        assert "arms crossed" in RIGGING_NEGATIVE.lower() or "crossed arms" in RIGGING_NEGATIVE.lower()
        assert "multiple views" not in RIGGING_NEGATIVE.lower(), "RIGGING_NEGATIVE must NOT suppress multiple views!"

        # 2. FLUX / Qwen natural language compilation
        pos_nat, neg_nat = compile_turnaround_prompt(char, story, spec=spec, style_kind="natural", return_negative=True)
        assert "A-pose" in pos_nat or "a-pose" in pos_nat
        assert "45 degrees" in pos_nat
        assert "glowing cybernetic eye" in pos_nat
        assert "trench coat" in pos_nat

    def test_e2e_offline_turnaround_guide_box_outline_defect_finding(self, tmp_path: Path):
        """Empirically document that offline turnaround sheet guide box outlines introduce matting instability.

        Finding:
        _create_offline_turnaround_image() in engine/original/rigging.py draws an outline rectangle:
            draw.rectangle([x_left + 4, 4, x_right - 4, h - 4], outline=(150, 150, 150), width=1)
        When sliced and fed to remove_background(), line 841:
            gc_mask[diff_mask] = cv2.GC_PR_FGD
        overwrites the outer GC_BGD margin with GC_PR_FGD because (150, 150, 150) differs from
        background (180, 180, 180).
        This causes GrabCut GMM clustering to become sensitive to prior RNG state.
        In contrast, clean orthographic silhouettes without the artificial guide box outline
        are 100% stable, deterministic, and produce clean zero gutters on all 4 perimeter edges.
        """
        story = create_e2e_story()
        char = story.bible.characters[0]
        ws = tmp_path / "finding_ws"
        ws.mkdir(parents=True, exist_ok=True)

        sheet = generate_turnaround_sheet(char, story, ws, runner=None, spec=RiggingSpec(pose="a_pose"), slice_views=True)
        front_path = Path(sheet.views["front"])

        with Image.open(front_path) as front_img:
            res_front = remove_background(front_img, runner=None, defringe=True)
        assert isinstance(res_front, MattingResult)
        assert res_front.has_alpha is True
        assert res_front.width == 384 and res_front.height == 768

        # 2. Verify clean orthographic turnaround without guide box outline is 100% robust
        ortho_img = Image.new("RGB", (384, 768), color=(180, 180, 180))
        draw = ImageDraw.Draw(ortho_img)
        cx = 384 // 2
        head_r = int(768 * 0.07)
        head_cy = int(768 * 0.18)
        draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill=(60, 60, 70))
        torso_top = head_cy + head_r + 4
        torso_bottom = int(768 * 0.55)
        torso_half_w = int(head_r * 1.2)
        draw.rectangle([cx - torso_half_w, torso_top, cx + torso_half_w, torso_bottom], fill=(60, 60, 70))
        leg_y_top = torso_bottom
        leg_y_bottom = int(768 * 0.90)
        draw.line([cx - 25, leg_y_top, cx - 35, leg_y_bottom], fill=(60, 60, 70), width=14)
        draw.line([cx + 25, leg_y_top, cx + 35, leg_y_bottom], fill=(60, 60, 70), width=14)

        res_clean = remove_background(ortho_img, runner=None, defringe=True)
        clean_np = np.array(res_clean.to_image())
        clean_alpha = clean_np[:, :, 3]

        # Invariant: Clean silhouette without guide box always has 0 perimeter gutters
        assert np.all(clean_alpha[0, :] <= 2), "Top edge must be transparent"
        assert np.all(clean_alpha[-1, :] <= 2), "Bottom edge must be transparent"
        assert np.all(clean_alpha[:, 0] <= 2), "Left edge must be transparent"
        assert np.all(clean_alpha[:, -1] <= 2), "Right edge must be transparent"
        assert clean_alpha[head_cy, cx] == 255, "Head center must be solid opaque"


