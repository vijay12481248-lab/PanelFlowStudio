"""Unit tests for MiniMax Fast H3 workflow, patch slots, and motion prompt composition."""
import pytest
from pathlib import Path

from engine.comfyui.client import ComfyUIClient
from engine.comfyui.registry import ComfyWorkflowRegistry
from engine.comfyui.service import _patch_workflow
from engine.original.shotspec import ShotSpec, CharPose, compose_motion_prompt


def test_minimax_h3_workflow_registration():
    registry = ComfyWorkflowRegistry()
    workflow, checksum = registry.load("minimax_h3_turbo_i2v")
    assert isinstance(workflow, dict)
    assert len(workflow) == 15
    assert checksum == "77afb4b99b11ea828bddc9e07d5f68563bb302cb3f8b15a6a99b0d6c004d266e"

    meta = registry.metadata("minimax_h3_turbo_i2v")
    assert meta["id"] == "minimax_h3_turbo_i2v"
    assert meta["purpose"] == "image_to_video"
    assert meta["gpu_vram_mb"] == 14000
    assert "MiniMaxH3ImageToVideo" in meta["required_nodes"]
    assert "LoraLoaderModelOnly" in meta["required_nodes"]
    assert "SaveVideo" in meta["required_nodes"]


def test_minimax_h3_workflow_patch_slots():
    registry = ComfyWorkflowRegistry()
    workflow, _ = registry.load("minimax_h3_turbo_i2v")
    meta = registry.metadata("minimax_h3_turbo_i2v")

    patched = _patch_workflow(
        workflow,
        meta["patch_slots"],
        prompt="cinematic camera push in, glowing aura, 24fps",
        negative_prompt="distortion, jitter, blurry",
        width=1344,
        height=768,
        seed=42,
        prefix="panelflow/test_h3",
        reference_image="test_panel.png",
    )

    # Node 7: MiniMaxH3ImageToVideo
    assert patched["7"]["inputs"]["prompt"] == "cinematic camera push in, glowing aura, 24fps"
    assert patched["7"]["inputs"]["width"] == 1344
    assert patched["7"]["inputs"]["height"] == 768

    # Node 6: Negative CLIPTextEncode
    assert patched["6"]["inputs"]["text"] == "distortion, jitter, blurry"

    # Node 11: RandomNoise seed
    assert patched["11"]["inputs"]["noise_seed"] == 42

    # Node 5: LoadImage reference
    assert patched["5"]["inputs"]["image"] == "test_panel.png"

    # Node 15: SaveVideo prefix
    assert patched["15"]["inputs"]["filename_prefix"] == "panelflow/test_h3"


def test_compose_motion_prompt():
    spec = ShotSpec(
        shot="medium",
        camera="eye_level",
        characters=[CharPose(id="c1", action="raising her sword", expression="determined", pose="standing")],
        mood="epic and tense",
    )

    pos, neg = compose_motion_prompt(spec, camera_direction="pan_right", custom_prompt="sparks falling from above")

    assert "Gentle camera pan from left to right" in pos
    assert "sparks falling from above" in pos
    assert "24fps smooth motion" in pos
    assert "fast jerky motion" in neg
    assert "distorted hands" in neg


def test_compose_motion_prompt_defaults():
    pos, neg = compose_motion_prompt(camera_direction="push_in")
    assert "Slow cinematic camera push in" in pos
    assert "natural subtle movement" in pos
    assert "bad anatomy" in neg
