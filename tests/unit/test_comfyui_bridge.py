"""Unit tests for MotionComfyUIBridge and Wan2.1 Fun-Control graph composition."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from engine.motion_bank.comfyui_bridge import (
    MotionComfyUIBridge,
    build_wan21_pose_control_graph,
)


def test_build_wan21_pose_control_graph_structure():
    """Verifies that the generated Wan 2.1 Fun-Control ComfyUI graph contains all required nodes and links."""
    graph = build_wan21_pose_control_graph(
        image_filename="heroine.png",
        control_video_filename="control.mp4",
        prompt="A warrior performing a spinning strike",
        negative_prompt="blurry, distorted",
        width=832,
        height=480,
    )

    # 1. Check critical node class types
    class_types = {node_data["class_type"] for node_data in graph.values()}
    assert "UNETLoader" in class_types
    assert "CLIPLoader" in class_types
    assert "VAELoader" in class_types
    assert "LoadImage" in class_types
    assert "VHS_LoadVideo" in class_types
    assert "WanFunControlApply" in class_types
    assert "KSampler" in class_types
    assert "VHS_VideoCombine" in class_types

    # 2. Check input links
    apply_node = next(n for n in graph.values() if n["class_type"] == "WanFunControlApply")
    assert apply_node["inputs"]["width"] == 832
    assert apply_node["inputs"]["height"] == 480


def test_prepare_input_media(tmp_path: Path):
    """Tests staging of character image and control video into ComfyUI input folder."""
    input_dir = tmp_path / "comfy_input"
    output_dir = tmp_path / "comfy_output"

    img_file = tmp_path / "hero.png"
    img_file.write_text("dummy-image-bytes")
    vid_file = tmp_path / "dance_control.mp4"
    vid_file.write_text("dummy-video-bytes")

    bridge = MotionComfyUIBridge(input_dir=input_dir, output_dir=output_dir)
    img_name, vid_name = bridge.prepare_input_media(img_file, vid_file)

    assert (input_dir / img_name).exists()
    assert (input_dir / vid_name).exists()
    assert img_name == "hero.png"
    assert vid_name == "dance_control.mp4"


def test_render_pose_video_mocked(tmp_path: Path):
    """Verifies workflow dispatch and polling loop with mocked ComfyUIClient."""
    mock_client = MagicMock()
    mock_client.submit_prompt.return_value = "prompt_12345"
    mock_client.history.return_value = {
        "prompt_12345": {
            "status": {"status_str": "success"},
            "outputs": {
                "11": {
                    "videos": [{"filename": "wan_pose_gen_00001.mp4", "subfolder": ""}]
                }
            },
        }
    }

    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "wan_pose_gen_00001.mp4").write_text("output-video-data")

    img = tmp_path / "character.png"
    img.write_text("image")
    vid = tmp_path / "pose.mp4"
    vid.write_text("video")

    bridge = MotionComfyUIBridge(client=mock_client, input_dir=input_dir, output_dir=output_dir)
    result = bridge.render_pose_video(
        character_image_path=img,
        control_video_path=vid,
        prompt="Anime fighter",
        poll_interval_s=0.01,
        timeout_s=5.0,
    )

    mock_client.submit_prompt.assert_called_once()
    assert result.name == "wan_pose_gen_00001.mp4"
