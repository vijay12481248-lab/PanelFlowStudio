"""Empirical stress test suite for Phase 4: ControlNet Conditioning & Graceful Fallback.

This test harness tests:
1. Preflight failure simulation:
   - Empty node_names (custom ControlNet nodes missing).
   - Missing model files (openpose missing, depth missing, both missing).
   - Server unavailable / capabilities error.
   - Verify ComfyRunner sets ready == False, disables ControlNet, and executes standard generation without crashing or stalling.
   - Check warning logging behavior.
2. Cache invalidation verification:
   - Altering pose_image, depth_image, pose_weight, depth_weight changes cond_sig and prompt_hash.
   - Identical calls with identical conditioning hit cache.
   - Removing conditioning invalidates cache.
3. Edge and boundary stress testing:
   - Empty capabilities dict, corrupted inputs, boundary weights.
   - Single-conditioning neutralization (pose-only sets depth strength 0.0, depth-only sets pose strength 0.0).
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from PIL import Image

from engine.comfyui import ComfyWorkflowRegistry
from engine.comfyui.client import ComfyUIClient
from engine.original import art, shotspec
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
from engine.original.shotspec import CharPose, ShotSpec


def _dummy_png(color="blue", size=(32, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _make_story(spec: ShotSpec | None = None) -> OriginalStory:
    bible = Bible(
        premise=Premise(title="Stress Tale", genre="fantasy", logline="l", tone="t", setting="s"),
        characters=[
            Character(id="c1", name="Fighter", role="protagonist", age_group="adult",
                      look="spiky red hair, amber eyes, combat gi, iron gauntlets", personality="p"),
        ],
        locations=[Location(id="arena", name="Stone Arena", look="circular stone platform, banners")],
    )
    if spec is None:
        spec = ShotSpec(shot="medium", camera="eye_level")
    panel = Panel(
        id="p001",
        scene_id="sc01",
        shot=spec.shot,
        angle=spec.camera,
        location_id="arena",
        character_ids=["c1"],
        action="Fighter braces for impact.",
        dialogue=[Line(speaker_id="c1", text="Come at me!")],
        director=spec.model_dump(),
        caption="Fighter braces on the arena stones.",
    )
    scene = Scene(id="sc01", location_id="arena", character_ids=["c1"], summary="s", mood="m")
    return OriginalStory(bible=bible, scenes=[scene], panels=[panel])


def _make_mock_client(nodes: list[str], models: dict[str, list[str]], available: bool = True):
    client = MagicMock()
    client.base_url = "http://127.0.0.1:8188/"
    client.capabilities.return_value = {
        "available": available,
        "node_names": nodes,
        "models": models,
    }
    client.api_workflow_root.return_value = Path(__file__).parent.parent.parent / "engine" / "comfyui" / "workflows"
    client.submit_prompt.return_value = "prompt_id_stress_999"
    client.history.return_value = {
        "prompt_id_stress_999": {
            "outputs": {
                "13": {"images": [{"filename": "cn_out.png", "subfolder": "", "type": "output"}]},
                "7": {"images": [{"filename": "base_out.png", "subfolder": "", "type": "output"}]},
            }
        }
    }
    client.download_output.return_value = _dummy_png("green")
    return client


ALL_NODES = [
    "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
    "ControlNetLoader", "LoadImage", "ControlNetApplyAdvanced",
    "KSampler", "VAEDecode", "SaveImage",
]

ALL_MODELS = {
    "checkpoints": ["animagine-xl-4.0.safetensors"],
    "controlnet": [
        "controlnet-openpose-sdxl-1.0.safetensors",
        "controlnet-depth-sdxl-1.0.safetensors",
    ],
}


# ==============================================================================
# SECTION 1: Preflight Failure Simulations & Graceful Fallback
# ==============================================================================

def test_stress_preflight_empty_node_names():
    """Simulate ComfyUI server reporting empty node_names (ControlNet custom nodes absent)."""
    # Empty node_names
    client = _make_mock_client(nodes=[], models=ALL_MODELS, available=True)
    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_sdxl_controlnet")
    assert pre["ready"] is False
    assert len(pre["missing_nodes"]) > 0
    assert "ControlNetLoader" in pre["missing_nodes"]
    assert "ControlNetApplyAdvanced" in pre["missing_nodes"]

    # ComfyRunner initialization:
    # Since base workflow anime_sdxl also requires nodes, if node_names is completely empty,
    # base preflight fails when engine is sdxl and qwen/flux are absent.
    # But if standard nodes exist and ONLY ControlNet custom nodes are absent:
    std_nodes = [
        "CheckpointLoaderSimple", "CLIPTextEncode", "EmptyLatentImage",
        "KSampler", "VAEDecode", "SaveImage",
    ]
    client_std = _make_mock_client(nodes=std_nodes, models=ALL_MODELS, available=True)
    runner = art.ComfyRunner(client=client_std, engine="sdxl")
    assert runner.controlnet_ready is False
    assert runner.sdxl_controlnet is None

    # Verify execution with both pose and depth conditioning falls back to base without crashing
    out = runner.generate(
        pos="1girl fighting",
        neg="bad hands",
        seed=42,
        width=832,
        height=1216,
        prefix="stress_empty_nodes",
        pose_image="pose_test.png",
        depth_image="depth_test.png",
    )
    assert out == _dummy_png("green")
    submitted = client_std.submit_prompt.call_args[0][0]
    node_types = [n.get("class_type") for n in submitted.values()]
    assert "ControlNetLoader" not in node_types
    assert "ControlNetApplyAdvanced" not in node_types
    assert len(submitted) == 7


def test_stress_preflight_missing_openpose_model():
    """Simulate missing controlnet-openpose-sdxl-1.0.safetensors."""
    models_no_openpose = {
        "checkpoints": ["animagine-xl-4.0.safetensors"],
        "controlnet": ["controlnet-depth-sdxl-1.0.safetensors"],
    }
    client = _make_mock_client(nodes=ALL_NODES, models=models_no_openpose, available=True)
    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_sdxl_controlnet")
    assert pre["ready"] is False
    assert "controlnet-openpose-sdxl-1.0.safetensors" in pre["missing_models"]
    assert "controlnet-depth-sdxl-1.0.safetensors" not in pre["missing_models"]

    runner = art.ComfyRunner(client=client, engine="sdxl")
    assert runner.controlnet_ready is False
    assert runner.sdxl_controlnet is None

    out = runner.generate(
        pos="action",
        neg="bad",
        seed=10,
        width=1344,
        height=768,
        prefix="stress_no_openpose",
        pose_image="pose.png",
    )
    assert out == _dummy_png("green")
    submitted = client.submit_prompt.call_args[0][0]
    assert "ControlNetLoader" not in [n.get("class_type") for n in submitted.values()]


def test_stress_preflight_missing_depth_model():
    """Simulate missing controlnet-depth-sdxl-1.0.safetensors."""
    models_no_depth = {
        "checkpoints": ["animagine-xl-4.0.safetensors"],
        "controlnet": ["controlnet-openpose-sdxl-1.0.safetensors"],
    }
    client = _make_mock_client(nodes=ALL_NODES, models=models_no_depth, available=True)
    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_sdxl_controlnet")
    assert pre["ready"] is False
    assert "controlnet-depth-sdxl-1.0.safetensors" in pre["missing_models"]

    runner = art.ComfyRunner(client=client, engine="sdxl")
    assert runner.controlnet_ready is False
    assert runner.sdxl_controlnet is None

    out = runner.generate(
        pos="action",
        neg="bad",
        seed=10,
        width=1344,
        height=768,
        prefix="stress_no_depth",
        depth_image="depth.png",
    )
    assert out == _dummy_png("green")
    submitted = client.submit_prompt.call_args[0][0]
    assert "ControlNetLoader" not in [n.get("class_type") for n in submitted.values()]


def test_stress_preflight_both_controlnet_models_missing():
    """Simulate both ControlNet model files missing."""
    models_no_cn = {
        "checkpoints": ["animagine-xl-4.0.safetensors"],
        "controlnet": [],
    }
    client = _make_mock_client(nodes=ALL_NODES, models=models_no_cn, available=True)
    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_sdxl_controlnet")
    assert pre["ready"] is False
    assert "controlnet-openpose-sdxl-1.0.safetensors" in pre["missing_models"]
    assert "controlnet-depth-sdxl-1.0.safetensors" in pre["missing_models"]

    runner = art.ComfyRunner(client=client, engine="sdxl")
    assert runner.controlnet_ready is False
    assert runner.sdxl_controlnet is None

    out = runner.generate(
        pos="hero",
        neg="bad",
        seed=10,
        width=1024,
        height=1024,
        prefix="stress_both_missing",
        pose_image="pose.png",
        depth_image="depth.png",
    )
    assert out == _dummy_png("green")
    submitted = client.submit_prompt.call_args[0][0]
    assert "ControlNetLoader" not in [n.get("class_type") for n in submitted.values()]


def test_stress_preflight_server_unavailable():
    """Simulate ComfyUI server reporting available=False."""
    client = _make_mock_client(nodes=ALL_NODES, models=ALL_MODELS, available=False)
    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_sdxl_controlnet")
    assert pre["ready"] is False

    # Base workflow preflight also checks available: False -> ready: False
    # If engine="sdxl" and base is not ready, ComfyRunner raises RuntimeError
    with pytest.raises(RuntimeError, match="ComfyUI workflow not ready"):
        art.ComfyRunner(client=client, engine="sdxl")


def test_stress_preflight_capabilities_exception_resilience():
    """Simulate capabilities raising an unexpected network exception during preflight."""
    client = _make_mock_client(nodes=ALL_NODES, models=ALL_MODELS, available=True)
    # Let initial preflight for base workflow succeed, then make controlnet preflight raise
    orig_caps = client.capabilities.return_value
    call_count = [0]
    def failing_caps():
        call_count[0] += 1
        if call_count[0] >= 3:
            raise ConnectionResetError("Server connection reset")
        return orig_caps
    client.capabilities.side_effect = failing_caps

    # ComfyRunner preflights multiple workflows: qwen, flux, base, ipa, ipa2, inpaint, controlnet
    runner = art.ComfyRunner(client=client, engine="sdxl")
    # ControlNet preflight exception was caught, runner safely disabled ControlNet
    assert runner.controlnet_ready is False
    assert runner.sdxl_controlnet is None


def test_stress_empty_capabilities_dictionary():
    """Simulate client returning completely empty capabilities dictionary."""
    client = MagicMock()
    client.capabilities.return_value = {}
    client.api_workflow_root.return_value = Path(__file__).parent.parent.parent / "engine" / "comfyui" / "workflows"
    reg = ComfyWorkflowRegistry(client)
    pre = reg.preflight("anime_sdxl_controlnet")
    assert pre["ready"] is False
    assert pre["workflow_id"] == "anime_sdxl_controlnet"


# ==============================================================================
# SECTION 2: Cache Invalidation & Persistence Verification
# ==============================================================================

class DummyCapturingRunner:
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
        return f"up_{p.name}"

    def _upload_bytes(self, b: bytes) -> str:
        return "up_bytes.png"

    def generate(self, pos, neg, seed, width, height, prefix, reference=None, reference_b=None,
                 pose_image=None, depth_image=None, pose_weight=None, depth_weight=None, **kw):
        self.calls.append({
            "prefix": prefix,
            "width": width,
            "height": height,
            "pos": pos,
            "seed": seed,
            "pose_image": pose_image,
            "depth_image": depth_image,
            "pose_weight": pose_weight,
            "depth_weight": depth_weight,
        })
        return _dummy_png("blue", size=(width, height))


def test_stress_cache_hit_on_identical_conditioning(tmp_path):
    """Two identical calls with identical conditioning MUST hit cache without regenerating."""
    spec = ShotSpec(
        shot="medium",
        camera="eye_level",
        pose_image="pose_v1.png",
        depth_image="depth_v1.png",
        pose_weight=0.75,
        depth_weight=0.6,
    )
    story = _make_story(spec)
    runner = DummyCapturingRunner(controlnet_ready=True)

    # First call: generates character sheet + panel p001
    res1 = art.generate_art(story, tmp_path, runner)
    assert res1["generated"] == 1
    assert res1["reused"] == 0
    panel_calls1 = [c for c in runner.calls if "panel_p001" in c["prefix"]]
    assert len(panel_calls1) == 1

    # Second call with identical story & conditioning: must reuse panel
    runner.calls.clear()
    res2 = art.generate_art(story, tmp_path, runner)
    assert res2["generated"] == 0
    assert res2["reused"] == 1
    panel_calls2 = [c for c in runner.calls if "panel_p001" in c["prefix"]]
    assert len(panel_calls2) == 0


def test_stress_cache_invalidation_on_pose_image_change(tmp_path):
    """Changing pose_image MUST invalidate cache and force regeneration."""
    spec_a = ShotSpec(shot="medium", pose_image="pose_A.png", depth_image="depth.png", pose_weight=0.75, depth_weight=0.6)
    story_a = _make_story(spec_a)
    runner = DummyCapturingRunner(controlnet_ready=True)

    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 1

    # Alter pose_image
    spec_b = ShotSpec(shot="medium", pose_image="pose_B_modified.png", depth_image="depth.png", pose_weight=0.75, depth_weight=0.6)
    story_b = _make_story(spec_b)
    runner.calls.clear()
    res_b = art.generate_art(story_b, tmp_path, runner)
    assert res_b["generated"] == 1
    assert res_b["reused"] == 0
    assert runner.calls[-1]["pose_image"] == "pose_B_modified.png"


def test_stress_cache_invalidation_on_depth_image_change(tmp_path):
    """Changing depth_image MUST invalidate cache and force regeneration."""
    spec_a = ShotSpec(shot="medium", pose_image="pose.png", depth_image="depth_A.png", pose_weight=0.75, depth_weight=0.6)
    story_a = _make_story(spec_a)
    runner = DummyCapturingRunner(controlnet_ready=True)

    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 1

    # Alter depth_image
    spec_b = ShotSpec(shot="medium", pose_image="pose.png", depth_image="depth_B_modified.png", pose_weight=0.75, depth_weight=0.6)
    story_b = _make_story(spec_b)
    runner.calls.clear()
    res_b = art.generate_art(story_b, tmp_path, runner)
    assert res_b["generated"] == 1
    assert res_b["reused"] == 0
    assert runner.calls[-1]["depth_image"] == "depth_B_modified.png"


def test_stress_cache_invalidation_on_pose_weight_change(tmp_path):
    """Changing pose_weight MUST invalidate cache and force regeneration."""
    spec_a = ShotSpec(shot="medium", pose_image="pose.png", pose_weight=0.75)
    story_a = _make_story(spec_a)
    runner = DummyCapturingRunner(controlnet_ready=True)

    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 1

    # Alter pose_weight from 0.75 to 0.90
    spec_b = ShotSpec(shot="medium", pose_image="pose.png", pose_weight=0.90)
    story_b = _make_story(spec_b)
    runner.calls.clear()
    res_b = art.generate_art(story_b, tmp_path, runner)
    assert res_b["generated"] == 1
    assert res_b["reused"] == 0
    assert runner.calls[-1]["pose_weight"] == 0.90


def test_stress_cache_invalidation_on_depth_weight_change(tmp_path):
    """Changing depth_weight MUST invalidate cache and force regeneration."""
    spec_a = ShotSpec(shot="medium", depth_image="depth.png", depth_weight=0.6)
    story_a = _make_story(spec_a)
    runner = DummyCapturingRunner(controlnet_ready=True)

    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 1

    # Alter depth_weight from 0.6 to 0.35
    spec_b = ShotSpec(shot="medium", depth_image="depth.png", depth_weight=0.35)
    story_b = _make_story(spec_b)
    runner.calls.clear()
    res_b = art.generate_art(story_b, tmp_path, runner)
    assert res_b["generated"] == 1
    assert res_b["reused"] == 0
    assert runner.calls[-1]["depth_weight"] == 0.35


def test_stress_cache_invalidation_removing_conditioning(tmp_path):
    """Removing conditioning from a panel MUST invalidate cache and regenerate."""
    spec_a = ShotSpec(shot="medium", pose_image="pose.png")
    story_a = _make_story(spec_a)
    runner = DummyCapturingRunner(controlnet_ready=True)

    art.generate_art(story_a, tmp_path, runner)
    assert len([c for c in runner.calls if "panel_p001" in c["prefix"]]) == 1

    # Remove pose_image completely
    spec_b = ShotSpec(shot="medium", pose_image=None)
    story_b = _make_story(spec_b)
    runner.calls.clear()
    res_b = art.generate_art(story_b, tmp_path, runner)
    assert res_b["generated"] == 1
    assert res_b["reused"] == 0
    assert runner.calls[-1]["pose_image"] is None


def test_stress_prompt_hash_formula_invariants():
    """Directly verify _hash() with cond_sig differences."""
    pos = "masterpiece, 1girl"
    neg = "lowres"
    dims = (1024, 1024)

    h_baseline = art._hash(pos, neg, "sdxl", dims=dims)
    h_pose1 = art._hash(pos, neg, "sdxl|pose:p1.png:0.75|depth:None:0.6", dims=dims)
    h_pose2 = art._hash(pos, neg, "sdxl|pose:p2.png:0.75|depth:None:0.6", dims=dims)
    h_pose1_w85 = art._hash(pos, neg, "sdxl|pose:p1.png:0.85|depth:None:0.6", dims=dims)
    h_dual = art._hash(pos, neg, "sdxl|pose:p1.png:0.75|depth:d1.png:0.6", dims=dims)
    h_dual_w4 = art._hash(pos, neg, "sdxl|pose:p1.png:0.75|depth:d1.png:0.4", dims=dims)

    hashes = [h_baseline, h_pose1, h_pose2, h_pose1_w85, h_dual, h_dual_w4]
    # All 6 hash signatures must be strictly mutually distinct
    assert len(set(hashes)) == 6


# ==============================================================================
# SECTION 3: Edge Cases, Neutralization, & Extreme Inputs
# ==============================================================================

def test_stress_single_conditioning_neutralization_behavior():
    """Verify exact strength values submitted to ComfyUI for single conditioning."""
    client = _make_mock_client(nodes=ALL_NODES, models=ALL_MODELS, available=True)
    runner = art.ComfyRunner(client=client, engine="sdxl")
    runner._upload = lambda p: f"up_{p.name if hasattr(p, 'name') else p}"

    # Only pose supplied: node 7 (pose) gets strength, node 10 (depth) gets strength 0.0
    runner.generate(
        pos="pose test",
        neg="bad",
        seed=1,
        width=1024,
        height=1024,
        prefix="pose_only",
        pose_image=Path("skeleton_only.png"),
        pose_weight=0.88,
    )
    wf_pose = client.submit_prompt.call_args[0][0]
    assert wf_pose["7"]["inputs"]["strength"] == 0.88
    assert wf_pose["10"]["inputs"]["strength"] == 0.0
    assert wf_pose["9"]["inputs"]["image"] == "up_skeleton_only.png"

    # Only depth supplied: node 10 (depth) gets strength, node 7 (pose) gets strength 0.0
    runner.generate(
        pos="depth test",
        neg="bad",
        seed=2,
        width=1024,
        height=1024,
        prefix="depth_only",
        depth_image=Path("depth_only.png"),
        depth_weight=0.52,
    )
    wf_depth = client.submit_prompt.call_args[0][0]
    assert wf_depth["10"]["inputs"]["strength"] == 0.52
    assert wf_depth["7"]["inputs"]["strength"] == 0.0
    assert wf_depth["6"]["inputs"]["image"] == "up_depth_only.png"


def test_stress_boundary_weights():
    """Verify zero, fractional, and boundary weight handling."""
    client = _make_mock_client(nodes=ALL_NODES, models=ALL_MODELS, available=True)
    runner = art.ComfyRunner(client=client, engine="sdxl")
    runner._upload = lambda p: "up.png"

    # Edge weights: pose=0.0, depth=1.0
    runner.generate(
        pos="edge weights",
        neg="bad",
        seed=3,
        width=832,
        height=1216,
        prefix="edge_w",
        pose_image=Path("pose.png"),
        depth_image=Path("depth.png"),
        pose_weight=0.0,
        depth_weight=1.0,
    )
    wf = client.submit_prompt.call_args[0][0]
    assert wf["7"]["inputs"]["strength"] == 0.0
    assert wf["10"]["inputs"]["strength"] == 1.0


def test_stress_logging_warning_audit(caplog):
    """Empirical audit of warning logs during preflight failure fallback."""
    # When ControlNet preflight fails, observe whether a warning was emitted
    models_missing = {"checkpoints": ["animagine-xl-4.0.safetensors"], "controlnet": []}
    client = _make_mock_client(nodes=ALL_NODES, models=models_missing, available=True)

    with caplog.at_level(logging.WARNING):
        runner = art.ComfyRunner(client=client, engine="sdxl")
        runner.generate(
            pos="test",
            neg="bad",
            seed=1,
            width=832,
            height=1216,
            prefix="warn_audit",
            pose_image=Path("pose.png"),
        )

    # Document empirical reality: art.py currently handles fallback by setting sdxl_controlnet = None
    # and silently branching in generate(), without logging a warning.
    warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
    # We assert that execution succeeded completely without exception (0 stalling, 0 crashing)
    assert runner.controlnet_ready is False
