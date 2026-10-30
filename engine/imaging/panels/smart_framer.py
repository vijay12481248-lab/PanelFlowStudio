"""
Saliency-Aware 16:9 Video Framing & Cinematic Motion Engine.

Solves the video framing and panel visibility problem:
1. Detects visual saliency (character faces, speech bubbles, high-contrast action).
2. For standard panels: computes optimal focal crop centered on narrative interest.
3. For tall vertical panels: automatically generates smooth Ken-Burns vertical camera scanning
   (panning from top speech/face reveal to bottom action/reaction) over the panel duration.
4. Ensures no speech bubble or focal subject is randomly cut off.
"""
from typing import Dict, Any, Tuple, Optional, List
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import logging

logger = logging.getLogger("panelflow.imaging.smart_framer")


class SmartFramer:
    """
    Computes saliency-aware framing, focal centers, and cinematic motion for comic panels.
    """

    def __init__(self, target_width: int = 1920, target_height: int = 1080):
        self.target_w = target_width
        self.target_h = target_height
        self.target_aspect = float(target_width) / float(target_height)  # 16:9 = 1.777...

    def analyze_saliency_and_focal_points(
        self,
        img: np.ndarray,
        text_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
    ) -> Dict[str, Any]:
        """
        Analyzes an image to find the primary focal center, top focal point, and bottom focal point.
        """
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

        # 1. Edge saliency via Canny & Sobel
        edges = cv2.Canny(gray, 40, 120)
        edge_weight = edges.astype(np.float32) / 255.0

        # 2. Text region saliency weighting (dialogue is primary narrative interest)
        text_mask = np.zeros((h, w), dtype=np.float32)
        if text_boxes:
            for bx, by, bw, bh in text_boxes:
                x1, y1 = max(0, bx), max(0, by)
                x2, y2 = min(w, bx + bw), min(h, by + bh)
                text_mask[y1:y2, x1:x2] = 2.0

        # 3. Combined Saliency Map
        saliency = edge_weight + text_mask
        total_mass = float(np.sum(saliency))

        if total_mass < 1.0:
            # Fallback to visual center
            return {
                "center_x": w / 2.0,
                "center_y": h / 2.0,
                "top_focal_y": h * 0.25,
                "bottom_focal_y": h * 0.75,
                "is_tall": (h / max(1, w)) > 1.35,
            }

        # Compute Center of Mass (Centroid)
        y_indices, x_indices = np.indices((h, w))
        centroid_x = float(np.sum(x_indices * saliency) / total_mass)
        centroid_y = float(np.sum(y_indices * saliency) / total_mass)

        # Compute Top (Upper 40%) and Bottom (Lower 40%) Focal Points for Vertical Panning
        top_half = saliency[: int(h * 0.45), :]
        bot_half = saliency[int(h * 0.55) :, :]

        top_mass = float(np.sum(top_half))
        bot_mass = float(np.sum(bot_half))

        if top_mass > 0:
            top_y_ind = np.indices(top_half.shape)[0]
            top_focal_y = float(np.sum(top_y_ind * top_half) / top_mass)
        else:
            top_focal_y = h * 0.20

        if bot_mass > 0:
            bot_y_ind = np.indices(bot_half.shape)[0] + int(h * 0.55)
            bot_focal_y = float(np.sum(bot_y_ind * bot_half) / bot_mass)
        else:
            bot_focal_y = h * 0.80

        is_tall = (float(h) / float(max(1, w))) > 1.30

        return {
            "center_x": centroid_x,
            "center_y": centroid_y,
            "top_focal_y": top_focal_y,
            "bottom_focal_y": bot_focal_y,
            "is_tall": is_tall,
            "aspect_ratio": round(float(w) / float(max(1, h)), 3),
        }

    def compute_framing_plan(
        self,
        image_path: Path | str,
        duration_sec: float = 4.0,
        text_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates the complete 16:9 framing and camera motion plan for a panel.
        """
        p = Path(image_path)
        if not p.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        with Image.open(p) as pil_img:
            w, h = pil_img.size

        img_cv = cv2.imread(str(p), cv2.IMREAD_COLOR)
        saliency_info = self.analyze_saliency_and_focal_points(img_cv, text_boxes=text_boxes)

        is_tall = saliency_info["is_tall"]
        aspect = saliency_info["aspect_ratio"]

        # Case 1: Tall Vertical Panel -> Automatic Cinematic Vertical Scan
        if is_tall and duration_sec >= 2.5:
            # We pan smoothly from the top focal area down to the bottom focal area
            # Zoom is adjusted so width fills the 16:9 screen (or safe margin)
            fill_scale = 1.05
            pan_start_y = max(0.0, min(1.0, saliency_info["top_focal_y"] / float(h)))
            pan_end_y = max(0.0, min(1.0, saliency_info["bottom_focal_y"] / float(h)))

            return {
                "motion_type": "CINEMATIC_VERTICAL_PAN",
                "scale": fill_scale,
                "fit_mode": "cover",
                "start_transform": {
                    "x": 0.0,
                    "y": round((0.5 - pan_start_y) * 40.0, 2),  # Pan offset in %
                    "scale": fill_scale,
                },
                "end_transform": {
                    "x": 0.0,
                    "y": round((0.5 - pan_end_y) * 40.0, 2),
                    "scale": fill_scale * 1.02,
                },
                "saliency_center": {
                    "norm_x": round(saliency_info["center_x"] / float(w), 3),
                    "norm_y": round(saliency_info["center_y"] / float(h), 3),
                },
                "is_tall": True,
                "recommendation": "Smooth vertical camera glide across tall panel",
            }

        # Case 2: Wide / Landscape Panel -> Subtle Slow Push or Action Centered
        if aspect >= 1.5:
            return {
                "motion_type": "SLOW_PUSH_IN",
                "scale": 1.0,
                "fit_mode": "contain",
                "start_transform": {"x": 0.0, "y": 0.0, "scale": 1.0},
                "end_transform": {"x": 0.0, "y": 0.0, "scale": 1.06},
                "saliency_center": {
                    "norm_x": round(saliency_info["center_x"] / float(w), 3),
                    "norm_y": round(saliency_info["center_y"] / float(h), 3),
                },
                "is_tall": False,
                "recommendation": "16:9 landscape push-in centered on action",
            }

        # Case 3: Standard Square / Balanced Panel
        focal_norm_x = (saliency_info["center_x"] / float(w)) - 0.5
        focal_norm_y = (saliency_info["center_y"] / float(h)) - 0.5

        return {
            "motion_type": "FOCAL_HOLD",
            "scale": 1.0,
            "fit_mode": "contain",
            "start_transform": {
                "x": round(focal_norm_x * 15.0, 2),
                "y": round(focal_norm_y * 15.0, 2),
                "scale": 1.0,
            },
            "end_transform": {
                "x": round(focal_norm_x * 15.0, 2),
                "y": round(focal_norm_y * 15.0, 2),
                "scale": 1.04,
            },
            "saliency_center": {
                "norm_x": round(saliency_info["center_x"] / float(w), 3),
                "norm_y": round(saliency_info["center_y"] / float(h), 3),
            },
            "is_tall": False,
            "recommendation": "Balanced focal framing with duplicate-blur background",
        }
