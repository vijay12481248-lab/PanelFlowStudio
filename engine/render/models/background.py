"""Versioned editor/export contract for non-destructive canvas backgrounds."""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class BackgroundSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    version: Literal[1] = 1
    enabled: bool = True
    preset: Literal["none", "solid", "duplicate_blur", "gradient", "mirror", "edge_stretch", "custom_image"] = "duplicate_blur"
    source_mode: Literal["follow_active_visual", "pinned_layer", "custom_image"] = "follow_active_visual"
    source_layer_id: Optional[str] = None
    custom_image_url: Optional[str] = None
    color: str = Field(default="#09090b", pattern=r"^#[0-9a-fA-F]{6}$")
    color_secondary: str = Field(default="#27272a", pattern=r"^#[0-9a-fA-F]{6}$")
    blur_sigma: float = Field(default=32, ge=0, le=100)
    zoom: float = Field(default=1, ge=1, le=3)
    focal_x: float = Field(default=.5, ge=0, le=1)
    focal_y: float = Field(default=.5, ge=0, le=1)
    brightness: float = Field(default=-.04, ge=-1, le=1)
    saturation: float = Field(default=.85, ge=0, le=2)
    tint: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    tint_opacity: float = Field(default=0, ge=0, le=1)
    opacity: float = Field(default=1, ge=0, le=1)
    vignette: float = Field(default=0, ge=0, le=1)
    edge_shadow: float = Field(default=0, ge=0, le=1)
    glow: float = Field(default=0, ge=0, le=1)
    motion: Literal["none", "slow_zoom", "pan_left", "pan_right"] = "none"
    motion_amount: float = Field(default=.08, ge=0, le=.5)
    foreground_fit: Literal["contain", "cover"] = "contain"
    foreground_x: float = Field(default=.5, ge=0, le=1)
    foreground_y: float = Field(default=.5, ge=0, le=1)
    auto_only_when_needed: bool = True
