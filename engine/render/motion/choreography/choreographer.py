"""
Motion Choreographer: Normalized Fractional Keyframe Sequencing.
Ported from Animora Cortex (animation_templates.py).
Provides duration-agnostic animation sequencing where keyframe timestamps are normalized to [0.0, 1.0]
and scaled smoothly to any scene duration without manual re-keyframing.
"""

from typing import Dict, List, Any, Optional, Tuple
import math
from engine.render.motion.curves import solve_cubic_bezier, interpolate_value, clamp


class MotionChoreographer:
    """
    Manages duration-agnostic keyframe sequences for visual elements and layers.
    """

    def __init__(
        self,
        name: str,
        duration_sec: float = 6.0,
        loop: bool = False,
        keyframes: Optional[List[Dict[str, Any]]] = None,
    ):
        self.name = name
        self.duration_sec = duration_sec
        self.loop = loop
        # Each keyframe: {"t": fraction_in_0_to_1, "roles": {"role_name": {"x": 0, "y": 0, "rot": 0, ...}}}
        self.keyframes = sorted(keyframes or [], key=lambda k: float(k.get("t", 0.0)))

    def add_keyframe(self, t_fraction: float, roles: Dict[str, Dict[str, float]]) -> None:
        """Adds a normalized keyframe at fractional timestamp t in [0.0, 1.0]."""
        self.keyframes.append({"t": clamp(t_fraction), "roles": roles})
        self.keyframes.sort(key=lambda k: float(k["t"]))

    def evaluate_role(
        self,
        role: str,
        t_sec: float,
        duration_sec: Optional[float] = None,
        easing: str = "ease_out_cubic",
    ) -> Dict[str, float]:
        """
        Evaluates the interpolated properties of a given role at timestamp t_sec.
        Returns a dictionary of properties: {"x": ..., "y": ..., "scale": ..., "rot": ..., "opacity": ...}
        """
        total_dur = duration_sec if duration_sec is not None else self.duration_sec
        if total_dur <= 0.001:
            total_dur = 1.0

        if self.loop:
            t_norm = (t_sec % total_dur) / total_dur
        else:
            t_norm = clamp(t_sec / total_dur)

        if not self.keyframes:
            return {"x": 0.0, "y": 0.0, "scale": 1.0, "rot": 0.0, "opacity": 1.0}

        # Filter keyframes that define this role
        role_keys = [k for k in self.keyframes if role in k.get("roles", {})]
        if not role_keys:
            return {"x": 0.0, "y": 0.0, "scale": 1.0, "rot": 0.0, "opacity": 1.0}

        # Boundary checks
        if t_norm <= role_keys[0]["t"]:
            return dict(role_keys[0]["roles"][role])
        if t_norm >= role_keys[-1]["t"]:
            return dict(role_keys[-1]["roles"][role])

        # Find surrounding keyframes
        k_prev = role_keys[0]
        k_next = role_keys[-1]
        for idx in range(len(role_keys) - 1):
            if role_keys[idx]["t"] <= t_norm <= role_keys[idx + 1]["t"]:
                k_prev = role_keys[idx]
                k_next = role_keys[idx + 1]
                break

        t0, t1 = float(k_prev["t"]), float(k_next["t"])
        span = max(0.0001, t1 - t0)
        local_p = (t_norm - t0) / span

        props_prev = k_prev["roles"][role]
        props_next = k_next["roles"][role]

        # Interpolate all shared keys
        result = {}
        all_prop_keys = set(props_prev.keys()).union(props_next.keys())

        for prop in all_prop_keys:
            v0 = float(props_prev.get(prop, 1.0 if "scale" in prop or "opacity" in prop else 0.0))
            v1 = float(props_next.get(prop, v0))
            result[prop] = interpolate_value(v0, v1, local_p, curve=easing)

        return result
