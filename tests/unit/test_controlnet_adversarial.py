"""Adversarial and stress-test suite for Phase 4: ControlNet conditioning.

Covers:
1. Extreme / negative weights (pose_weight=-0.5, pose_weight=2.0, depth_weight=0.0, etc.)
2. Non-standard character actions and custom poses.
3. Non-standard camera angles and extreme aspect ratios.
4. Malformed image paths (non-existent paths, spaces, Unicode, Path vs str vs bytes).
5. Single-conditioning behavior (pose-only neutralization, depth-only neutralization, explicit zero-weights).
6. Preflight & graceful fallback resilience under corrupted or missing environments.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image
import pytest

from engine.comfyui import ComfyWorkflowRegistry
from engine.comfyui.service import ComfyImageGenerationError, _patch_workflow, _validate_output_dimensions
from engine.original import art
from engine.original import shotspec
from engine.original.models import (
    Bible,
    Character,
    Line,
    Location,
    OriginalStory,
    Panel,
    Premise,
    Scene,
)
from engine.original.shotspec import CharPose, ShotSpec, compile_controlnet_conditioning


def _dummy_png(color="blue", size=(32, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _make_story(spec: ShotSpec | None = None) -> OriginalStory:
    bible = Bible(
        premise=Premise(title="Stress Tale", genre="fantasy", logline="l", tone="t", setting="s"),
        characters=[
            Character(id="hero", name="Hero", role="protagonist", age_group="adult",
                      look="short black hair, blue eyes, iron armor, silver sword", personality="p"),
            Character(id="mage", name="Mage", role="ally", age_group="adult",
                      look="long silver hair, green eyes, wizard robe, wooden staff", personality="p"),
        ],
        locations=[Location(id="ruins", name="Ancient Ruins", look="mossy stone pillars, overcast sky")],
    )
    if spec is None:
        spec = ShotSpec(
            shot="medium",
            camera="eye_level",
            setting="mossy stone pillars",
            lighting="daylight",
            mood="tense",
            characters=[CharPose(id="hero", side="center", pose="standing", expression="focused", action="gripping sword")],
        )
    panel = Panel(
        id="p001",
        scene_id="sc01",
        shot=spec.shot,
        angle=spec.camera,
        location_id="ruins",
        character_ids=["hero"],
        action="Hero stands ready.",
        dialogue=[Line(speaker_id="hero", text="I am ready.")],
        director=spec.model_dump(),
        caption="Hero stands firmly among the mossy stone pillars.",
    )
    scene = Scene(id="sc01", location_id="ruins", character_ids=["hero"], summary="s", mood="m")
    return OriginalStory(bible=bible, scenes=[scene], panels=[panel])


class MockComfyClient:
    def __init__(self):
        self.base_url = "http://127.0.0.1:8188/"
        self.prompts_submitted = []
        self.uploaded_images = {}

    def submit_prompt(self, workflow: dict) -> str:
        self.prompts_submitted.append(workflow)
        return "mock_pid_adv_001"

    def history(self, pid: str) -> dict:
        return {
            pid: {
                "outputs": {
                    "13": {
                        "images": [{"filename": "panelflow_controlnet_adv_001.png", "subfolder": "", "type": "output"}]
                    }
                }
            }
        }

    def download_output(self, filename: str, subfolder: str = "", folder_type: str = "output") -> bytes:
        return _dummy_png("green", (64, 64))


# ==============================================================================
# Suite 1: Extreme & Negative Weights Stress Testing
# ==============================================================================

@pytest.mark.parametrize("pose_w, depth_w", [
    (-0.5, 0.6),
    (2.0, 0.6),
    (0.75, -1.0),
    (0.75, 5.0),
    (-100.0, 100.0),
    (0.0, 0.0),
    (0.0, 0.6),
    (0.75, 0.0),
])
def test_shotspec_and_compilation_with_extreme_weights(pose_w, depth_w):
    spec = ShotSpec(shot="medium", pose_weight=pose_w, depth_weight=depth_w)
    assert spec.pose_weight == pose_w
    assert spec.depth_weight == depth_w

    cond = compile_controlnet_conditioning(spec, (1024, 1024))
    assert cond["pose_weight"] == pose_w
    assert cond["depth_weight"] == depth_w


@pytest.mark.parametrize("pose_w, depth_w", [
    (-0.5, 1.5),
    (2.5, -0.2),
    (0.0, 0.0),
])
def test_patch_workflow_with_extreme_weights(pose_w, depth_w):
    reg = ComfyWorkflowRegistry()
    wf, _ = reg.load("anime_sdxl_controlnet")
    meta = reg.metadata("anime_sdxl_controlnet")

    patched = _patch_workflow(
        wf,
        meta["patch_slots"],
        "heroic knight",
        "lowres",
        1024,
        1024,
        42,
        "panelflow_adv",
        pose_image="pose_test.png",
        depth_image="depth_test.png",
        pose_weight=pose_w,
        depth_weight=depth_w,
    )

    # Node 7 is pose ControlNetApplyAdvanced, Node 10 is depth ControlNetApplyAdvanced
    assert patched["7"]["inputs"]["strength"] == pose_w
    assert patched["10"]["inputs"]["strength"] == depth_w


def test_explicit_zero_weights_not_reverted_to_defaults():
    """Explicit weight of 0.0 must not be overridden by default fallback weights."""
    client = MockComfyClient()
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = client
    runner.engine = "sdxl"
    runner.style = "tags"
    reg = ComfyWorkflowRegistry()
    runner.sdxl_controlnet = (reg.load("anime_sdxl_controlnet")[0], reg.metadata("anime_sdxl_controlnet"))
    runner.controlnet_ready = True

    # Dual conditioning with explicit 0.0 weights
    runner.generate(
        pos="hero", neg="lowres", seed=1, width=1024, height=1024, prefix="test",
        pose_image="pose.png", depth_image="depth.png",
        pose_weight=0.0, depth_weight=0.0
    )
    submitted = client.prompts_submitted[-1]
    assert submitted["7"]["inputs"]["strength"] == 0.0
    assert submitted["10"]["inputs"]["strength"] == 0.0


# ==============================================================================
# Suite 2: Non-Standard Character Actions & Custom Poses
# ==============================================================================

@pytest.mark.parametrize("custom_action, custom_pose", [
    ("cartwheel into a backflip off a temple ledge", "acrobatic mid-air inversion"),
    ("juggling blazing torches while riding a unicycle", "unicycle balance"),
    ("drinking tea while conversing with a dragon", "sitting cross-legged with saucer"),
    ("", ""),
    ("   ", "   "),
    ("!@#$%^&*()_+{}[]:;\"'<>?,./~`", "<invalid_tag>"),
    ("supercalifragilisticexpialidocious " * 50, "ultra_long_pose " * 50),
    ("日本語のポーズ", "忍者の構え"),
])
def test_compile_controlnet_conditioning_handles_exotic_poses_and_actions(custom_action, custom_pose):
    spec = ShotSpec(
        shot="full",
        camera="low",
        characters=[
            CharPose(id="c1", pose=custom_pose, action=custom_action)
        ],
        control_pose="custom_override_pose" if custom_pose else None,
    )
    cond = compile_controlnet_conditioning(spec, (832, 1216))
    assert cond["width"] == 832
    assert cond["height"] == 1216
    if custom_pose:
        assert cond["control_pose"] == "custom_override_pose"
    assert cond["dims"] == (832, 1216)


def test_character_action_keyword_extraction_deterministic():
    """Verify that multiple matching keywords resolve predictably without crashing."""
    spec = ShotSpec(
        shot="medium",
        characters=[
            CharPose(id="c1", pose="sitting and kneeling", action="pointing while jumping")
        ]
    )
    cond = compile_controlnet_conditioning(spec, (1024, 1024))
    assert cond["control_pose"] in shotspec.POSES.values()


# ==============================================================================
# Suite 3: Non-Standard Camera Angles & Extreme Aspect Ratios
# ==============================================================================

@pytest.mark.parametrize("angle, shot", [
    ("dutch_tilt_45", "extreme_macro"),
    ("worm_eye_perspective", "satellite_god_view"),
    ("", ""),
    ("overhead", "unrecognized_shot_spec"),
    ("360_spherical_panorama", "medium"),
])
def test_compile_controlnet_conditioning_with_non_standard_camera_and_shot(angle, shot):
    spec = ShotSpec(shot=shot, camera=angle)
    cond = compile_controlnet_conditioning(spec, (1024, 1024))
    assert cond["camera"] == angle
    assert cond["shot"] == shot
    # For unrecognized shots without explicit depth, control_depth is None
    if shot not in ("close", "extreme_close", "wide", "full", "full_body", "medium"):
        assert cond["control_depth"] is None


@pytest.mark.parametrize("w, h, should_pass", [
    (1024, 1024, True),
    (1344, 768, True),
    (832, 1216, True),
    (256, 2048, True),   # min/max boundary
    (2048, 256, True),   # min/max boundary
    (100, 1024, False),  # below min (256)
    (1024, 3000, False), # above max (2048)
    (1025, 1024, False), # not multiple of 8
    (1024, 1027, False), # not multiple of 8
])
def test_dimension_policy_boundary_and_extremes(w, h, should_pass):
    reg = ComfyWorkflowRegistry()
    meta = reg.metadata("anime_sdxl_controlnet")
    policy = meta["dimension_policy"]

    if should_pass:
        _validate_output_dimensions(
            actual_width=w, actual_height=h,
            requested_width=w, requested_height=h,
            dimension_policy=policy
        )
    else:
        with pytest.raises(ComfyImageGenerationError):
            _validate_output_dimensions(
                actual_width=w, actual_height=h,
                requested_width=w, requested_height=h,
                dimension_policy=policy
            )


# ==============================================================================
# Suite 4: Malformed Image Paths & Path Handling
# ==============================================================================

def test_resolve_upload_with_nonexistent_string_path():
    """String paths that do not exist locally are passed through as filename references."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    res = runner._resolve_upload("nonexistent_pose_xyz.png")
    assert res == "nonexistent_pose_xyz.png"


