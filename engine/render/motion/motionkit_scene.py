"""Adapter that plays a MotionKit JSON spec through PanelFlow's MotionRegistry scene contract."""

import copy
import dataclasses
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image


def _with_narration(spec: Dict[str, Any], narration: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Copy of spec with each {at, audio_path, text, character=0} added as a lip-synced `say` on that character."""
    spec = copy.deepcopy(spec)
    chars = [e for sc in spec.get("scenes", []) for e in sc.get("elements", []) if e.get("type") == "character"]
    for n in narration:
        if chars:
            ch = chars[min(int(n.get("character", 0)), len(chars) - 1)]
            ch.setdefault("timeline", []).append(
                ["say", float(n["at"]), n.get("text") or " ", {"speech": "file", "path": n["audio_path"]}]
            )
    return spec


class MotionKitScene:
    """render_frame(t) -> PIL image, driven by a MotionKit spec (dict or .json path)."""

    def __init__(
        self,
        spec: Optional[Dict[str, Any]] = None,
        spec_path: Optional[str] = None,
        narration: Optional[List[Dict[str, Any]]] = None,
        bounds: Tuple[int, int] = (1280, 720),
        duration_sec: Optional[float] = None,
        **_: Any,
    ):
        try:
            import motionkit as mk
        except ImportError as e:
            raise RuntimeError("MotionKit is not installed: uv pip install -e <path-to-motionkit>") from e
        if not (spec or spec_path):
            raise ValueError("motionkit preset needs props.spec (dict) or props.spec_path (.json file)")
        if narration and spec:
            spec = _with_narration(spec, narration)
        try:
            project = mk.load(spec if spec else spec_path)
        except mk.MotionKitError as e:
            raise ValueError(f"Invalid MotionKit spec: {e}") from e
        self._mk = mk
        self._project = dataclasses.replace(project, width=bounds[0] - bounds[0] % 2, height=bounds[1] - bounds[1] % 2)
        self.duration_sec = duration_sec or project.duration

    def render_frame(self, t: float) -> Image.Image:
        last = max(0.0, self._project.duration - 1.0 / self._project.fps)
        return self._mk.frame(self._project, min(max(t, 0.0), last))
