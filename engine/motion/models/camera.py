"""
Normalized camera and viewport models for PanelFlow Motion Director.
"""
from typing import Optional, Tuple
from pydantic import BaseModel, Field


class NormalizedRect(BaseModel):
    """
    Represents a normalized bounding box or region in 0.0 to 1.0 coordinate space.
    x, y represent top-left origin.
    """
    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    width: float = Field(default=1.0, gt=0.0, le=1.0)
    height: float = Field(default=1.0, gt=0.0, le=1.0)

    @property
    def center_x(self) -> float:
        return self.x + (self.width / 2.0)

    @property
    def center_y(self) -> float:
        return self.y + (self.height / 2.0)

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(self.height, 1e-6)

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def clamp(self) -> "NormalizedRect":
        clamped_x = max(0.0, min(1.0, self.x))
        clamped_y = max(0.0, min(1.0, self.y))
        max_w = 1.0 - clamped_x
        max_h = 1.0 - clamped_y
        clamped_w = max(0.01, min(max_w, self.width))
        clamped_h = max(0.01, min(max_h, self.height))
        return NormalizedRect(x=round(clamped_x, 4), y=round(clamped_y, 4), width=round(clamped_w, 4), height=round(clamped_h, 4))

    def contains_point(self, px: float, py: float) -> bool:
        return self.x <= px <= self.right and self.y <= py <= self.bottom

    def to_pixel_box(self, canvas_w: int, canvas_h: int) -> Tuple[int, int, int, int]:
        """Convert normalized (x, y, w, h) to pixel (left, top, right, bottom)."""
        left = int(round(self.x * canvas_w))
        top = int(round(self.y * canvas_h))
        right = int(round(self.right * canvas_w))
        bottom = int(round(self.bottom * canvas_h))
        return (left, top, right, bottom)


class CameraState(BaseModel):
    """
    Normalized camera position, zoom factor, and optional rotation.
    center_x and center_y are normalized coordinates in [0.0, 1.0].
    zoom: 1.0 means the camera view spans the full available visual dimension.
          >1.0 zooms in (e.g. 1.25 = 25% closer).
    """
    center_x: float = Field(default=0.5, ge=0.0, le=1.0)
    center_y: float = Field(default=0.5, ge=0.0, le=1.0)
    zoom: float = Field(default=1.0, ge=0.5, le=4.0)
    rotation: float = Field(default=0.0, ge=-180.0, le=180.0)
    crop: Optional[NormalizedRect] = None

    def visible_rect(self, target_aspect: float = 16.0 / 9.0, source_aspect: float = 1.0) -> NormalizedRect:
        """
        Calculates the normalized bounding rect visible to the camera in source coordinate space.
        Accounts for zoom and aspect ratio fitting.
        """
        # Base scale in source coordinates
        # If source is wider than target aspect, height is the constraint; otherwise width.
        z = max(self.zoom, 0.5)

        if source_aspect >= target_aspect:
            vis_h = 1.0 / z
            vis_w = (vis_h * target_aspect) / source_aspect
        else:
            vis_w = 1.0 / z
            vis_h = (vis_w / target_aspect) * source_aspect

        vis_w = min(1.0, vis_w)
        vis_h = min(1.0, vis_h)

        left = self.center_x - (vis_w / 2.0)
        top = self.center_y - (vis_h / 2.0)

        # Clamp safely within source bounds
        if left < 0.0:
            left = 0.0
        elif left + vis_w > 1.0:
            left = 1.0 - vis_w

        if top < 0.0:
            top = 0.0
        elif top + vis_h > 1.0:
            top = 1.0 - vis_h

        return NormalizedRect(
            x=round(left, 4),
            y=round(top, 4),
            width=round(vis_w, 4),
            height=round(vis_h, 4),
        )


class TargetResolution(BaseModel):
    """
    Canvas/output display dimensions and frame rate.
    """
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    fps: int = Field(default=30, gt=0)
    aspect_ratio: str = Field(default="16:9")

    @property
    def numeric_aspect(self) -> float:
        if self.height <= 0:
            return 16.0 / 9.0
        return self.width / self.height

    @classmethod
    def standard_1080p(cls) -> "TargetResolution":
        return cls(width=1920, height=1080, fps=30, aspect_ratio="16:9")

    @classmethod
    def portrait_shorts(cls) -> "TargetResolution":
        return cls(width=1080, height=1920, fps=30, aspect_ratio="9:16")

    @classmethod
    def cinema_4k(cls) -> "TargetResolution":
        return cls(width=3840, height=2160, fps=60, aspect_ratio="16:9")