def test_resolve_upload_with_spaces_and_unicode_string():
    """Filenames with spaces and unicode characters are preserved."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    res_spaces = runner._resolve_upload("poses/hero action stance 01.png")
    assert res_spaces == "poses/hero action stance 01.png"

    res_unicode = runner._resolve_upload("ポーズ/格闘技_stance.png")
    assert res_unicode == "ポーズ/格闘技_stance.png"


def test_resolve_upload_with_existing_local_file(tmp_path):
    """Local existing Path or str file is uploaded via _upload_bytes."""
    dummy_file = tmp_path / "actual_pose.png"
    dummy_file.write_bytes(_dummy_png("red", (64, 64)))

    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner._upload_bytes = MagicMock(return_value="uploaded_pf_12345.png")

    # Pass as Path object
    uploaded_path = runner._resolve_upload(dummy_file)
    assert uploaded_path == "uploaded_pf_12345.png"
    assert runner._upload_bytes.call_count == 1

    # Pass as str pointing to existing file
    runner._upload_bytes.reset_mock()
    uploaded_str = runner._resolve_upload(str(dummy_file))
    assert uploaded_str == "uploaded_pf_12345.png"
    assert runner._upload_bytes.call_count == 1


def test_resolve_upload_with_raw_bytes():
    """Raw image bytes are uploaded directly."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner._upload_bytes = MagicMock(return_value="uploaded_bytes_67890.png")

    raw_bytes = _dummy_png("yellow", (32, 32))
    uploaded = runner._resolve_upload(raw_bytes)
    assert uploaded == "uploaded_bytes_67890.png"
    runner._upload_bytes.assert_called_once_with(raw_bytes)


