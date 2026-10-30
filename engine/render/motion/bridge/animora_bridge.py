"""
Animora Asset & Motion Bridge for PanelFlow Studio.
Ingests Animora 2D skeletal animation exports, parses bone hierarchies and keyframe timelines,
evaluates forward kinematics, and composites character motion directly onto video canvas.
"""

from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import json
import math
from PIL import Image, ImageDraw


class AnimoraAssetBridge:
    """
    Parses and renders Animora character rigs and animations within PanelFlow Studio.
    """

    def __init__(self, animora_json_path: Optional[str] = None):
        self.rig_data: Dict[str, Any] = {}
        self.bones: Dict[str, Dict[str, Any]] = {}
        self.animations: Dict[str, Dict[str, Any]] = {}
        if animora_json_path:
            self.load_from_file(animora_json_path)

    def load_from_file(self, json_path: str) -> bool:
        """Loads and parses an Animora export JSON document."""
        p = Path(json_path)
        if not p.exists() or not p.is_file():
            return False

        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.rig_data = data
            self.bones = {b.get("name", f"bone_{i}"): b for i, b in enumerate(data.get("bones", []))}
            self.animations = data.get("animations", {})
            return True
        except Exception:
            return False

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """Initializes rig directly from an in-memory dictionary."""
        self.rig_data = data
        self.bones = {b.get("name", f"bone_{i}"): b for i, b in enumerate(data.get("bones", []))}
        self.animations = data.get("animations", {})

    def evaluate_bone_pose(
        self,
        bone_name: str,
        anim_name: str,
        t_sec: float,
    ) -> Dict[str, float]:
        """
        Evaluates the local transform for a specific bone at timestamp t_sec.
        Returns: {"rot": deg, "tx": px, "ty": px, "sx": scale, "sy": scale}
        """
        base_bone = self.bones.get(bone_name, {})
        base_rot = float(base_bone.get("rotation", 0.0))
        base_tx = float(base_bone.get("x", 0.0))
        base_ty = float(base_bone.get("y", 0.0))

        anim = self.animations.get(anim_name, {})
        anim_bones = anim.get("bones", {})
        bone_keys = anim_bones.get(bone_name, {})

        # Rotation keyframes
        rot_keys = bone_keys.get("rotate", [])
        cur_rot = base_rot
        if rot_keys:
            cur_rot += self._interpolate_channel(rot_keys, t_sec, default=0.0)

        # Translation keyframes
        trans_keys = bone_keys.get("translate", [])
        cur_tx, cur_ty = base_tx, base_ty
        if trans_keys:
            cur_tx += self._interpolate_channel(trans_keys, t_sec, key_name="x", default=0.0)
            cur_ty += self._interpolate_channel(trans_keys, t_sec, key_name="y", default=0.0)

        return {"rot": cur_rot, "tx": cur_tx, "ty": cur_ty, "sx": 1.0, "sy": 1.0}

    def _interpolate_channel(
        self,
        keyframes: List[Dict[str, Any]],
        t_sec: float,
        key_name: str = "value",
        default: float = 0.0,
    ) -> float:
        """Linear or stepped interpolation along a keyframe channel."""
        if not keyframes:
            return default
        if len(keyframes) == 1:
            return float(keyframes[0].get(key_name, default))

        # Sort by time
        sorted_keys = sorted(keyframes, key=lambda k: float(k.get("time", 0.0)))
        t_max = float(sorted_keys[-1].get("time", 1.0))
        eff_t = t_sec % t_max if t_max > 0.0 else 0.0

        if eff_t <= sorted_keys[0].get("time", 0.0):
            return float(sorted_keys[0].get(key_name, default))
        if eff_t >= sorted_keys[-1].get("time", 0.0):
            return float(sorted_keys[-1].get(key_name, default))

        for idx in range(len(sorted_keys) - 1):
            k0 = sorted_keys[idx]
            k1 = sorted_keys[idx + 1]
            t0, t1 = float(k0.get("time", 0.0)), float(k1.get("time", 0.0))
            if t0 <= eff_t <= t1:
                p = (eff_t - t0) / max(0.0001, t1 - t0)
                v0 = float(k0.get(key_name, default))
                v1 = float(k1.get(key_name, default))
                return v0 + (v1 - v0) * p

        return default

    def render_rig_skeleton(
        self,
        canvas: Image.Image,
        anim_name: str,
        t_sec: float,
        origin: Tuple[int, int] = (640, 500),
        bone_color: Tuple[int, int, int] = (0, 240, 255),
    ) -> Image.Image:
        """
        Renders a debug visual skeleton wireframe of the Animora rig onto canvas.
        """
        draw = ImageDraw.Draw(canvas)
        ox, oy = origin

        # Forward kinematics: compute world positions
        world_positions: Dict[str, Tuple[float, float, float]] = {}  # bone -> (wx, wy, world_rot)

        for name, bone in self.bones.items():
            parent_name = bone.get("parent")
            pose = self.evaluate_bone_pose(name, anim_name, t_sec)

            if parent_name and parent_name in world_positions:
                px, py, prot = world_positions[parent_name]
                rad = math.radians(prot)
                wx = px + (pose["tx"] * math.cos(rad) - pose["ty"] * math.sin(rad))
                wy = py + (pose["tx"] * math.sin(rad) + pose["ty"] * math.cos(rad))
                wrot = prot + pose["rot"]
            else:
                wx = ox + pose["tx"]
                wy = oy + pose["ty"]
                wrot = pose["rot"]

            world_positions[name] = (wx, wy, wrot)

            # Draw bone connection line to parent
            if parent_name and parent_name in world_positions:
                px, py, _ = world_positions[parent_name]
                draw.line([(int(px), int(py)), (int(wx), int(wy))], fill=bone_color, width=3)
                draw.ellipse([int(wx - 4), int(wy - 4), int(wx + 4), int(wy + 4)], fill=(255, 255, 255))

        return canvas
