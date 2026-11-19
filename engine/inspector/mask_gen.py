"""Defect Inpainting Mask Synthesizer with Category-Adaptive Padding, Tile Fallback, and Gaussian Feathering."""
from __future__ import annotations

import io
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image

from engine.inspector.schema import DefectRecord


class DefectMaskGenerator:
    """
    Generates 8-bit grayscale PNG inpaint masks from detected visual defects.
    Applies category-adaptive dilation padding, tile-to-bbox coordinate fallback,
    morphological smoothing, and soft Gaussian feathering to prevent hard boundary seams.
    """

    CATEGORY_PADDING = {
        "extra_hands": 0.20,
        "extra_limbs": 0.20,
        "distorted_face": 0.12,
        "extra_head": 0.12,
        "stray_text": 0.08,
        "duplicate_object": 0.08,
    }

    # Deterministic quadrant mapping for unbounded defects flagged by tile review
    TILE_BBOXES: Dict[str, Tuple[float, float, float, float]] = {
        "zoom_hands": (0.15, 0.45, 0.85, 0.95),  # Lower body / lap quadrant
        "zoom_head": (0.20, 0.05, 0.80, 0.45),   # Upper portrait quadrant
        "zoom_center": (0.20, 0.20, 0.80, 0.80), # Central subject framing
        "zoom_left": (0.05, 0.20, 0.50, 0.80),
        "zoom_right": (0.50, 0.20, 0.95, 0.80),
    }

    def __init__(
        self,
        default_padding_ratio: float = 0.15,
        feather_radius: int = 21,
    ):
        self.default_padding_ratio = default_padding_ratio
        # Ensure feather radius is an odd integer for Gaussian kernel
        self.feather_radius = feather_radius if feather_radius % 2 == 1 else feather_radius + 1

    def get_padding_ratio(self, category: str) -> float:
        """Returns defect category-specific padding ratio."""
        return self.CATEGORY_PADDING.get(category, self.default_padding_ratio)

    def generate_mask_with_coverage(
        self,
        width: int,
        height: int,
        defects: List[DefectRecord],
    ) -> Tuple[np.ndarray, float]:
        """
        Synthesizes an 8-bit single-channel mask (H, W) where 255 = inpaint area, 0 = keep.
        Returns tuple of (mask_array, coverage_ratio_float).
        """
        mask = np.zeros((height, width), dtype=np.uint8)

        for d in defects:
            pad_ratio = self.get_padding_ratio(d.category)

            # Resolve bounding box: direct bbox or tile fallback
            bbox = d.bbox
            if bbox is None and d.tile in self.TILE_BBOXES:
                bbox = self.TILE_BBOXES[d.tile]

            # 1. Bounding-box based mask
            if bbox:
                bx1, by1, bx2, by2 = bbox
                x1 = int(round(bx1 * width))
                y1 = int(round(by1 * height))
                x2 = int(round(bx2 * width))
                y2 = int(round(by2 * height))

                # Apply category-specific dilation padding
                bw = x2 - x1
                bh = y2 - y1
                pad_x = int(round(bw * pad_ratio))
                pad_y = int(round(bh * pad_ratio))

                cx1 = max(0, x1 - pad_x)
                cy1 = max(0, y1 - pad_y)
                cx2 = min(width, x2 + pad_x)
                cy2 = min(height, y2 + pad_y)

                cv2.rectangle(mask, (cx1, cy1), (cx2, cy2), 255, -1)

            # 2. Keypoints-based convex hull mask (if available in details)
            pts = d.details.get("keypoints") or d.details.get("points")
            if pts and len(pts) >= 3:
                pixel_pts = np.array(
                    [[int(p[0] * width), int(p[1] * height)] for p in pts],
                    dtype=np.int32,
                )
                hull = cv2.convexHull(pixel_pts)
                cv2.fillConvexPoly(mask, hull, 255)

        # 3. Morphological closing to seal internal pinholes
        if np.any(mask > 0):
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Calculate canvas coverage ratio before feathering
        nonzero_pixels = np.count_nonzero(mask > 10)
        coverage_ratio = float(nonzero_pixels) / float(width * height)

        # 4. Edge feathering via Gaussian Blur (smooth alpha gradient)
        if np.any(mask > 0) and self.feather_radius > 1:
            mask = cv2.GaussianBlur(mask, (self.feather_radius, self.feather_radius), 0)

        return mask, coverage_ratio

    def generate_mask(
        self,
        width: int,
        height: int,
        defects: List[DefectRecord],
    ) -> np.ndarray:
        """Standard mask generator returning numpy array."""
        mask, _ = self.generate_mask_with_coverage(width, height, defects)
        return mask

    def generate_mask_png_with_coverage(
        self,
        width: int,
        height: int,
        defects: List[DefectRecord],
    ) -> Tuple[bytes, float]:
        """Convenience method returning (mask_png_bytes, coverage_ratio)."""
        mask, coverage = self.generate_mask_with_coverage(width, height, defects)
        success, buf = cv2.imencode(".png", mask)
        if not success:
            raise RuntimeError("Failed to encode inpainting mask to PNG.")
        return buf.tobytes(), coverage

    def generate_mask_png(
        self,
        width: int,
        height: int,
        defects: List[DefectRecord],
    ) -> bytes:
        """Convenience method returning PNG bytes directly."""
        png_bytes, _ = self.generate_mask_png_with_coverage(width, height, defects)
        return png_bytes