def test_shotspec_path_conversion_in_compile_controlnet_conditioning():
    """ShotSpec accepts Path objects and compile_controlnet_conditioning normalizes to strings."""
    spec = ShotSpec(
        shot="medium",
        pose_image=Path("assets/poses/ninja_leap.png"),
        depth_image=Path("assets/depth/courtyard.png"),
    )
    cond = compile_controlnet_conditioning(spec, (1024, 1024))
    assert isinstance(cond["pose_image"], str)
    assert isinstance(cond["depth_image"], str)
    assert "assets" in cond["pose_image"]
    assert "assets" in cond["depth_image"]


# ==============================================================================
# Suite 5: Single-Conditioning Neutralization Behavior
# ==============================================================================

def test_single_conditioning_pose_only_neutralizes_depth_cleanly():
    """When only pose_image is supplied, depth is neutralized to strength 0.0 with pose image filename."""
    client = MockComfyClient()
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = client
    runner.engine = "sdxl"
    runner.style = "tags"
    reg = ComfyWorkflowRegistry()
    runner.sdxl_controlnet = (reg.load("anime_sdxl_controlnet")[0], reg.metadata("anime_sdxl_controlnet"))
    runner.controlnet_ready = True

    runner.generate(
        pos="hero", neg="lowres", seed=42, width=1024, height=1024, prefix="test_pose_only",
        pose_image="my_pose.png", depth_image=None,
        pose_weight=0.85, depth_weight=0.6
    )

    submitted = client.prompts_submitted[-1]
    # Pose node 6 LoadImage has my_pose.png, node 7 ControlNetApplyAdvanced has strength 0.85
    assert submitted["6"]["inputs"]["image"] == "my_pose.png"
    assert submitted["7"]["inputs"]["strength"] == 0.85

    # Depth node 9 LoadImage reuses my_pose.png, but node 10 ControlNetApplyAdvanced is neutralized to 0.0
    assert submitted["9"]["inputs"]["image"] == "my_pose.png"
    assert submitted["10"]["inputs"]["strength"] == 0.0


