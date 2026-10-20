import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import uuid
import logging
import io
import json
from engine.security.paths import read_contained_bytes

from engine.imaging.panels.base import (
    BasePanelDetector,
    PanelBox,
    DetectionProfile,
    ReadingDirection,
    PanelType,
    PanelStatus,
)
from engine.imaging.panels.ordering import sort_panel_boxes

logger = logging.getLogger(__name__)

class ContourPanelDetector(BasePanelDetector):
    def __init__(
        self,
        min_area_ratio: float = 0.02,
        max_area_ratio: float = 0.90,
        row_threshold_ratio: float = 0.08,
        allow_insets: bool = True,
    ):
        self.min_area_ratio = min_area_ratio
        self.max_area_ratio = max_area_ratio
        self.row_threshold_ratio = row_threshold_ratio
        self.allow_insets = allow_insets

    def detect_panels(
        self,
        page_image_path: Path | str,
        reading_direction: str = "ltr",
        page_id: str = "",
        profile: str = "AUTO",
    ) -> list[PanelBox]:
        p_path = Path(page_image_path)
        encoded = np.frombuffer(read_contained_bytes(p_path.parent.parent, p_path), dtype=np.uint8)
        img = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"Failed to load image for panel detection: {page_image_path}")

        page_h, page_w = img.shape[:2]
        total_page_area = page_w * page_h

        # Determine effective profile & reading direction
        aspect_ratio = float(page_h) / float(page_w)
        effective_profile = profile.upper() if profile else "AUTO"
        if effective_profile == "AUTO":
            if aspect_ratio >= 2.5:
                effective_profile = DetectionProfile.WEBTOON.value
            elif reading_direction == "rtl":
                effective_profile = DetectionProfile.MANGA_PAGE.value
            else:
                effective_profile = DetectionProfile.WESTERN_COMIC.value

        effective_direction = reading_direction.lower()
        if effective_profile == DetectionProfile.WEBTOON.value:
            effective_direction = "vertical"
        elif effective_profile == DetectionProfile.MANGA_PAGE.value and reading_direction == "auto":
            effective_direction = "rtl"

        logger.info(
            f"Detecting panels for page {page_id} [{page_w}x{page_h}] "
            f"profile={effective_profile}, direction={effective_direction}"
        )

        # 1. Long webtoon tiled handling if needed
        if effective_profile == DetectionProfile.WEBTOON.value:
            candidates = self._detect_webtoon_tiled(img, page_w, page_h)
        else:
            candidates = self._detect_page_contours(img, page_w, page_h, effective_profile)

        # 2. Suppress overlapping twins while preserving insets
        filtered_boxes = self._suppress_overlapping(candidates, page_w, page_h)

        # 3. Fallback behavior if no panels detected (e.g. borderless splash page)
        if not filtered_boxes:
            logger.warning(f"No panels detected on page {page_id}; activating FULL_PAGE fallback.")
            return [
                PanelBox(
                    id=str(uuid.uuid4()),
                    page_id=page_id,
                    sequence=1,
                    page_sequence=1,
                    x=0,
                    y=0,
                    width=page_w,
                    height=page_h,
                    normalized_x=0.0,
                    normalized_y=0.0,
                    normalized_width=1.0,
                    normalized_height=1.0,
                    confidence=0.5,
                    panel_type=PanelType.FULL_PAGE.value,
                    status=PanelStatus.NEEDS_REVIEW.value,
                    detection_method="FALLBACK",
                    manually_modified=False,
                )
            ]

        # 4. Construct candidate PanelBox objects
        candidate_boxes: list[PanelBox] = []
        for x, y, w, h, conf, p_type in filtered_boxes:
            polygon_json = self._extract_polygon_from_box(img, int(x), int(y), int(w), int(h))
            candidate_boxes.append(
                PanelBox(
                    id=str(uuid.uuid4()),
                    page_id=page_id,
                    x=int(x),
                    y=int(y),
                    width=int(w),
                    height=int(h),
                    normalized_x=round(float(x) / float(page_w), 4),
                    normalized_y=round(float(y) / float(page_h), 4),
                    normalized_width=round(float(w) / float(page_w), 4),
                    normalized_height=round(float(h) / float(page_h), 4),
                    polygon_json=polygon_json,
                    confidence=round(float(conf), 2),
                    panel_type=p_type,
                    status=PanelStatus.DETECTED.value,
                    detection_method="AUTO",
                    manually_modified=False,
                )
            )

        # 5. Delegate narrative sequencing to canonical sort_panel_boxes from ordering.py
        results = sort_panel_boxes(
            candidate_boxes,
            reading_direction=effective_direction,
            page_height=page_h,
            row_threshold_ratio=self.row_threshold_ratio,
        )

        logger.info(f"Panel detection completed for page {page_id}: {len(results)} panels found.")
        return results

    def _detect_page_contours(
        self,
        img: np.ndarray,
        page_w: int,
        page_h: int,
        profile: str,
    ) -> list[tuple[int, int, int, int, float, str]]:
        total_page_area = page_w * page_h
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Morphological gradient & edge detection. Masking every bright region
        # destroys the synthetic white panel interiors and suppresses borders.
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 30, 110)

        # Bridge gaps between thin comic borders
        kernel_size = 5 if profile == DetectionProfile.SIMPLE_GRID.value else 3
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)

        # 1. First pass: find closed stroke borders
        contours, _ = cv2.findContours(
            closed,
            cv2.RETR_TREE,
            cv2.CHAIN_APPROX_SIMPLE,
        )

        candidates: list[tuple[int, int, int, int, float, str, str]] = []
        min_area = total_page_area * self.min_area_ratio
        max_area = total_page_area * self.max_area_ratio

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h

            # Filter out tiny noise and gigantic page envelopes
            if area < min_area or area > max_area:
                continue
            if w > 0.94 * page_w and h > 0.94 * page_h:
                continue
            if w < 40 or h < 40:
                continue

            aspect = float(w) / float(h)
            if aspect > 4.5 or aspect < (1.0 / 4.5):
                continue

            cnt_area = cv2.contourArea(cnt)
            solidity = cnt_area / float(area) if area > 0 else 0.0
            # Slanted panel frames occupy less of their axis-aligned rectangle.
            # Accept convex quadrilaterals only when they fill their rotated box;
            # this keeps diagonal cuts without admitting arbitrary character outlines.
            if solidity < 0.88:
                approx = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
                (_, _), (rw, rh), _ = cv2.minAreaRect(cnt)
                rotated_area = rw * rh
                if not (len(approx) == 4 and cv2.isContourConvex(approx)
                        and solidity >= 0.55 and rotated_area > 0
                        and cnt_area / rotated_area >= 0.80):
                    continue

            # Determine panel type
            area_ratio = area / float(total_page_area)
            if area_ratio >= 0.65:
                p_type = PanelType.SPLASH.value
            else:
                p_type = PanelType.STANDARD.value

            confidence = min(0.98, 0.75 + (area_ratio * 0.20))
            candidates.append((x, y, w, h, confidence, p_type))

        # 2. Second pass: If stroke borders didn't find panels, inspect white/dark gutters (borderless panels)
        if not candidates:
            border_pixels = np.concatenate([
                gray[0:15, :].flatten(),
                gray[-15:, :].flatten(),
                gray[:, 0:15].flatten(),
                gray[:, -15:].flatten(),
            ])
            bg_val = float(np.median(border_pixels))
            if bg_val < 100:
                _, thresh = cv2.threshold(blurred, int(min(220, bg_val + 35)), 255, cv2.THRESH_BINARY)
            else:
                _, thresh = cv2.threshold(blurred, int(max(40, bg_val - 35)), 255, cv2.THRESH_BINARY_INV)

            # Erode slightly to disconnect thin gutter bleed
            gutter_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            thresh_clean = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, gutter_kernel)

            gutter_contours, _ = cv2.findContours(
                thresh_clean,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE,
            )

            for cnt in gutter_contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                if area < min_area or area > max_area:
                    continue
                if w > 0.94 * page_w and h > 0.94 * page_h:
                    continue
                if w < 40 or h < 40:
                    continue
                aspect = float(w) / float(h)
                if aspect > 6.0 or aspect < (1.0 / 6.0):
                    continue
                area_ratio = area / float(total_page_area)
                confidence = min(0.95, 0.70 + (area_ratio * 0.20))
                candidates.append((x, y, w, h, confidence, PanelType.BORDERLESS.value))

        return candidates

    def _detect_webtoon_tiled(
        self,
        img: np.ndarray,
        page_w: int,
        page_h: int,
        tile_height: int = 3000,
        overlap: int = 1200,
    ) -> list[tuple[int, int, int, int, float, str]]:
        """
        Segments long webtoon scrolls via continuous horizontal whitespace projection,
        preventing arbitrary tile cuts from bifurcating illustrations.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # The gutter color can change along a strip (white, blue, or black).
        # Estimate it locally from both side margins rather than page ends.
        margin = max(2, round(page_w * 0.01))
        row_background = np.median(
            np.concatenate([gray[:, :margin], gray[:, -margin:]], axis=1),
            axis=1,
        )

        # Mean brightness mistakes white speech balloons for empty gutters.
        # Keep even thin outlines/text as content, and bridge short blank runs
        # so line spacing cannot split a single dialogue balloon into fragments.
        deviation = np.abs(gray.astype(np.float32) - row_background[:, None])
        is_content = (deviation > 12).mean(axis=1) >= 0.001
        min_gutter = max(25, round(page_w * 0.02)) | 1
        is_content = cv2.morphologyEx(
            is_content.astype(np.uint8).reshape(-1, 1),
            cv2.MORPH_CLOSE,
            np.ones((min_gutter, 1), dtype=np.uint8),
        ).reshape(-1).astype(bool)
        is_gutter = ~is_content

        # Identify contiguous non-gutter vertical spans
        in_panel = False
        start_y = 0
        spans: list[tuple[int, int]] = []

        for y, gut in enumerate(is_gutter):
            if not gut and not in_panel:
                in_panel = True
                start_y = y
            elif gut and in_panel:
                in_panel = False
                if (y - start_y) >= 80:  # Minimum panel height
                    spans.append((start_y, y))

        if in_panel and (page_h - start_y) >= 80:
            spans.append((start_y, page_h))

        candidates: list[tuple[int, int, int, int, float, str]] = []
        for y1, y2 in spans:
            content_cols = np.where((deviation[y1:y2] > 12).any(axis=0))[0]

            if len(content_cols) > 0:
                x1 = int(content_cols[0])
                x2 = int(content_cols[-1])
                w = max(50, x2 - x1 + 1)
                h = y2 - y1
                # Plausibility check
                if w >= 50 and h >= 50:
                    candidates.append((x1, y1, w, h, 0.95, PanelType.WEBTOON_SEGMENT.value))

        return candidates

    def _suppress_overlapping(
        self,
        boxes: list[tuple[int, int, int, int, float, str]],
        page_w: int,
        page_h: int,
        iou_thresh: float = 0.55,
    ) -> list[tuple[int, int, int, int, float, str]]:
        if not boxes:
            return []

        # Sort by area descending
        boxes = sorted(boxes, key=lambda b: b[2] * b[3], reverse=True)
        accepted: list[tuple[int, int, int, int, float, str]] = []

        for b in boxes:
            x1, y1, w1, h1, conf1, type1 = b
            area1 = w1 * h1
            keep = True
            is_inset = False

            for a in accepted:
                x2, y2, w2, h2, _, _ = a
                ix = max(x1, x2)
                iy = max(y1, y2)
                iw = max(0, min(x1 + w1, x2 + w2) - ix)
                ih = max(0, min(y1 + h1, y2 + h2) - iy)
                inter_area = iw * ih

                if inter_area > 0:
                    union_area = area1 + (w2 * h2) - inter_area
                    iou = inter_area / float(union_area)

                    # If essentially the same box (twin border duplicate)
                    if iou > iou_thresh:
                        keep = False
                        break

                    # Check for nested contour inside an accepted parent panel
                    overlap_ratio = inter_area / float(area1)
                    if overlap_ratio > 0.65:
                        if self.allow_insets and area1 < 0.40 * (w2 * h2) and overlap_ratio > 0.85:
                            is_inset = True
                        else:
                            keep = False
                            break

            if keep:
                if is_inset:
                    b = (x1, y1, w1, h1, conf1, PanelType.INSET.value)
                accepted.append(b)

        return accepted

    def _sort_reading_order(
        self,
        boxes: list[tuple[int, int, int, int, float, str]],
        page_h: int,
        reading_direction: str = "ltr",
    ) -> list[tuple[int, int, int, int, float, str]]:
        """Delegates tuple sorting to canonical sort_panel_boxes from ordering.py for backward compatibility."""
        if len(boxes) <= 1:
            return boxes
        temp_boxes = [
            PanelBox(
                id=str(i),
                page_id="",
                x=b[0],
                y=b[1],
                width=b[2],
                height=b[3],
                confidence=b[4],
                panel_type=b[5],
            )
            for i, b in enumerate(boxes)
        ]
        sorted_temp = sort_panel_boxes(
            temp_boxes,
            reading_direction=reading_direction,
            page_height=page_h,
            row_threshold_ratio=self.row_threshold_ratio,
        )
        return [(p.x, p.y, p.width, p.height, p.confidence, p.panel_type) for p in sorted_temp]

    def extract_crop(
        self,
        source_image_path: Path | str,
        panel_box: PanelBox,
        target_path: Path | str,
    ) -> Path:
        s_path = Path(source_image_path)
        t_path = Path(target_path)
        t_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(io.BytesIO(read_contained_bytes(s_path.parent.parent, s_path))) as img:
            img_w, img_h = img.size
            # Clamp coordinates safely
            x1 = max(0, min(panel_box.x, img_w - 1))
            y1 = max(0, min(panel_box.y, img_h - 1))
            x2 = max(x1 + 1, min(panel_box.x + panel_box.width, img_w))
            y2 = max(y1 + 1, min(panel_box.y + panel_box.height, img_h))

            crop = img.crop((x1, y1, x2, y2))
            # If polygon is available, mask crop to exact panel shape
            if panel_box.polygon_json:
                try:
                    import json
                    import numpy as np
                    import cv2
                    pts = json.loads(panel_box.polygon_json)
                    # Translate points from absolute image coords to crop-local coords
                    pts_local = [(int(px - x1), int(py - y1)) for px, py in pts]
                    mask = Image.new("L", crop.size, 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.polygon(pts_local, fill=255)
                    crop = Image.composite(
                        crop,
                        Image.new("RGB", crop.size, (255,255,255)),
                        mask
                    )
                except Exception:
                    # Fallback to rectangular crop on any error
                    pass
            if crop.mode not in ("RGB", "L"):
                crop = crop.convert("RGB")
            from engine.security.paths import write_contained_image
            write_contained_image(t_path.parent.parent, t_path, crop, "JPEG", quality=95, optimize=True)

        data = read_contained_bytes(t_path.parent.parent, t_path)

        import hashlib
        return {
            "crop_path": str(t_path.resolve()),
            "width": x2 - x1,
            "height": y2 - y1,
            "byte_size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def generate_debug_overlay(
        self,
        page_image_path: Path | str,
        panels: list[PanelBox],
        output_path: Path | str,
    ) -> Path:
        """Generates a visual debug overlay with bounding boxes and sequence badges."""
        p_path = Path(page_image_path)
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with Image.open(io.BytesIO(read_contained_bytes(p_path.parent.parent, p_path))) as img:
            overlay = img.convert("RGBA")
            draw = ImageDraw.Draw(overlay)

            for p in panels:
                box_color = (79, 70, 229, 255)  # Indigo
                fill_color = (99, 102, 241, 40)
                # Bounding box
                draw.rectangle(
                    [p.x, p.y, p.x + p.width, p.y + p.height],
                    outline=box_color,
                    width=4,
                    fill=fill_color,
                )
                # Sequence badge
                badge_w, badge_h = 90, 28
                badge_y = max(0, p.y - badge_h)
                draw.rectangle(
                    [p.x, badge_y, p.x + badge_w, badge_y + badge_h],
                    fill=box_color,
                )
                draw.text(
                    (p.x + 8, badge_y + 4),
                    f"#{p.sequence} ({int(p.confidence*100)}%)",
                    fill=(255, 255, 255, 255),
                )

            final_img = overlay.convert("RGB")
            from engine.security.paths import write_contained_image
            write_contained_image(out_path.parent.parent, out_path, final_img, "JPEG", quality=90)

        return out_path

    def _extract_polygon_from_box(self, img: np.ndarray, x: int, y: int, w: int, h: int) -> str | None:
        """Extract polygon via Hough lines and approxPolyDP for slanted panels."""
        try:
            roi = img[y:y+h, x:x+w]
            if roi.size == 0:
                return None
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5,5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, minLineLength=max(20, w//4), maxLineGap=20)
            if lines is None or len(lines) < 4:
                # Fallback to contour approx on ROI
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if not contours:
                    return None
                cnt = max(contours, key=cv2.contourArea)
                peri = cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, 0.02*peri, True)
                if (4 <= len(approx) <= 8 and cv2.isContourConvex(approx)
                        and cv2.contourArea(approx) >= 0.70 * w * h):
                    pts = approx.reshape(-1, 2)
                    # Normalize to absolute image coords
                    pts_abs = [[int(x + pt[0]), int(y + pt[1])] for pt in pts]
                    return json.dumps(pts_abs)
                return None
            # Build edge map from lines
            mask = np.zeros_like(gray)
            for line in lines:
                x1, y1, x2, y2 = line[0]
                cv2.line(mask, (x1, y1), (x2, y2), 255, 2)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None
            cnt = max(contours, key=cv2.contourArea)
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02*peri, True)
            if (not 4 <= len(approx) <= 8 or not cv2.isContourConvex(approx)
                    or cv2.contourArea(approx) < 0.70 * w * h):
                return None
            pts = approx.reshape(-1, 2)
            pts_abs = [[int(x + pt[0]), int(y + pt[1])] for pt in pts]
            return json.dumps(pts_abs)
        except Exception:
            return None

# Export both names for backwards compatibility and specification alignment
ClassicalPanelDetector = ContourPanelDetector
panel_detector = ContourPanelDetector()
