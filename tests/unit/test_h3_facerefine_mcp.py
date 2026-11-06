"""Unit tests for MiniMax H3 FaceRefine, 2K Upscale, and MCP agent guidance."""
import os
import pytest
from pathlib import Path

from engine.comfyui.registry import ComfyWorkflowRegistry
from engine.comfyui.service import _patch_workflow
from engine.chronoflow.pipeline import ChronoFlowPipeline
from engine.original.shotspec import ShotSpec, CharPose, compose_motion_prompt
from engine.mcp.registry import registry as mcp_registry
import engine.mcp.tools.chronoflow_tools  # noqa: F401 registers tools


@pytest.fixture(autouse=True)
def set_workflow_dir():
    old = os.environ.get("PANELFLOW_COMFYUI_WORKFLOW_DIR")
    os.environ["PANELFLOW_COMFYUI_WORKFLOW_DIR"] = "engine/comfyui/workflows"
    yield
    if old:
        os.environ["PANELFLOW_COMFYUI_WORKFLOW_DIR"] = old
    else:
        os.environ.pop("PANELFLOW_COMFYUI_WORKFLOW_DIR", None)


def test_h3_facerefine_workflow_registration():
    reg = ComfyWorkflowRegistry()
    workflow, checksum = reg.load("minimax_h3_facerefine_i2v")
    assert isinstance(workflow, dict)
    assert len(workflow) == 17
    assert checksum == "9a872d98d2fa33f500cc9ebfaa89e55ed8c1637e82059c825df7f3736bf2c5f9"

    meta = reg.metadata("minimax_h3_facerefine_i2v")
    assert meta["id"] == "minimax_h3_facerefine_i2v"
    assert "H3FaceTrackCrop" in meta["required_nodes"]
    assert "H3FaceStitch" in meta["required_nodes"]
    assert "face_yolov8m.pt" in meta["model_files"]


def test_h3_upscale_2k_workflow_registration():
    reg = ComfyWorkflowRegistry()
    workflow, checksum = reg.load("minimax_h3_upscale_2k")
    assert isinstance(workflow, dict)
    assert len(workflow) == 16
    assert checksum == "9a8227189ac92ea2770895fda80d21a154202c4d7b11a9c6551cad9b8d6b8931"

    meta = reg.metadata("minimax_h3_upscale_2k")
    assert meta["id"] == "minimax_h3_upscale_2k"
    assert "ImageScaleBy" in meta["required_nodes"]


def test_pipeline_build_h3_prompt_with_face_refine():
    pipeline = ChronoFlowPipeline()
    graph = pipeline.build_h3_prompt(
        prompt="Commander Maya walking through crowded neon street",
        width=1344,
        height=768,
        length=124,
        steps=8,
        lora_name="minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        workflow_mode="sliding_window",
        first_frame_filename="crowd_scene.png",
        seed=42,
        face_refine=True,
    )

    assert "face_track_crop" in graph
    assert graph["face_track_crop"]["class_type"] == "H3FaceTrackCrop"
    assert graph["face_track_crop"]["inputs"]["detector"] == "face_yolov8m.pt"
    assert graph["face_track_crop"]["inputs"]["images"] == ["13", 0]

    assert "face_stitch" in graph
    assert graph["face_stitch"]["class_type"] == "H3FaceStitch"
    assert graph["face_stitch"]["inputs"]["base_images"] == ["13", 0]
    assert graph["face_stitch"]["inputs"]["refined_crops"] == ["face_track_crop", 0]
    assert graph["face_stitch"]["inputs"]["transform"] == ["face_track_crop", 1]

    # CreateVideo should receive stitched output
    assert graph["15"]["inputs"]["images"] == ["face_stitch", 0]


def test_pipeline_build_h3_prompt_with_2k_upscale():
    pipeline = ChronoFlowPipeline()
    graph = pipeline.build_h3_prompt(
        prompt="Epic landscape drone flight",
        width=1344,
        height=768,
        length=124,
        steps=8,
        lora_name="minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        upscale_mode="2k_latent",
        seed=100,
    )

    assert "upscale_2k" in graph
    assert graph["upscale_2k"]["class_type"] == "ImageScaleBy"
    assert graph["upscale_2k"]["inputs"]["scale_by"] == 1.5
    assert graph["15"]["inputs"]["images"] == ["upscale_2k", 0]


def test_compile_h3_prompt_bokeh_directive():
    pipeline = ChronoFlowPipeline()
    compiled = pipeline.compile_h3_prompt(
        detailed_description="People walking past glowing store fronts in dense market alley.",
        subject_definitions="Maya: Protagonist in dark jacket.",
        bokeh_background=True,
    )

    assert "shallow depth of field" in compiled
    assert "softly blurred in lens bokeh" in compiled


def test_compose_motion_prompt_wide_shot_bokeh():
    spec = ShotSpec(
        shot="wide",
        camera="wide",
        characters=[CharPose(id="c1", action="walking forward", expression="determined", pose="walking")],
        mood="tense night cyberpunk",
    )
    pos, neg = compose_motion_prompt(spec, camera_direction="push_in")

    assert "shallow depth of field" in pos
    assert "soft background bokeh" in pos
    assert "melted face" in neg
    assert "blurry facial features" in neg
    assert "faceless pedestrians" in neg


def test_mcp_chronoflow_tools_face_refine_and_upscale_schema():
    tool = mcp_registry.get_tool("panelflow_chronoflow_generate_video")
    assert tool is not None
    props = tool.input_schema["properties"]
    assert "face_refine" in props
    assert props["face_refine"]["type"] == "boolean"
    assert "upscale_mode" in props
    assert "2k_latent" in props["upscale_mode"]["enum"]
    assert "shallow depth of field" in tool.description