def test_single_conditioning_depth_only_neutralizes_pose_cleanly():
    """When only depth_image is supplied, pose is neutralized to strength 0.0 with depth image filename."""
    client = MockComfyClient()
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = client
    runner.engine = "sdxl"
    runner.style = "tags"
    reg = ComfyWorkflowRegistry()
    runner.sdxl_controlnet = (reg.load("anime_sdxl_controlnet")[0], reg.metadata("anime_sdxl_controlnet"))
    runner.controlnet_ready = True

    runner.generate(
        pos="landscape", neg="lowres", seed=42, width=1344, height=768, prefix="test_depth_only",
        pose_image=None, depth_image="my_depth.png",
        pose_weight=0.75, depth_weight=0.9
    )

    submitted = client.prompts_submitted[-1]
    # Pose node 6 LoadImage reuses my_depth.png, and node 7 is neutralized to 0.0
    assert submitted["6"]["inputs"]["image"] == "my_depth.png"
    assert submitted["7"]["inputs"]["strength"] == 0.0

    # Depth node 9 LoadImage has my_depth.png, and node 10 has strength 0.9
    assert submitted["9"]["inputs"]["image"] == "my_depth.png"
    assert submitted["10"]["inputs"]["strength"] == 0.9


def test_dual_conditioning_preserves_both_distinct_modalities():
    """When both pose and depth are supplied, neither is neutralized."""
    client = MockComfyClient()
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = client
    runner.engine = "sdxl"
    runner.style = "tags"
    reg = ComfyWorkflowRegistry()
    runner.sdxl_controlnet = (reg.load("anime_sdxl_controlnet")[0], reg.metadata("anime_sdxl_controlnet"))
    runner.controlnet_ready = True

    runner.generate(
        pos="hero", neg="lowres", seed=42, width=1024, height=1024, prefix="test_dual",
        pose_image="skeletal_pose.png", depth_image="depth_map.png",
        pose_weight=0.7, depth_weight=0.55
    )

    submitted = client.prompts_submitted[-1]
    assert submitted["6"]["inputs"]["image"] == "skeletal_pose.png"
    assert submitted["7"]["inputs"]["strength"] == 0.7
    assert submitted["9"]["inputs"]["image"] == "depth_map.png"
    assert submitted["10"]["inputs"]["strength"] == 0.55


