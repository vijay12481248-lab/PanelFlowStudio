"""
Automated Manga Panel & Page Sanitizer for PanelFlow Studio.

Detects promotional watermarks, scanlation URLs, donation links, and blacklisted
keywords using hardware-accelerated local OCR, and automatically applies Gaussian
blur to the detected regions across all panel images.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageFilter

from engine.database.session import SessionLocal
from engine.database.models import ProjectRecord, PanelRecord, TextRegionRecord

logger = logging.getLogger("panelflow.imaging.sanitizer")

DEFAULT_BLUR_KEYWORDS: List[str] = [
    "manhuaplus",
    "manhua",
    "patreon",
    "paypal",
    "discord",
    "faster release",
    "read on",
    "read first",
    "support us",
    "donate",
    "scanlation",
    "bilibili",
    "asura",
    "reaper",
    "flamecomics",
    "void-scans",
]


def get_blur_keywords_for_project(project_id: str, db=None) -> List[str]:
    """Returns the effective blur keywords for a project (defaults + custom)."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            return list(DEFAULT_BLUR_KEYWORDS)
        settings = dict(proj.settings or {})
        custom_kw = settings.get("blur_keywords", [])
        # Combine unique keywords preserving order
        combined = list(DEFAULT_BLUR_KEYWORDS)
        for kw in custom_kw:
            cleaned = kw.strip().lower()
            if cleaned and cleaned not in combined:
                combined.append(cleaned)
        return combined
    finally:
        if close_db:
            db.close()


def save_blur_keywords_for_project(project_id: str, keywords: List[str], db=None) -> List[str]:
    """Updates custom blur keywords in the project settings."""
    from sqlalchemy.orm.attributes import flag_modified
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project '{project_id}' not found.")
        settings = dict(proj.settings or {})
        clean_list = [k.strip().lower() for k in keywords if k.strip()]
        settings["blur_keywords"] = clean_list
        proj.settings = settings
        flag_modified(proj, "settings")
        db.commit()
        return get_blur_keywords_for_project(project_id, db=db)
    finally:
        if close_db:
            db.close()


def blur_image_region(
    img: Image.Image,
    bbox: Tuple[int, int, int, int],
    blur_radius: int = 18,
    pad: int = 6,
) -> Image.Image:
    """
    Applies Gaussian blur to a specific [x, y, w, h] rectangular region on an image.
    Pads slightly to prevent edge bleed of watermark text.
    """
    x, y, w, h = bbox
    img_w, img_h = img.size

    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(img_w, x + w + pad)
    y2 = min(img_h, y + h + pad)

    if x2 <= x1 or y2 <= y1:
        return img

    crop_box = (x1, y1, x2, y2)
    region = img.crop(crop_box)
    blurred_region = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    
    # In case of very sharp dark text on light background, apply an extra BoxBlur pass
    blurred_region = blurred_region.filter(ImageFilter.BoxBlur(radius=max(3, blur_radius // 3)))
    
    img.paste(blurred_region, crop_box)
    return img


def scan_and_blur_panel_image(
    image_path: Path,
    keywords: List[str],
    ocr_engine: Any = None,
    blur_radius: int = 18,
) -> Dict[str, Any]:
    """
    Scans a single panel image using OCR, matches text against keywords,
    and directly blurs matching regions on the file.
    """
    if not image_path.exists():
        return {"blurred_count": 0, "regions": []}

    if ocr_engine is None:
        from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine
        ocr_engine = WindowsMediaOCREngine()

    try:
        ocr_res = ocr_engine.extract_text(image_path, image_path.stem)
    except Exception as exc:
        logger.warning(f"OCR scan failed for {image_path}: {exc}")
        return {"blurred_count": 0, "regions": []}

    lowered_kw = [k.lower() for k in keywords]
    matching_boxes = []

    for reg in ocr_res.regions:
        text_lower = reg.detected_text.lower()
        if any(kw in text_lower for kw in lowered_kw):
            matching_boxes.append({
                "bbox": reg.bbox,
                "text": reg.detected_text,
                "confidence": reg.confidence,
            })

    if not matching_boxes:
        return {"blurred_count": 0, "regions": []}

    # Open image, apply blur for each matching box, and save
    im = Image.open(image_path)
    im_format = im.format or "JPEG"
    for match in matching_boxes:
        bbox = match["bbox"]  # [x, y, w, h]
        im = blur_image_region(im, (bbox[0], bbox[1], bbox[2], bbox[3]), blur_radius=blur_radius)

    im.save(image_path, format=im_format, quality=95)
    logger.info(f"Auto-blurred {len(matching_boxes)} watermark regions in {image_path.name}")
    return {"blurred_count": len(matching_boxes), "regions": matching_boxes}


def auto_sanitize_project_panels(
    project_id: str,
    db: Any = None,
    custom_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Scans all panels in the project, blurs detected watermark regions in the images,
    and updates database TextRegionRecord statuses so promotional text is omitted
    from dialogue generation.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project '{project_id}' not found.")

        ws = Path(proj.workspace_path or "")
        panels_dir = ws / "panels"
        if not panels_dir.exists():
            return {"success": False, "message": "Panels directory does not exist."}

        keywords = custom_keywords or get_blur_keywords_for_project(project_id, db=db)
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id).order_by(PanelRecord.sequence.asc()).all()

        from engine.ocr.providers.windows_media_provider import WindowsMediaOCREngine
        ocr_engine = WindowsMediaOCREngine()

        total_blurred_regions = 0
        panels_affected = 0
        details = []

        for p in panels:
            img_file = panels_dir / p.crop_filename
            if not img_file.exists():
                continue

            # Check existing TextRegionRecords first
            t_regs = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == p.id).all()
            dirty = False
            for tr in t_regs:
                txt = (tr.corrected_text or tr.raw_text or "").lower()
                if any(kw in txt for kw in keywords):
                    tr.status = "BLURRED"
                    dirty = True

            # Perform scan & blur on image
            res = scan_and_blur_panel_image(img_file, keywords, ocr_engine=ocr_engine)
            if res["blurred_count"] > 0:
                total_blurred_regions += res["blurred_count"]
                panels_affected += 1
                details.append({
                    "panel_id": p.id,
                    "sequence": p.sequence,
                    "crop_filename": p.crop_filename,
                    "blurred_regions": res["regions"],
                })

            if dirty:
                db.commit()

        return {
            "success": True,
            "project_id": project_id,
            "keywords_used": keywords,
            "panels_affected": panels_affected,
            "total_blurred_regions": total_blurred_regions,
            "details": details,
        }
    finally:
        if close_db:
            db.close()


def matches_label(text: str, labels: List[str]) -> bool:
    """Literal, case-insensitive labels tolerate OCR whitespace and punctuation."""
    import re
    import unicodedata
    def normalize(value):
        return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())
    normalized = normalize(text)
    return any(needle and needle in normalized for needle in map(normalize, labels))
