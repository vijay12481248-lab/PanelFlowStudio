"""
Unit tests for AnimoraAssetBridge: Rig Parsing, Forward Kinematics, and Canvas Rendering.
"""

import json
from pathlib import Path
import pytest
from PIL import Image
from engine.render.motion.bridge import AnimoraAssetBridge


def test_animora_bridge_load_dict():
    sample_rig = {
        "bones": [
            {"name": "root", "x": 0.0, "y": 0.0, "rotation": 0.0},
            {"name": "torso", "parent": "root", "x": 0.0, "y": -60.0, "rotation": 0.0},
            {"name": "head", "parent": "torso", "x": 0.0, "y": -40.0, "rotation": 0.0},
        ],
        "animations": {
            "walk": {
                "bones": {
                    "torso": {
                        "rotate": [
                            {"time": 0.0, "value": -5.0},
                            {"time": 0.5, "value": 5.0},
                            {"time": 1.0, "value": -5.0},
                        ]
                    }
                }
            }
        },
    }

    bridge = AnimoraAssetBridge()
    bridge.load_from_dict(sample_rig)
    assert len(bridge.bones) == 3
    assert "root" in bridge.bones
    assert "torso" in bridge.bones
    assert "head" in bridge.bones
    assert "walk" in bridge.animations


def test_animora_forward_kinematics_pose_eval():
    sample_rig = {
        "bones": [
            {"name": "root", "x": 100.0, "y": 200.0, "rotation": 0.0},
            {"name": "arm", "parent": "root", "x": 50.0, "y": 0.0, "rotation": 10.0},
        ],
        "animations": {
            "idle": {
                "bones": {
                    "arm": {
                        "rotate": [
                            {"time": 0.0, "value": 0.0},
                            {"time": 1.0, "value": 20.0},
                        ]
                    }
                }
            }
        },
    }

    bridge = AnimoraAssetBridge()
    bridge.load_from_dict(sample_rig)

    # At t=0.5, rotation should be base(10) + interp(10) = 20 deg
    pose = bridge.evaluate_bone_pose("arm", "idle", t_sec=0.5)
    assert abs(pose["rot"] - 20.0) < 0.1
    assert pose["tx"] == 50.0
    assert pose["ty"] == 0.0


def test_animora_render_rig_skeleton():
    sample_rig = {
        "bones": [
            {"name": "root", "x": 0.0, "y": 0.0, "rotation": 0.0},
            {"name": "torso", "parent": "root", "x": 0.0, "y": -50.0, "rotation": 0.0},
            {"name": "arm_l", "parent": "torso", "x": -30.0, "y": -10.0, "rotation": 45.0},
            {"name": "arm_r", "parent": "torso", "x": 30.0, "y": -10.0, "rotation": -45.0},
        ],
        "animations": {
            "pose": {
                "bones": {}
            }
        },
    }

    bridge = AnimoraAssetBridge()
    bridge.load_from_dict(sample_rig)

    canvas = Image.new("RGBA", (400, 400), (0, 0, 0, 255))
    res = bridge.render_rig_skeleton(canvas, anim_name="pose", t_sec=0.0, origin=(200, 250))
    assert res.size == (400, 400)
    # Check that canvas has non-black drawn pixels from skeleton lines
    extrema = res.getextrema()
    # Blue channel should contain drawn cyan lines (0, 240, 255)
    assert extrema[2][1] > 200
