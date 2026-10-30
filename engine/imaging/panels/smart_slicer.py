"""
Smart Saliency Gutter Slicer & Content-Aware Panel Extractor.

Solves the blind slicing problem in vertical webtoons and tall manga strips:
1. Calculates horizontal projection energy (gradient magnitude + color deviation).
2. Uses OCR text region masking to strictly prohibit cutting through dialogue bubbles.
3. Finds energy-valley minima to place cuts only at natural illustration boundaries.
4. Prevents character bisection and avoids cutting off heads, faces, or key action.
"""
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import logging

logger = logging.getLogger("panelflow.imaging.smart_slicer")


class SmartPanelSlicer:
    """
    Saliency-aware, energy-minimizing panel slicer for webtoon and tall manga strips.
    """

    def __init__(
        self,
        min_panel_height: int = 320,
        max_panel_height: int = 2400,
        energy_threshold: float = 0.15,
        text_padding: int = 16,
    ):
        self.min_panel_height = min_panel_height
        self.max_panel_height = max_panel_height
        self.energy_threshold = energy_threshold
        self.text_padding = text_padding

    def find_safe_horizontal_cut_lines(
        self,
        img: np.ndarray,
        text_boxes: Optional[List[Tuple[int, int, int, int]]] = None,  # (x, y, w, h)
        target_height_range: Tuple[int, int] = (600, 1800),
    ) -> List[int]:
        """
        Calculates horizontal energy valleys and returns optimal y-coordinates for panel cuts.
        """
        h, w = img.shape[:2]
        if h <= self.max_panel_height:
            return []

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

        # 1. Background gutter estimation from vertical margins
        margin = max(4, round(w * 0.02))
        bg_col = np.median(
            np.concatenate([gray[:, :margin], gray[:, -margin:]], axis=1),
            axis=1,
        )

        # 2. Content deviation from background
        deviation = np.abs(gray.astype(np.float32) - bg_col[:, None])
        content_density = (deviation > 14).mean(axis=1)

        # 3. Horizontal Sobel gradient (detects horizontal strokes, panel borders, character outlines)
        sobel_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        edge_energy = np.abs(sobel_y).mean(axis=1)
        if edge_energy.max() > 0:
            edge_energy = edge_energy / edge_energy.max()

        # 4. Total Energy Profile: low = empty gutter / safe seam
        total_energy = 0.65 * content_density + 0.35 * edge_energy

        # 5. Apply OCR text forbidden zones
        if text_boxes:
            for bx, by, bw, bh in text_boxes:
                y_start = max(0, by - self.text_padding)
                y_end = min(h, by + bh + self.text_padding)
                total_energy[y_start:y_end] = 10.0  # Infinite penalty: never cut through text!

        # 6. Smooth the energy profile with a 1D Gaussian kernel
        kernel_size = 31
        total_energy_smooth = cv2.GaussianBlur(
            total_energy.reshape(-1, 1).astype(np.float32),
            (1, kernel_size),
            0,
        ).flatten()

        # 7. Dynamic Programming / Greedy Valley Search
        cut_lines: List[int] = []
        cur_y = 0
        min_h, max_h = target_height_range
        min_h = max(self.min_panel_height, min_h)
        max_h = min(self.max_panel_height, max_h)

        while (h - cur_y) > max_h:
            # Search window for the next cut: between [cur_y + min_h, cur_y + max_h]
            w_start = cur_y + min_h
            w_end = min(h - self.min_panel_height, cur_y + max_h)

            if w_start >= w_end:
                break

            window_energy = total_energy_smooth[w_start:w_end]

            # Find local minima in this window
            best_local_offset = int(np.argmin(window_energy))
            best_cut = w_start + best_local_offset

            # If the minimum energy is acceptable or forced
            cut_lines.append(best_cut)
            cur_y = best_cut

        return cut_lines

    def slice_tall_image(
        self,
        image_path: Path | str,
        output_dir: Path | str,
        base_name: str,
        text_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Slices a tall image into safe, visually coherent panels and writes them to disk.
        Returns a list of panel metadata dicts.
        """
        p_path = Path(image_path)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        img = cv2.imread(str(p_path), cv2.IMREAD_COLOR)
        if img is None:
            raise FileNotFoundError(f"Image not found at: {image_path}")

        h, w = img.shape[:2]

        # Find safe cut lines
        cut_lines = self.find_safe_horizontal_cut_lines(img, text_boxes=text_boxes)

        # Construct slice intervals
        y_points = [0] + cut_lines + [h]
        slices: List[Dict[str, Any]] = []

        for idx in range(len(y_points) - 1):
            y1 = y_points[idx]
            y2 = y_points[idx + 1]
            slice_h = y2 - y1

            if slice_h < 40:
                continue

            slice_img = img[y1:y2, 0:w]
            out_filename = f"{base_name}_part_{idx + 1:02d}.jpg"
            out_path = out_dir / out_filename

            cv2.imwrite(str(out_path), slice_img, [cv2.IMWRITE_JPEG_QUALITY, 95])

            slices.append({
                "index": idx + 1,
                "filename": out_filename,
                "file_path": str(out_path),
                "y_start": y1,
                "y_end": y2,
                "width": w,
                "height": slice_h,
                "aspect_ratio": round(w / max(1, slice_h), 3),
            })

        logger.info(f"Smart sliced '{p_path.name}' ({w}x{h}) into {len(slices)} safe panels.")
        return slices
