"""
Layer and 2.5D Parallax models for PanelFlow Motion Director.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid
from engine.motion.models.enums import LayerType


class LayerInstruction(BaseModel):
    """
    Instructions for an individual visual depth plane within a composite shot.
    """
    layer_id: str = Field(default_factory=lambda: f"lay_{uuid.uuid4().hex[:8]}")
    layer_type: LayerType = LayerType.BACKGROUND
    source_uri: Optional[str] = None
    depth: float = Field(default=0.0, description="Relative Z depth: 0.0 is focus plane, <0 background, >0 foreground")
    motion_factor: float = Field(default=1.0, description="Parallax motion scalar (e.g. 0.5 for distant BG, 1.3 for close FG)")
    relative_scale: float = Field(default=1.0, ge=0.1, le=5.0)
    relative_offset_x: float = Field(default=0.0)
    relative_offset_y: float = Field(default=0.0)
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    blend_mode: str = "NORMAL"  # NORMAL, MULTIPLY, SCREEN, OVERLAY


class ParallaxPlan(BaseModel):
    """
    Container for 2.5D multi-plane motion or flat-image fallback.
    """
    enabled: bool = False
    layers: List[LayerInstruction] = Field(default_factory=list)
    fallback_flat: bool = True
    max_parallax_offset: float = 0.08  # Normalized max shift

    @classmethod
    def flat_fallback(cls, source_uri: Optional[str] = None) -> "ParallaxPlan":
        base_layer = LayerInstruction(
            layer_id="layer_flat_base",
            layer_type=LayerType.BACKGROUND,
            source_uri=source_uri,
            depth=0.0,
            motion_factor=1.0,
        )
        return cls(enabled=False, layers=[base_layer], fallback_flat=True)
