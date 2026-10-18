"""
Classical Text Region Detector.
Extracts speech balloons, narration boxes, captions, and SFX regions using
OpenCV connected components, morphology, and geometric heuristics.
Includes guaranteed fallback to panel bounds with NEEDS_REVIEW status.
"""

from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import uuid

from engine.imaging.text_regions.base import (
    TextRegionBox,
    TextRegionType,
    TextRegionStatus,
    TextCorrectionStatus,
)


class ClassicalTextRegionDetector:
    def __init__(
        self,
        min_region_area_ratio: float = 0.01,
        max_region_area_ratio: float = 0.60,
        whiteness_threshold: int = 215,
        merge_distance_px: int = 15,
    ):
        self.min_region_area_ratio = min_region_area_ratio
        self.max_region_area_ratio = max_region_area_ratio
        self.whiteness_threshold = whiteness_threshold
        self.merge_distance_px = merge_distance_px

    def detect(
        self,
        panel_image: np.ndarray | Path | str,
        panel_id: str = "",
        page_id: str = "",
        project_id: str = "",
        panel_x: int = 0,
        panel_y: int = 0,
        page_w: int = 1200,
        page_h: int = 1800,
        reading_direction: str = "ltr",
    ) -> list[TextRegionBox]:
        """
        Detects text regions within a panel.
        Returns ordered list of TextRegionBox objects.
        """
        if isinstance(panel_image, (Path, str)):
            img = cv2.imread(str(panel_image))
            if img is None:
                raise ValueError(f"Failed to load image for text region detection: {panel_image}")
        else:
            img = panel_image

        panel_h, panel_w = img.shape[:2]
        total_panel_area = panel_w * panel_h

        if total_panel_area <= 0:
            return []

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        min_area = total_panel_area * self.min_region_area_ratio
        max_area = total_panel_area * self.max_region_area_ratio

        candidates: list[tuple[int, int, int, int, str, float]] = []

        # -------------------------------------------------------------
        # 1. Speech Balloon & Narration Box Detection (Whiteness & Contours)
        # -------------------------------------------------------------
        _, white_mask = cv2.threshold(blurred, self.whiteness_threshold, 255, cv2.THRESH_BINARY)
        balloon_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        closed_white = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, balloon_kernel)

        contours, _ = cv2.findContours(closed_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if area < min_area or area > max_area:
                continue
            if w > 0.95 * panel_w and h > 0.95 * panel_h:
                continue
            if w < 30 or h < 25:
                continue

            cnt_area = cv2.contourArea(cnt)
            solidity = cnt_area / float(area) if area > 0 else 0.0

            # Inspect internal text presence (gradient / dark strokes inside the white bubble)
            sub_gray = gray[y:y+h, x:x+w]
            has_text = self._has_text_content(sub_gray)
            if not has_text:
                continue

            # Classify based on geometry
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)

            if len(approx) == 4 and solidity > 0.88:
                # Rectangular narration or caption box
                if y < panel_h * 0.25 or (y + h) > panel_h * 0.75:
                    reg_type = TextRegionType.NARRATION.value
                else:
                    reg_type = TextRegionType.CAPTION.value
                confidence = 0.92
            else:
                # Elliptical / rounded speech balloon
                reg_type = TextRegionType.SPEECH.value
                confidence = 0.90

            candidates.append((x, y, w, h, reg_type, confidence))

        # -------------------------------------------------------------
        # 2. Text Stroke Analysis for Non-balloon text (SFX & Free text)
        # -------------------------------------------------------------
        # Canny edge on darker strokes
        edges = cv2.Canny(blurred, 60, 180)
        # Dilate horizontally and vertically to merge individual letters into word/line blocks
        merge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (self.merge_distance_px, 7))
        merged_strokes = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, merge_kernel)

        stroke_contours, _ = cv2.findContours(merged_strokes, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in stroke_contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if area < min_area or area > max_area:
                continue
            if w > 0.92 * panel_w and h > 0.92 * panel_h:
                continue
            if w < 25 or h < 18:
                continue

            # Check if this stroke block is already inside an accepted balloon/narration candidate
            already_covered = False
            for bx, by, bw, bh, _, _ in candidates:
                if x >= bx - 5 and y >= by - 5 and (x + w) <= (bx + bw + 5) and (y + h) <= (by + bh + 5):
                    already_covered = True
                    break

            if not already_covered:
                # Text strokes must have compact dimensions and high internal text variance
                if w < 0.70 * panel_w and h < 0.50 * panel_h:
                    sub_roi = gray[y:y+h, x:x+w]
                    if self._has_text_content(sub_roi):
                        reg_type = TextRegionType.SFX.value if (w > h * 1.5 or h > w * 1.5) else TextRegionType.SPEECH.value
                        candidates.append((x, y, w, h, reg_type, 0.80))

        # -------------------------------------------------------------
        # 3. Suppress and Merge Overlapping / Fragmented Regions
        # -------------------------------------------------------------
        merged_boxes = self._merge_adjacent_regions(candidates)

        # -------------------------------------------------------------
        # 4. Fallback Path: Zero regions found -> Full Panel fallback
        # -------------------------------------------------------------
        if not merged_boxes:
            fallback_box = TextRegionBox(
                id=str(uuid.uuid4()),
                project_id=project_id,
                page_id=page_id,
                panel_id=panel_id,
                x=0,
                y=0,
                width=panel_w,
                height=panel_h,
                normalized_x=0.0,
                normalized_y=0.0,
                normalized_width=1.0,
                normalized_height=1.0,
                page_x=panel_x,
                page_y=panel_y,
                page_width=panel_w,
                page_height=panel_h,
                region_type=TextRegionType.UNKNOWN.value,
                confidence=0.50,
                sequence_in_panel=1,
                status=TextRegionStatus.NEEDS_REVIEW.value,
                detection_method="FALLBACK_PANEL",
            )
            return [fallback_box]

        # -------------------------------------------------------------
        # 5. Reading Order in Panel (Top-to-Bottom, LTR or RTL)
        # -------------------------------------------------------------
        is_rtl = reading_direction.lower() in ("rtl",)
        sorted_boxes = self._sort_in_panel_reading_order(merged_boxes, panel_h, is_rtl=is_rtl)

        # -------------------------------------------------------------
        # 6. Construct Canonical TextRegionBox Objects
        # -------------------------------------------------------------
        results: list[TextRegionBox] = []
        for seq, (rx, ry, rw, rh, r_type, conf) in enumerate(sorted_boxes, start=1):
            results.append(
                TextRegionBox(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    page_id=page_id,
                    panel_id=panel_id,
                    x=int(rx),
                    y=int(ry),
                    width=int(rw),
                    height=int(rh),
                    normalized_x=round(float(rx) / float(panel_w), 4),
                    normalized_y=round(float(ry) / float(panel_h), 4),
                    normalized_width=round(float(rw) / float(panel_w), 4),
                    normalized_height=round(float(rh) / float(panel_h), 4),
                    page_x=int(panel_x + rx),
                    page_y=int(panel_y + ry),
                    page_width=int(rw),
                    page_height=int(rh),
                    region_type=r_type,
                    confidence=round(float(conf), 2),
                    sequence_in_panel=seq,
                    status=TextRegionStatus.DETECTED.value,
                    detection_method="AUTO",
                )
            )

        return results

    def _has_text_content(self, gray_roi: np.ndarray) -> bool:
        """Verifies presence of text-like high-contrast dark strokes inside region."""
        if gray_roi.size == 0:
            return False
        # A detected white wall/caption-shaped surface can have a dark outline
        # without any text inside. Do not count that perimeter as lettering.
        height, width = gray_roi.shape[:2]
        padding = max(2, min(8, round(min(height, width) * 0.04)))
        if height > 2 * padding and width > 2 * padding:
            gray_roi = gray_roi[padding:-padding, padding:-padding]
        # Calculate contrast standard deviation and dark pixel fraction
        std = np.std(gray_roi)
        dark_pixels = np.count_nonzero(gray_roi < 160)
        total_pixels = gray_roi.size
        dark_ratio = dark_pixels / float(total_pixels)
        return bool(std > 12 and 0.02 <= dark_ratio <= 0.65)

    def _merge_adjacent_regions(
        self,
        boxes: list[tuple[int, int, int, int, str, float]],
    ) -> list[tuple[int, int, int, int, str, float]]:
        if not boxes:
            return []

        # Sort by area descending
        sorted_boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)
        accepted: list[tuple[int, int, int, int, str, float]] = []

        for b in sorted_boxes:
            x1, y1, w1, h1, type1, conf1 = b
            merged = False

            for idx, a in enumerate(accepted):
                x2, y2, w2, h2, type2, conf2 = a
                # Compute intersection
                ix = max(x1, x2)
                iy = max(y1, y2)
                iw = max(0, min(x1 + w1, x2 + w2) - ix)
                ih = max(0, min(y1 + h1, y2 + h2) - iy)
                inter_area = iw * ih

                if inter_area > 0:
                    union_area = (w1 * h1) + (w2 * h2) - inter_area
                    iou = inter_area / float(union_area) if union_area > 0 else 0.0
                    overlap1 = inter_area / float(w1 * h1)
                    overlap2 = inter_area / float(w2 * h2)

                    # If one is contained inside the other or heavily overlapping
                    if iou > 0.40 or overlap1 > 0.70 or overlap2 > 0.70:
                        # Merge into union bounding box
                        nx = min(x1, x2)
                        ny = min(y1, y2)
                        nw = max(x1 + w1, x2 + w2) - nx
                        nh = max(y1 + h1, y2 + h2) - ny
                        best_type = type2 if type2 != TextRegionType.UNKNOWN.value else type1
                        best_conf = max(conf1, conf2)
                        accepted[idx] = (nx, ny, nw, nh, best_type, best_conf)
                        merged = True
                        break

            if not merged:
                accepted.append(b)

        return accepted

    def _sort_in_panel_reading_order(
        self,
        boxes: list[tuple[int, int, int, int, str, float]],
        panel_h: int,
        is_rtl: bool = False,
    ) -> list[tuple[int, int, int, int, str, float]]:
        """Sorts text regions top-to-bottom, then left-to-right (or right-to-left for manga)."""
        if len(boxes) <= 1:
            return boxes

        # Group by vertical rows using 15% panel height tolerance
        row_tol = max(20, int(panel_h * 0.12))
        boxes_by_y = sorted(boxes, key=lambda b: b[1])

        rows: list[list[tuple[int, int, int, int, str, float]]] = []
        curr_row = [boxes_by_y[0]]

        for b in boxes_by_y[1:]:
            curr_y = b[1]
            row_avg_y = sum(item[1] for item in curr_row) / len(curr_row)
            if abs(curr_y - row_avg_y) <= row_tol:
                curr_row.append(b)
            else:
                rows.append(curr_row)
                curr_row = [b]
        if curr_row:
            rows.append(curr_row)

        sorted_result: list[tuple[int, int, int, int, str, float]] = []
        for r in rows:
            sorted_row = sorted(r, key=lambda b: b[0], reverse=is_rtl)
            sorted_result.extend(sorted_row)

        return sorted_result
