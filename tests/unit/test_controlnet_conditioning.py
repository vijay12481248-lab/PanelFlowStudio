"""Unit tests for Phase 4: Skeletal & Depth Conditioning via ControlNet (DWPose / Depth Anything v2)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image
import pytest

from engine.comfyui import ComfyWorkflowRegistry
from engine.comfyui.client import ComfyUIClient
from engine.comfyui.service import ComfyImageGenerationError, _patch_workflow
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


def _dummy_png(color="green", size=(32, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _make_story(spec: ShotSpec | None = None) -> OriginalStory:
    bible = Bible(
        premise=Premise(title="ControlNet Tale", genre="fantasy", logline="l", tone="t", setting="s"),
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


# ==============================================================================
# 1. ShotSpec Pose & Depth Compilation & Backward Compatibility
# ==============================================================================

def test_shotspec_default_fields_backward_compatibility():
    spec = ShotSpec(shot="medium", camera="eye_level")
    assert spec.pose_image is None
    assert spec.depth_image is None
    assert spec.control_pose is None
    assert spec.control_depth is None
    assert spec.pose_weight == 0.75
    assert spec.depth_weight == 0.6

    dump = spec.model_dump()
    assert dump["pose_image"] is None
    assert dump["depth_image"] is None
    assert dump["pose_weight"] == 0.75
    assert dump["depth_weight"] == 0.6


def test_shotspec_explicit_pose_and_depth_fields():
    spec = ShotSpec(
        shot="full",
        camera="low",
        pose_image=Path("poses/standing_combat.png"),
        depth_image="depth/ruins_depth.png",
        control_pose="openpose_standing",
        control_depth="depth_wide_landscape",
        pose_weight=0.85,
        depth_weight=0.5,
    )
    assert str(spec.pose_image).replace("\\", "/").endswith("poses/standing_combat.png")
    assert spec.depth_image == "depth/ruins_depth.png"
    assert spec.control_pose == "openpose_standing"
    assert spec.control_depth == "depth_wide_landscape"
    assert spec.pose_weight == 0.85
    assert spec.depth_weight == 0.5


def test_compile_controlnet_conditioning_defaults():
    spec = ShotSpec(shot="medium", camera="eye_level")
    cond = compile_controlnet_conditioning(spec, (1024, 1024))
    assert cond["pose_image"] is None
    assert cond["depth_image"] is None
    assert cond["pose_weight"] == 0.75
    assert cond["depth_weight"] == 0.6
    assert cond["control_depth"] == "depth_midground"
    assert cond["dims"] == (1024, 1024)
    assert cond["width"] == 1024
    assert cond["height"] == 1024
    assert cond["has_conditioning"] is False


def test_compile_controlnet_conditioning_with_explicit_images():
    spec = ShotSpec(
        shot="medium",
        camera="eye_level",
        pose_image=Path("skeletons/hero_ready.png"),
        depth_image="maps/chamber_depth.png",
        pose_weight=0.9,
        depth_weight=0.45,
    )
    cond = compile_controlnet_conditioning(spec, (1344, 768))
    assert "skeletons/hero_ready.png" in cond["pose_image"].replace("\\", "/")
    assert cond["depth_image"] == "maps/chamber_depth.png"
    assert cond["pose_weight"] == 0.9
    assert cond["depth_weight"] == 0.45
    assert cond["width"] == 1344
    assert cond["height"] == 768
    assert cond["has_conditioning"] is True


def test_compile_controlnet_conditioning_resolves_character_poses():
    spec = ShotSpec(
        shot="full",
        characters=[CharPose(id="hero", pose="sitting cross-legged", action="resting")],
    )
    cond = compile_controlnet_conditioning(spec, (832, 1216))
    assert cond["control_pose"] == "sitting"
    assert cond["pose_image"] is None


def test_compile_controlnet_conditioning_resolves_camera_depth_framing():
    spec_close = ShotSpec(shot="close", camera="eye_level")
    cond_close = compile_controlnet_conditioning(spec_close, (1024, 1024))
    assert cond_close["control_depth"] == "depth_foreground_portrait"

    spec_wide = ShotSpec(shot="wide", camera="eye_level")
    cond_wide = compile_controlnet_conditioning(spec_wide, (1344, 768))
    assert cond_wide["control_depth"] == "depth_wide_landscape"


def test_shotspec_compose_unaffected_by_controlnet_fields():
    story = _make_story()
    spec_plain = ShotSpec(shot="medium", camera="eye_level")
    spec_cond = ShotSpec(
        shot="medium",
        camera="eye_level",
        pose_image="p.png",
        depth_image="d.png",
        pose_weight=0.8,
        depth_weight=0.5,
    )
    pos1, neg1 = shotspec.compose(story, spec_plain, "ruins")
    pos2, neg2 = shotspec.compose(story, spec_cond, "ruins")
    assert pos1 == pos2
    assert neg1 == neg2


# ==============================================================================
# 2. ComfyUI Workflow Registry & Workflow Template Validation
# ==============================================================================

def test_anime_sdxl_controlnet_is_registered_and_checksum_valid():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, checksum = reg.load("anime_sdxl_controlnet")
    entry = reg.metadata("anime_sdxl_controlnet")
    assert entry["id"] == "anime_sdxl_controlnet"
    assert entry["sha256"] == checksum
    assert len(wf) == 13
    assert wf["1"]["class_type"] == "CheckpointLoaderSimple"
    assert wf["5"]["class_type"] == "ControlNetLoader"
    assert wf["7"]["class_type"] == "ControlNetApplyAdvanced"
    assert wf["8"]["class_type"] == "ControlNetLoader"
    assert wf["10"]["class_type"] == "ControlNetApplyAdvanced"


def test_anime_sdxl_controlnet_required_nodes_and_models():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    entry = reg.metadata("anime_sdxl_controlnet")
    required_nodes = set(entry["required_nodes"])
    expected_nodes = {
        "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
        "ControlNetLoader", "LoadImage", "ControlNetApplyAdvanced",
        "KSampler", "VAEDecode", "SaveImage",
    }
    assert expected_nodes <= required_nodes

    models = entry["model_files"]
    assert "animagine-xl-4.0.safetensors" in models
    assert "controlnet-openpose-sdxl-1.0.safetensors" in models
    assert "controlnet-depth-sdxl-1.0.safetensors" in models


def test_anime_sdxl_controlnet_patch_slots():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    entry = reg.metadata("anime_sdxl_controlnet")
    slots = entry["patch_slots"]
    assert "prompt" in slots
    assert "negative_prompt" in slots
    assert "seed" in slots
    assert "width" in slots
    assert "height" in slots
    assert "filename_prefix" in slots
    assert "pose_image" in slots
    assert "depth_image" in slots
    assert "pose_weight" in slots
    assert "depth_weight" in slots


def test_patch_workflow_controlnet_full_patching():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, _ = reg.load("anime_sdxl_controlnet")
    entry = reg.metadata("anime_sdxl_controlnet")

    patched = _patch_workflow(
        wf,
        entry["patch_slots"],
        prompt="1girl, warrior standing",
        negative_prompt="lowres, blurry",
        width=832,
        height=1216,
        seed=12345,
        prefix="cn_test",
        pose_image="hero_openpose.png",
        depth_image="hero_depth.png",
        pose_weight=0.8,
        depth_weight=0.55,
    )
    assert patched["2"]["inputs"]["text"] == "1girl, warrior standing"
    assert patched["3"]["inputs"]["text"] == "lowres, blurry"
    assert patched["4"]["inputs"]["width"] == 832
    assert patched["4"]["inputs"]["height"] == 1216
    assert patched["11"]["inputs"]["seed"] == 12345
    assert patched["13"]["inputs"]["filename_prefix"] == "cn_test"
    assert patched["6"]["inputs"]["image"] == "hero_openpose.png"
    assert patched["9"]["inputs"]["image"] == "hero_depth.png"
    assert patched["7"]["inputs"]["strength"] == 0.8
    assert patched["10"]["inputs"]["strength"] == 0.55


def test_patch_workflow_controlnet_partial_patching():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    wf, _ = reg.load("anime_sdxl_controlnet")
    entry = reg.metadata("anime_sdxl_controlnet")

    # Calling with only pose_image (omitting depth_image and explicit weights)
    patched = _patch_workflow(
        wf,
        entry["patch_slots"],
        prompt="1girl, standing",
        negative_prompt="lowres",
        width=1024,
        height=1024,
        seed=42,
        prefix="cn_pose_only",
        pose_image="pose_sample.png",
    )
    assert patched["6"]["inputs"]["image"] == "pose_sample.png"


def test_patch_workflow_plain_workflow_rejects_controlnet_slots():
    reg = ComfyWorkflowRegistry(ComfyUIClient())
    plain_wf, _ = reg.load("anime_sdxl")
    plain_entry = reg.metadata("anime_sdxl")

    with pytest.raises(ComfyImageGenerationError):
        _patch_workflow(
            plain_wf,
            plain_entry["patch_slots"],
            prompt="p",
            negative_prompt="n",
            width=832,
            height=1216,
            seed=1,
            prefix="test",
            pose_image="pose.png",
        )


# ==============================================================================
# 3. ComfyRunner ControlNet Dispatch & Preflight Verification
# ==============================================================================

def _make_mock_client_with_capabilities(nodes: list[str], models: dict[str, list[str]], available: bool = True):
    client = MagicMock()
    client.base_url = "http://127.0.0.1:8188/"
    client.capabilities.return_value = {
        "available": available,
        "node_names": nodes,
        "models": models,
    }
    client.api_workflow_root.return_value = Path(__file__).parent.parent.parent / "engine" / "comfyui" / "workflows"
    client.submit_prompt.return_value = "pid_test_123"
    client.history.return_value = {
        "pid_test_123": {
            "outputs": {
                "13": {"images": [{"filename": "out_cn.png", "subfolder": "", "type": "output"}]},
                "7": {"images": [{"filename": "out_std.png", "subfolder": "", "type": "output"}]},
            }
        }
    }
    client.download_output.return_value = _dummy_png("blue")
    return client


def _all_sdxl_and_cn_nodes():
    return [
        "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
        "ControlNetLoader", "LoadImage", "ControlNetApplyAdvanced",
        "KSampler", "VAEDecode", "SaveImage",
    ]


def _all_sdxl_and_cn_models():
    return {
        "checkpoints": ["animagine-xl-4.0.safetensors"],
        "controlnet": [
            "controlnet-openpose-sdxl-1.0.safetensors",
            "controlnet-depth-sdxl-1.0.safetensors",
        ],
    }


def test_comfyrunner_preflight_success_initializes_controlnet():
    mock_client = _make_mock_client_with_capabilities(
        nodes=_all_sdxl_and_cn_nodes(),
        models=_all_sdxl_and_cn_models(),
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    assert runner.controlnet_ready is True
    assert runner.sdxl_controlnet is not None
    assert runner.sdxl_controlnet[1]["id"] == "anime_sdxl_controlnet"


def test_comfyrunner_dispatches_controlnet_when_pose_provided():
    mock_client = _make_mock_client_with_capabilities(
        nodes=_all_sdxl_and_cn_nodes(),
        models=_all_sdxl_and_cn_models(),
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    runner._upload = lambda p: f"up_{p.name if hasattr(p, 'name') else p}"
    runner._upload_bytes = lambda b: "up_bytes.png"

    png = runner.generate(
        pos="1girl, action pose",
        neg="lowres",
        seed=101,
        width=832,
        height=1216,
        prefix="cn_run",
        pose_image=Path("action_pose.png"),
        pose_weight=0.8,
    )
    assert png == _dummy_png("blue")
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    # ControlNet workflow has node 5 (ControlNetLoader) and node 7 (ControlNetApplyAdvanced)
    assert "5" in submitted_wf
    assert "7" in submitted_wf
    assert submitted_wf["6"]["inputs"]["image"] == "up_action_pose.png"
    assert submitted_wf["7"]["inputs"]["strength"] == 0.8


def test_comfyrunner_dual_conditioning_pose_and_depth():
    mock_client = _make_mock_client_with_capabilities(
        nodes=_all_sdxl_and_cn_nodes(),
        models=_all_sdxl_and_cn_models(),
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    runner._upload = lambda p: f"up_{p.name if hasattr(p, 'name') else p}"

    runner.generate(
        pos="1girl, complex scene",
        neg="lowres",
        seed=202,
        width=1024,
        height=1024,
        prefix="dual_cn",
        pose_image=Path("skeleton.png"),
        depth_image=Path("depthmap.png"),
        pose_weight=0.75,
        depth_weight=0.6,
    )
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    assert submitted_wf["6"]["inputs"]["image"] == "up_skeleton.png"
    assert submitted_wf["9"]["inputs"]["image"] == "up_depthmap.png"
    assert submitted_wf["7"]["inputs"]["strength"] == 0.75
    assert submitted_wf["10"]["inputs"]["strength"] == 0.6


def test_comfyrunner_single_conditioning_pose_neutralizes_depth():
    mock_client = _make_mock_client_with_capabilities(
        nodes=_all_sdxl_and_cn_nodes(),
        models=_all_sdxl_and_cn_models(),
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    runner._upload = lambda p: "up_pose.png"

    runner.generate(
        pos="pose only",
        neg="lowres",
        seed=303,
        width=832,
        height=1216,
        prefix="pose_only",
        pose_image=Path("pose.png"),
        pose_weight=0.8,
    )
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    # Pose strength active
    assert submitted_wf["7"]["inputs"]["strength"] == 0.8
    # Depth strength neutralized to 0.0 so missing depth map does not cause issues
    assert submitted_wf["10"]["inputs"]["strength"] == 0.0


def test_comfyrunner_single_conditioning_depth_neutralizes_pose():
    mock_client = _make_mock_client_with_capabilities(
        nodes=_all_sdxl_and_cn_nodes(),
        models=_all_sdxl_and_cn_models(),
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    runner._upload = lambda p: "up_depth.png"

    runner.generate(
        pos="depth only",
        neg="lowres",
        seed=404,
        width=1024,
        height=1024,
        prefix="depth_only",
        depth_image=Path("depth.png"),
        depth_weight=0.65,
    )
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    # Depth strength active
    assert submitted_wf["10"]["inputs"]["strength"] == 0.65
    # Pose strength neutralized to 0.0
    assert submitted_wf["7"]["inputs"]["strength"] == 0.0


# ==============================================================================
# 4. Graceful Fallback Handling (Zero Crashing / Zero Stalling)
# ==============================================================================

def test_comfyrunner_fallback_when_models_missing():
    # Only standard animagine-xl is installed; ControlNet weights are absent
    mock_client = _make_mock_client_with_capabilities(
        nodes=_all_sdxl_and_cn_nodes(),
        models={"checkpoints": ["animagine-xl-4.0.safetensors"]},
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    assert runner.controlnet_ready is False
    assert runner.sdxl_controlnet is None

    # Requesting pose conditioning must fall back smoothly to base generation without exception
    png = runner.generate(
        pos="hero standing",
        neg="lowres",
        seed=505,
        width=832,
        height=1216,
        prefix="fallback_test",
        pose_image=Path("missing_model_pose.png"),
    )
    assert png == _dummy_png("blue")
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    # Must use standard anime_sdxl workflow (no ControlNet nodes)
    node_classes = [n.get("class_type") for n in submitted_wf.values()]
    assert "ControlNetLoader" not in node_classes
    assert "ControlNetApplyAdvanced" not in node_classes
    assert len(submitted_wf) == 7


def test_comfyrunner_fallback_when_custom_nodes_missing():
    # Model files exist, but ControlNet custom nodes are not installed
    standard_nodes = [
        "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
        "KSampler", "VAEDecode", "SaveImage",
    ]
    mock_client = _make_mock_client_with_capabilities(
        nodes=standard_nodes,
        models=_all_sdxl_and_cn_models(),
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    assert runner.controlnet_ready is False
    assert runner.sdxl_controlnet is None

    # Falls back gracefully to standard anime_sdxl
    runner.generate(
        pos="hero standing",
        neg="lowres",
        seed=606,
        width=832,
        height=1216,
        prefix="node_fallback",
        depth_image=Path("depth.png"),
    )
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    node_classes = [n.get("class_type") for n in submitted_wf.values()]
    assert "ControlNetLoader" not in node_classes
    assert "ControlNetApplyAdvanced" not in node_classes
    assert len(submitted_wf) == 7


def test_comfyrunner_no_conditioning_uses_standard_workflow():
    # ControlNet is available, but no conditioning is requested
    mock_client = _make_mock_client_with_capabilities(
        nodes=_all_sdxl_and_cn_nodes(),
        models=_all_sdxl_and_cn_models(),
    )
    runner = art.ComfyRunner(client=mock_client, engine="sdxl")
    assert runner.controlnet_ready is True

    runner.generate(
        pos="plain scenery",
        neg="lowres",
        seed=707,
        width=832,
        height=1216,
        prefix="no_cn",
        pose_image=None,
        depth_image=None,
    )
    submitted_wf = mock_client.submit_prompt.call_args[0][0]
    # Dispatches standard workflow because no conditioning was requested
    node_classes = [n.get("class_type") for n in submitted_wf.values()]
    assert "ControlNetLoader" not in node_classes
    assert "ControlNetApplyAdvanced" not in node_classes
    assert len(submitted_wf) == 7


# ==============================================================================
# 5. Pipeline & Cache Invalidation Integration (generate_art)
# ==============================================================================

class CapturingControlNetRunner:
    def __init__(self, controlnet_ready: bool = True):
        self.controlnet_ready = controlnet_ready
        self.sdxl_controlnet = ({}, {}) if controlnet_ready else None
        self.calls = []
        self.style = "tags"
        self.engine = "sdxl"
        self.workflow = {"1": {}}
        self.meta = {"patch_slots": {}}
        self.ipa = None
        self.ipa2 = None
        self.flux = None
        self.flux_pulid = None
        self.qwen = None

    def _upload(self, p: Path) -> str:
        return f"uploaded_{p.name}"

    def _upload_bytes(self, b: bytes) -> str:
        return "uploaded_bytes.png"

    def generate(self, pos, neg, seed, w, h, prefix, reference=None, reference_b=None,
                 pose_image=None, depth_image=None, pose_weight=None, depth_weight=None, **kw):
        self.calls.append({
            "prefix": prefix,
            "w": w,
            "h": h,
            "pos": pos,
            "ref": reference,
            "ref_b": reference_b,
            "pose_image": pose_image,
            "depth_image": depth_image,
            "pose_weight": pose_weight,
            "depth_weight": depth_weight,
        })
        return _dummy_png("red", size=(w, h))


def test_generate_art_extracts_and_passes_controlnet_conditioning(tmp_path):
    spec = ShotSpec(
        shot="medium",
        camera="eye_level",
        pose_image="poses/combat_stance.png",
        depth_image="depth/ruins.png",
        pose_weight=0.8,
        depth_weight=0.5,
    )
    story = _make_story(spec=spec)
    runner = CapturingControlNetRunner(controlnet_ready=True)

    art.generate_art(story, tmp_path, runner)
    # At least one call was for character sheet, and one for panel p001
    panel_calls = [c for c in runner.calls if "panel_p001" in c["prefix"]]
    assert len(panel_calls) == 1
    call = panel_calls[0]
    assert call["pose_image"] == "poses/combat_stance.png"
    assert call["depth_image"] == "depth/ruins.png"
    assert call["pose_weight"] == 0.8
    assert call["depth_weight"] == 0.5


def test_generate_art_cache_invalidation_on_conditioning_change(tmp_path):
    spec_a = ShotSpec(shot="medium", camera="eye_level", pose_image="pose_v1.png")
    story_a = _make_story(spec=spec_a)
    runner = CapturingControlNetRunner(controlnet_ready=True)

    # First run generates panel
    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 1

    # Second run with identical story_a reuses cached panel (0 new panel generations)
    runner.calls.clear()
    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 0

    # Third run with modified pose conditioning invalidates cache and triggers generation
    spec_b = ShotSpec(shot="medium", camera="eye_level", pose_image="pose_v2_altered.png")
    story_b = _make_story(spec=spec_b)
    runner.calls.clear()
    art.generate_art(story_b, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 1
    assert runner.calls[-1]["pose_image"] == "pose_v2_altered.png"


def test_generate_art_graceful_fallback_when_controlnet_unloaded(tmp_path):
    spec = ShotSpec(shot="medium", camera="eye_level", pose_image="pose.png")
    story = _make_story(spec=spec)
    runner = CapturingControlNetRunner(controlnet_ready=False)

    # Should run smoothly without exceptions
    art.generate_art(story, tmp_path, runner)
    panel_calls = [c for c in runner.calls if "panel_p001" in c["prefix"]]
    assert len(panel_calls) == 1