# ==============================================================================
# Suite 6: Preflight & Graceful Fallback Stress Testing
# ==============================================================================

def test_runner_fallback_when_controlnet_loader_missing(monkeypatch):
    """If ControlNetLoader node is missing from ComfyUI, preflight fails and generation falls back."""
    client = MockComfyClient()
    reg = ComfyWorkflowRegistry()

    # Artificially remove ControlNetLoader from node types
    orig_preflight = reg.preflight
    def fake_preflight(wid):
        res = orig_preflight(wid)
        if wid == "anime_sdxl_controlnet":
            res["ready"] = False
            res["missing_nodes"] = ["ControlNetLoader"]
        return res

    monkeypatch.setattr(reg, "preflight", fake_preflight)

    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = client
    runner.engine = "sdxl"
    runner.style = "tags"
    runner.workflow, runner.meta = reg.load("anime_sdxl")[0], reg.metadata("anime_sdxl")
    runner.ipa = None
    runner.ipa2 = None
    runner.flux = None
    runner.qwen = None

    pre = reg.preflight("anime_sdxl_controlnet")
    runner.sdxl_controlnet = None if not pre["ready"] else (reg.load("anime_sdxl_controlnet")[0], reg.metadata("anime_sdxl_controlnet"))
    runner.controlnet_ready = runner.sdxl_controlnet is not None

    # Even though pose_image is specified, it MUST fall back to base anime_sdxl without raising
    out = runner.generate(
        pos="knight", neg="lowres", seed=10, width=1024, height=1024, prefix="fallback_test",
        pose_image="pose.png", pose_weight=0.8
    )
    assert len(out) > 0
    submitted = client.prompts_submitted[-1]
    # Check that base anime_sdxl was submitted (node 5 is KSampler in anime_sdxl, node 11 is KSampler in controlnet)
    assert "5" in submitted
    assert submitted["5"]["class_type"] == "KSampler"
    assert "7" not in submitted or submitted["7"]["class_type"] != "ControlNetApplyAdvanced"


def test_generate_art_end_to_end_with_adversarial_spec(tmp_path):
    """End-to-end generate_art execution with extreme weights and non-standard action."""
    spec = ShotSpec(
        shot="wide",
        camera="dutch_tilt_45",
        pose_image="poses/combat_leap.png",
        depth_image="depth/temple_clash.png",
        pose_weight=-0.5,
        depth_weight=2.0,
        characters=[CharPose(id="hero", pose="jumping backflip", action="striking downward with great force")],
    )
    story = _make_story(spec=spec)

    captured_calls = []
    class CapturingRunner:
        engine = "sdxl"
        style = "tags"
        def generate(self, pos, neg, seed, w, h, prefix, pose_image=None, depth_image=None,
                     pose_weight=None, depth_weight=None, **kw):
            captured_calls.append({
                "prefix": prefix,
                "w": w, "h": h,
                "pose_image": pose_image,
                "depth_image": depth_image,
                "pose_weight": pose_weight,
                "depth_weight": depth_weight,
            })
            return _dummy_png("purple", (w, h))

    art.generate_art(story, tmp_path, CapturingRunner())
    panel_calls = [c for c in captured_calls if "panel_p001" in c["prefix"]]
    assert len(panel_calls) == 1
    p_call = panel_calls[0]
    assert p_call["pose_image"] == "poses/combat_leap.png"
    assert p_call["depth_image"] == "depth/temple_clash.png"
    assert p_call["pose_weight"] == -0.5
    assert p_call["depth_weight"] == 2.0


