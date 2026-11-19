"""Flow-guided temporal inpainting engine for video watermark removal.

Implements windowed optical flow propagation to retain authentic background pixels:
1. Crops a localized context window around the watermark bounding box.
2. Flat-black passthrough: detects black intro/outro frames and bypasses inpainting.
3. Bidirectional optical flow propagation: warps uncorrupted background pixels
   from neighboring frames (t-k, t+k) along motion trajectories straight into the mask.
4. Soft-edge feathered compositing: smoothly pastes the cleaned window back onto the source frame.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple
import cv2
import numpy as np

from engine.video.watermark.models import WatermarkBoundingBox


class FlowInpainter:
    def __init__(
        self,
        box: WatermarkBoundingBox,
        feather_px: int = 3,
        context_margin_px: int = 32,
        models_dir: Optional[Path] = None,
    ):
        self.box = box
        self.feather_px = max(0, min(feather_px, 16))
        self.context_margin_px = max(8, min(context_margin_px, 128))
        self.models_dir = models_dir

    def is_flat_black(self, patch: np.ndarray, threshold: float = 3.5) -> bool:
        """Detect pure black or fade-to-black frames to avoid AI hallucination or drift."""
        return float(np.mean(patch)) < threshold and float(np.std(patch)) < threshold

    def compute_window(self, frame_w: int, frame_h: int) -> Tuple[WatermarkBoundingBox, np.ndarray]:
        """
        Calculates the expanded window box and the local watermark mask within that window.
        
        Returns:
            Tuple of (window_box, local_mask) where local_mask is (H_w, W_w) uint8 with 255 at watermark.
        """
        window_box = self.box.expand(self.context_margin_px, frame_w, frame_h)
        local_mask = np.zeros((window_box.height, window_box.width), dtype=np.uint8)

        # Coordinates of the watermark inside the window
        rel_x = self.box.x - window_box.x
        rel_y = self.box.y - window_box.y
        local_mask[rel_y : rel_y + self.box.height, rel_x : rel_x + self.box.width] = 255

        return window_box, local_mask

    def warp_pixels_via_optical_flow(
        self,
        target_patch: np.ndarray,
        source_patch: np.ndarray,
        target_mask: np.ndarray,
        source_mask: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Warps valid (unmasked) pixels from source_patch into target_patch along optical flow vectors.
        Uses flow completion to estimate motion vectors within the masked watermark region.
        """
        h, w = target_patch.shape[:2]

        # Convert to grayscale for flow calculation
        gray_target = cv2.cvtColor(target_patch, cv2.COLOR_BGR2GRAY)
        gray_source = cv2.cvtColor(source_patch, cv2.COLOR_BGR2GRAY)

        # Compute optical flow from target -> source
        flow = cv2.calcOpticalFlowFarneback(
            gray_target, gray_source, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0
        )

        # Flow completion: inpaint motion vectors across target_mask hole
        # so motion of the surrounding background guides pixel warping into the hole
        if np.count_nonzero(target_mask) > 0 and np.count_nonzero(target_mask) < (h * w):
            flow_u = cv2.inpaint(flow[:, :, 0].astype(np.float32), target_mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)
            flow_v = cv2.inpaint(flow[:, :, 1].astype(np.float32), target_mask, inpaintRadius=7, flags=cv2.INPAINT_TELEA)
            flow = np.stack([flow_u, flow_v], axis=-1)

        # Create coordinate map for remapping
        grid_x, grid_y = np.meshgrid(np.arange(w), np.arange(h))
        map_x = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y + flow[:, :, 1]).astype(np.float32)

        # Warp source patch and source mask to target alignment
        warped_source = cv2.remap(source_patch, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        warped_source_mask = cv2.remap(source_mask, map_x, map_y, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=255)

        # Valid donor pixels are those where:
        # 1. Target needs inpainting (target_mask == 255)
        # 2. Source pixel is outside the watermark (warped_source_mask == 0)
        # 3. Warped flow coordinates fall inside image boundaries
        in_bounds = (map_x >= 0) & (map_x < w) & (map_y >= 0) & (map_y < h)
        donor_valid = (target_mask == 255) & (warped_source_mask == 0) & in_bounds

        result_patch = target_patch.copy()
        result_patch[donor_valid] = warped_source[donor_valid]

        remaining_mask = target_mask.copy()
        remaining_mask[donor_valid] = 0

        return result_patch, remaining_mask

    def detect_and_restore_translucent_backdrop(
        self,
        window_patch: np.ndarray,
        rel_box: WatermarkBoundingBox,
    ) -> Tuple[np.ndarray, Optional[float], Optional[np.ndarray]]:
        """
        Detects any translucent backdrop attenuation (e.g. black@0.4 or white@0.3)
        using consistent ambient background columns and algebraically inverts it.
        """
        h_win, w_win = window_patch.shape[:2]
        bx1 = max(0, min(w_win - 1, rel_box.x))
        by1 = max(0, min(h_win - 1, rel_box.y))
        bx2 = max(bx1 + 1, min(w_win, rel_box.x2))
        by2 = max(by1 + 1, min(h_win, rel_box.y2))

        # Sample border margins immediately adjacent to the box (tight 2px margin avoids crossing angled transitions)
        margin_y = min(2, by1, h_win - by2)
        if margin_y < 1:
            return window_patch.copy(), None, None

        top_sample = np.median(window_patch[by1 - margin_y : by1, bx1:bx2], axis=0).astype(float)
        bot_sample = np.median(window_patch[by2 : by2 + margin_y, bx1:bx2], axis=0).astype(float)

        # Ignore black/letterbox columns (mean intensity < 15)
        valid_cols = (np.mean(top_sample, axis=-1) > 15) & (np.mean(bot_sample, axis=-1) > 15)
        color_diff = np.linalg.norm(top_sample - bot_sample, axis=-1)
        # Consistent background columns
        consistent_cols = valid_cols & (color_diff < 25)

        patch = window_patch[by1:by2, bx1:bx2].astype(float)
        ambient_col = (top_sample + bot_sample) / 2.0

        ratio_map = np.mean(patch / np.maximum(ambient_col, 1.0), axis=-1)
        dark_mask = (ratio_map < 0.88)
        bright_mask = (ratio_map > 1.15)

        restored_patch = patch.copy()
        backdrop_ratio = None
        backdrop_mask = None

        if np.count_nonzero(consistent_cols) >= 3:
            consistent_ratios = ratio_map[:, consistent_cols]
            dark_ratios = consistent_ratios[(consistent_ratios > 0.15) & (consistent_ratios < 0.88)]
            bright_ratios = consistent_ratios[(consistent_ratios > 1.12) & (consistent_ratios < 4.0)]

            if len(dark_ratios) > (consistent_ratios.size * 0.10):
                T = float(np.median(dark_ratios))
                if 0.15 <= T <= 0.92:
                    backdrop_ratio = T
                    backdrop_mask = dark_mask
                    restored_patch[backdrop_mask] = np.clip(patch[backdrop_mask] / T, 0, 255)
            elif len(bright_ratios) > (consistent_ratios.size * 0.10):
                T = float(np.median(bright_ratios))
                if 1.08 <= T <= 4.0:
                    backdrop_ratio = T
                    backdrop_mask = bright_mask
                    restored_patch[backdrop_mask] = np.clip(patch[backdrop_mask] / T, 0, 255)

        cleaned_window = window_patch.copy()
        cleaned_window[by1:by2, bx1:bx2] = np.clip(restored_patch, 0, 255).astype(np.uint8)
        return cleaned_window, backdrop_ratio, backdrop_mask

    def extract_watermark_stroke_mask(
        self,
        window_patch: np.ndarray,
        rel_box: WatermarkBoundingBox,
    ) -> np.ndarray:
        """
        Extracts the precise watermark foreground strokes inside the bounding box,
        preserving all authentic background pixels (cracks, textures, color transitions).
        Uses Min-Axis Background Matching: a pixel is background if it matches
        EITHER vertical OR horizontal surrounding background features.
        """
        h_win, w_win = window_patch.shape[:2]
        bx1 = max(0, min(w_win - 1, rel_box.x))
        by1 = max(0, min(h_win - 1, rel_box.y))
        bx2 = max(bx1 + 1, min(w_win, rel_box.x2))
        by2 = max(by1 + 1, min(h_win, rel_box.y2))
        bw = bx2 - bx1
        bh = by2 - by1

        # Border margin around the box to sample ambient background
        margin = min(6, by1, h_win - by2, bx1, w_win - bx2)
        margin = max(2, margin)

        top_b = window_patch[max(0, by1 - margin) : by1, bx1:bx2]
        bot_b = window_patch[by2 : min(h_win, by2 + margin), bx1:bx2]
        left_b = window_patch[by1:by2, max(0, bx1 - margin) : bx1]
        right_b = window_patch[by1:by2, bx2 : min(w_win, bx2 + margin)]

        top_p = np.median(top_b, axis=0, keepdims=True) if top_b.size > 0 else np.zeros((1, bw, 3))
        bot_p = np.median(bot_b, axis=0, keepdims=True) if bot_b.size > 0 else top_p
        left_p = np.median(left_b, axis=1, keepdims=True) if left_b.size > 0 else np.zeros((bh, 1, 3))
        right_p = np.median(right_b, axis=1, keepdims=True) if right_b.size > 0 else left_p

        y_w = np.linspace(0, 1, bh).reshape(-1, 1, 1)
        x_w = np.linspace(0, 1, bw).reshape(1, -1, 1)
        bg_v = (1.0 - y_w) * top_p + y_w * bot_p
        bg_h = (1.0 - x_w) * left_p + x_w * right_p

        patch = window_patch[by1:by2, bx1:bx2].astype(float)

        dist_v = np.minimum(np.linalg.norm(patch - top_p, axis=-1), np.linalg.norm(patch - bot_p, axis=-1))
        dist_v_interp = np.linalg.norm(patch - bg_v, axis=-1)
        dist_v_min = np.minimum(dist_v, dist_v_interp)

        dist_h = np.minimum(np.linalg.norm(patch - left_p, axis=-1), np.linalg.norm(patch - right_p, axis=-1))
        dist_h_interp = np.linalg.norm(patch - bg_h, axis=-1)
        dist_h_min = np.minimum(dist_h, dist_h_interp)

        bg_dist = np.minimum(dist_v_min, dist_h_min)

        gray_patch = cv2.cvtColor(window_patch[by1:by2, bx1:bx2], cv2.COLOR_BGR2GRAY)
        top_gray = cv2.cvtColor(top_b, cv2.COLOR_BGR2GRAY) if top_b.size > 0 else np.zeros((1, bw), dtype=np.uint8)
        bot_gray = cv2.cvtColor(bot_b, cv2.COLOR_BGR2GRAY) if bot_b.size > 0 else top_gray
        gray_bg_v = (1.0 - y_w[:, :, 0]) * np.median(top_gray, axis=0, keepdims=True) + y_w[:, :, 0] * np.median(bot_gray, axis=0, keepdims=True)
        lum_diff = np.abs(gray_patch.astype(float) - gray_bg_v)

        stroke = ((bg_dist > 22) | (lum_diff > 25)).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        dil_stroke = cv2.dilate(stroke, kernel, iterations=2)

        stroke_ratio = np.sum(dil_stroke > 0) / dil_stroke.size
        local_stroke_mask = np.zeros((h_win, w_win), dtype=np.uint8)
        if stroke_ratio < 0.005 or stroke_ratio > 0.90:
            local_stroke_mask[by1:by2, bx1:bx2] = 255
        else:
            local_stroke_mask[by1:by2, bx1:bx2] = dil_stroke

        return local_stroke_mask

    def restore_stationary_domain_features(
        self,
        cleaned_window: np.ndarray,
        rel_box: WatermarkBoundingBox,
    ) -> np.ndarray:
        """
        In stationary/static video scenes, restores authentic background pixels
        and wipes out text/graphic overlay strokes without blurring across color boundaries.
        """
        h_win, w_win = cleaned_window.shape[:2]
        bx1 = max(0, min(w_win - 1, rel_box.x))
        by1 = max(0, min(h_win - 1, rel_box.y))
        bx2 = max(bx1 + 1, min(w_win, rel_box.x2))
        by2 = max(by1 + 1, min(h_win, rel_box.y2))
        bw = bx2 - bx1
        bh = by2 - by1

        margin_y = min(2, by1, h_win - by2)
        if margin_y >= 1:
            top_clean = np.median(cleaned_window[by1 - margin_y : by1, bx1:bx2], axis=0).astype(float)
            bot_clean = np.median(cleaned_window[by2 : by2 + margin_y, bx1:bx2], axis=0).astype(float)
            col_diff = np.linalg.norm(top_clean - bot_clean, axis=-1)
            is_vertical_pattern = np.mean(col_diff < 15) > 0.85

            if is_vertical_pattern:
                patch = cleaned_window[by1:by2, bx1:bx2].astype(float)
                for x in range(bw):
                    c_top = top_clean[x]
                    c_bot = bot_clean[x]
                    if np.linalg.norm(c_top - c_bot) < 25:
                        expected_bg = (c_top + c_bot) / 2.0
                        col_pixels = patch[:, x]
                        diff_from_bg = np.linalg.norm(col_pixels - expected_bg, axis=-1)
                        is_text = diff_from_bg > 15
                        patch[is_text, x] = expected_bg
                    else:
                        for y in range(bh):
                            curr_val = patch[y, x]
                            d_top = np.linalg.norm(curr_val - c_top)
                            d_bot = np.linalg.norm(curr_val - c_bot)
                            if min(d_top, d_bot) > 22:
                                patch[y, x] = c_top if d_top < d_bot else c_bot
                out_win = cleaned_window.copy()
                out_win[by1:by2, bx1:bx2] = np.clip(patch, 0, 255).astype(np.uint8)
                return out_win

        # Min-axis stroke isolation and Navier-Stokes fluid continuation:
        hole_mask = self.extract_watermark_stroke_mask(cleaned_window, rel_box)
        return cv2.inpaint(cleaned_window, hole_mask, inpaintRadius=4, flags=cv2.INPAINT_NS)

    def refine_watermark_mask(
        self,
        window_frame: np.ndarray,
        rel_box: WatermarkBoundingBox,
    ) -> Tuple[np.ndarray, Optional[float], Optional[np.ndarray]]:
        """
        Refines coarse bounding box and extracts backdrop transmission ratio.
        """
        cleaned_window, backdrop_ratio, backdrop_mask = self.detect_and_restore_translucent_backdrop(
            window_frame, rel_box
        )
        h_win, w_win = window_frame.shape[:2]
        refined_mask = np.zeros((h_win, w_win), dtype=np.uint8)
        refined_mask[rel_box.y : rel_box.y2, rel_box.x : rel_box.x2] = 255
        return refined_mask, backdrop_ratio, backdrop_mask

    def inpaint_window_sequence(
        self,
        window_frames: List[np.ndarray],
        local_mask: np.ndarray,
        temporal_radius: int = 5,
    ) -> List[np.ndarray]:
        """
        Performs flow-guided temporal propagation across a chunk of windowed frames with zero-blur preservation.
        
        Args:
            window_frames: List of cropped frames (H, W, 3).
            local_mask: uint8 (H, W) where 255 indicates watermark pixels.
            temporal_radius: Number of neighbor frames to look forward/backward for real pixels.
            
        Returns:
            List of cleaned window frames with background pixels retained.
        """
        n = len(window_frames)
        cleaned_frames: List[np.ndarray] = []
        if n == 0:
            return cleaned_frames

        # Extract relative bounding box from local_mask
        rows = np.any(local_mask > 0, axis=1)
        cols = np.any(local_mask > 0, axis=0)
        if not np.any(rows) or not np.any(cols):
            return [f.copy() for f in window_frames]

        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]
        rel_box = WatermarkBoundingBox(
            x=int(x_min),
            y=int(y_min),
            width=int(x_max - x_min + 1),
            height=int(y_max - y_min + 1),
        )

        # Detect motion magnitude in the window
        is_moving = False
        if n >= 2:
            g0 = cv2.cvtColor(window_frames[0], cv2.COLOR_BGR2GRAY)
            g1 = cv2.cvtColor(window_frames[min(1, n - 1)], cv2.COLOR_BGR2GRAY)
            flow = cv2.calcOpticalFlowFarneback(g0, g1, None, 0.5, 3, 15, 3, 5, 1.2, 0)
            mag = np.linalg.norm(flow, axis=-1)
            is_moving = float(np.mean(mag)) >= 0.08

        # Detect translucent backdrop ratio
        _, backdrop_ratio, backdrop_mask = self.detect_and_restore_translucent_backdrop(
            window_frames[0], rel_box
        )

        # Pre-restore backdrop across all frames if present
        clean_windows: List[np.ndarray] = []
        bx1, by1 = rel_box.x, rel_box.y
        bx2, by2 = rel_box.x2, rel_box.y2

        for wf in window_frames:
            cw = wf.copy()
            if self.is_flat_black(cw):
                clean_windows.append(cw)
                continue
            if backdrop_ratio is not None and backdrop_mask is not None:
                patch = cw[by1:by2, bx1:bx2].astype(float)
                patch[backdrop_mask] = np.clip(patch[backdrop_mask] / backdrop_ratio, 0, 255)
                cw[by1:by2, bx1:bx2] = patch.astype(np.uint8)
            clean_windows.append(cw)

        if not is_moving:
            # Stationary / static scene: zero-blur domain-aware restoration
            for cw in clean_windows:
                if self.is_flat_black(cw):
                    cleaned_frames.append(cw.copy())
                else:
                    restored_win = self.restore_stationary_domain_features(cw, rel_box)
                    cleaned_frames.append(restored_win)
            return cleaned_frames

        # Moving scene: optical flow temporal propagation
        stroke_mask = self.extract_watermark_stroke_mask(clean_windows[0], rel_box)

        for i in range(n):
            curr_frame = clean_windows[i].copy()
            if self.is_flat_black(curr_frame):
                cleaned_frames.append(curr_frame)
                continue

            current_reconstructed = curr_frame.copy()
            active_mask = stroke_mask.copy()

            neighbor_offsets: list[int] = []
            for r in range(1, temporal_radius + 1):
                if i - r >= 0:
                    neighbor_offsets.append(-r)
                if i + r < n:
                    neighbor_offsets.append(r)

            for offset in neighbor_offsets:
                if np.count_nonzero(active_mask) == 0:
                    break
                donor_idx = i + offset
                donor_frame = clean_windows[donor_idx]
                if self.is_flat_black(donor_frame):
                    continue

                current_reconstructed, active_mask = self.warp_pixels_via_optical_flow(
                    current_reconstructed,
                    donor_frame,
                    active_mask,
                    stroke_mask,
                )

            # Inpaint remaining stroke pixels along contours using Navier-Stokes (zero cruciform blur!)
            if np.count_nonzero(active_mask) > 0:
                current_reconstructed = cv2.inpaint(
                    current_reconstructed,
                    active_mask,
                    inpaintRadius=3,
                    flags=cv2.INPAINT_NS,
                )

            cleaned_frames.append(current_reconstructed)

        return cleaned_frames

    def composite_patch(
        self,
        full_frame: np.ndarray,
        cleaned_patch: np.ndarray,
        window_box: WatermarkBoundingBox,
    ) -> np.ndarray:
        """
        Composites the cleaned window patch back onto the full frame with edge feathering.
        95%+ of the full frame outside the window remains 100% byte-identical.
        """
        h, w = cleaned_patch.shape[:2]
        x1, y1 = window_box.x, window_box.y
        x2, y2 = x1 + w, y1 + h

        result = full_frame.copy()

        if self.feather_px > 0 and w > self.feather_px * 2 and h > self.feather_px * 2:
            alpha = np.ones((h, w), dtype=np.float32)
            f = self.feather_px
            for p in range(f):
                weight = float(p + 1) / float(f + 1)
                alpha[p, :] = np.minimum(alpha[p, :], weight)
                alpha[h - 1 - p, :] = np.minimum(alpha[h - 1 - p, :], weight)
                alpha[:, p] = np.minimum(alpha[:, p], weight)
                alpha[:, w - 1 - p] = np.minimum(alpha[:, w - 1 - p], weight)
            alpha = alpha[:, :, np.newaxis]

            target_region = result[y1:y2, x1:x2].astype(np.float32)
            blended = (cleaned_patch.astype(np.float32) * alpha) + (target_region * (1.0 - alpha))
            result[y1:y2, x1:x2] = np.clip(blended, 0, 255).astype(np.uint8)
        else:
            result[y1:y2, x1:x2] = cleaned_patch

        return result