def test_weight_change_invalidates_cache_key(tmp_path):
    """Changing only conditioning weights must invalidate the panel cache and trigger redraw."""
    spec_a = ShotSpec(shot="medium", pose_image="pose_ref.png", pose_weight=0.75)
    story_a = _make_story(spec=spec_a)

    captured_calls = []
    class CapturingRunner:
        engine = "sdxl"
        style = "tags"
        def generate(self, pos, neg, seed, w, h, prefix, pose_image=None, depth_image=None,
                     pose_weight=None, depth_weight=None, **kw):
            captured_calls.append({"pose_weight": pose_weight, "prefix": prefix})
            return _dummy_png("green", (w, h))

    runner = CapturingRunner()
    # First pass: generates panel
    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in captured_calls if "panel_p001" in c["prefix"]]) == 1

    # Second pass: identical weights reuses cache
    captured_calls.clear()
    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in captured_calls if "panel_p001" in c["prefix"]]) == 0

    # Third pass: modified pose_weight from 0.75 -> 0.35 must invalidate cache
    spec_b = ShotSpec(shot="medium", pose_image="pose_ref.png", pose_weight=0.35)
    story_b = _make_story(spec=spec_b)
    captured_calls.clear()
    art.generate_art(story_b, tmp_path, runner)
    assert len([c for c in captured_calls if "panel_p001" in c["prefix"]]) == 1
    assert captured_calls[-1]["pose_weight"] == 0.35


def test_tag_only_conditioning_does_not_trigger_controlnet_workflow(tmp_path):
    """When only semantic control tags are present without image files, base generation is used."""
    spec = ShotSpec(
        shot="medium",
        characters=[CharPose(id="hero", pose="standing", action="pointing")],
    )
    story = _make_story(spec=spec)

    captured_calls = []
    class CapturingRunner:
        engine = "sdxl"
        style = "tags"
        def generate(self, pos, neg, seed, w, h, prefix, pose_image=None, depth_image=None,
                     pose_weight=None, depth_weight=None, **kw):
            captured_calls.append({"pose_image": pose_image, "depth_image": depth_image})
            return _dummy_png("blue", (w, h))

    runner = CapturingRunner()
    art.generate_art(story, tmp_path, runner)
    assert captured_calls[-1]["pose_image"] is None
    assert captured_calls[-1]["depth_image"] is None


def test_missing_single_model_triggers_clean_fallback(monkeypatch):
    """When only one required model is missing from preflight, fallback operates seamlessly."""
    client = MockComfyClient()
    reg = ComfyWorkflowRegistry()

    orig_preflight = reg.preflight
    def fake_preflight(wid):
        res = orig_preflight(wid)
        if wid == "anime_sdxl_controlnet":
            res["ready"] = False
            res["missing_models"] = ["controlnet-depth-sdxl-1.0.safetensors"]
        return res

    monkeypatch.setattr(reg, "preflight", fake_preflight)

    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    runner.client = client
    runner.engine = "sdxl"
    runner.style = "tags"
    runner.workflow, runner.meta = reg.load("anime_sdxl")[0], reg.metadata("anime_sdxl")
    runner.ipa = None
    runner.ipa2 = None
    runner.flux = None
    runner.qwen = None

    pre = reg.preflight("anime_sdxl_controlnet")
    runner.sdxl_controlnet = None if not pre["ready"] else (reg.load("anime_sdxl_controlnet")[0], reg.metadata("anime_sdxl_controlnet"))
    runner.controlnet_ready = runner.sdxl_controlnet is not None

    assert not runner.controlnet_ready
    out = runner.generate(
        pos="hero", neg="lowres", seed=1, width=1024, height=1024, prefix="single_model_missing",
        pose_image="pose.png", depth_image="depth.png"
    )
    assert len(out) > 0
    submitted = client.prompts_submitted[-1]
    # Anime SDXL workflow used, not ControlNet
    assert submitted["5"]["class_type"] == "KSampler"


def test_windows_path_with_backslashes_and_drive_letters():
    """Windows backslash paths and drive letters are safely processed by resolve_upload."""
    runner = art.ComfyRunner.__new__(art.ComfyRunner)
    win_path = r"C:\ComfyUI\input\custom_pose.png"
    resolved = runner._resolve_upload(win_path)
    assert resolved == win_path
