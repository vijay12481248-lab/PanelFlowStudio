"""Reusable, conservative OCR cleanup for newly detected episode panels."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from engine.config.settings import settings
from engine.database.models import PanelRecord, ProjectRecord, TextRegionRecord
from engine.imaging.redaction import restore_image_backup
from engine.imaging.sanitizer import matches_label
from engine.security.paths import project_path


class CleanupRules(BaseModel):
    enabled: bool = True
    labels: list[str] = Field(default_factory=lambda: [
        "manhuaplus.com", "manhuuplus.com", "read first at", "faster release",
        "if you enjoyed", "head over to our website", "support us", "patreon.com", "paypal.me", "discord.gg",
    ], max_length=200)

    @field_validator("labels")
    @classmethod
    def clean_labels(cls, labels):
        result = []
        for label in labels:
            label = label.strip().casefold()
            if not label:
                continue
            if len(label) > 200 or not any(c.isalnum() for c in label):
                raise ValueError("Labels must contain letters or digits and be at most 200 characters")
            if label not in result:
                result.append(label)
        return result


def load_rules() -> CleanupRules:
    path = settings.app_data_dir / "content-cleanup.json"
    if not path.exists():
        return CleanupRules()
    return CleanupRules.model_validate_json(path.read_text(encoding="utf-8"))


def save_rules(rules: CleanupRules) -> None:
    directory = settings.app_data_dir
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f"content-cleanup-{uuid4()}.tmp"
    try:
        temporary.write_text(rules.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(directory / "content-cleanup.json")
    finally:
        temporary.unlink(missing_ok=True)


def require_cleanup_review(db, project_id):
    pending = db.query(TextRegionRecord).join(PanelRecord, TextRegionRecord.panel_id == PanelRecord.id).filter(
        TextRegionRecord.project_id == project_id, TextRegionRecord.detection_method == "AUTO_CLEANUP",
        TextRegionRecord.status == "NEEDS_REVIEW", PanelRecord.status != "IGNORED").count()
    if pending:
        raise ValueError(f"Review {pending} uncertain promotional text matches in Panel Review before continuing. Blur, exclude, or verify the text in OCR Review.")


# Bumping this re-checks every existing panel once under the new rules (it is part of the fingerprint).
RULES_VERSION = "2026-11-01.promo-banner"

# Any scanlator, not only listed ones: OCR often splits a domain ("MANHUA PLUS . COM").
_DOMAIN = re.compile(r"\b[a-z0-9][a-z0-9-]{2,}\s?\.\s?(?:com|net|org|io|gg|me|co|xyz|site|cc|to|tv|club|online)\b")
_PROMO_PHRASES = ["read first at", "read first on", "faster release", "please read on", "if you enjoyed",
                  "join our discord", "discord.gg", "patreon", "paypal", "ko-fi", "support us",
                  "head over to our website", "higher quality releases", "updates in real time", "read the chapter on", "scanlation team"]
# Credit lines and outro calls that only appear on cover / credits / outro pages.
_POSTER_CUES = ["head over to our website", "support us", "updates in real time", "discord.gg",
                "join our discord", "patreon", "paypal", "want to read a new chapter", "higher quality releases"]
_CREDIT = re.compile(r"^\s*(?:tl|pr|ts|rp|qc|cl|rd|c/rd|raw|raws|translator|proofreader|typesetter|cleaner)\s*[:：]")
_HEADER = ["read first at", "read first on", "please read on"]


def is_promo_text(text, labels):
    lowered = text.casefold()
    return (matches_label(text, labels) or bool(_DOMAIN.search(lowered))
            or any(matches_label(text, [p]) for p in _PROMO_PHRASES))


def _clamp(bbox, width, height):
    x, y, w, h = bbox
    x0, y0 = max(0, min(int(x), width - 1)), max(0, min(int(y), height - 1))
    return [x0, y0, max(1, min(int(x + w), width) - x0), max(1, min(int(y + h), height) - y0)]


def _join_line(region, others):
    """OCR can split one logo into pieces ("MANHUA" + "PLUS.COM"); take adjacent pieces on the same line."""
    x, y, w, h = region.bbox
    x0, x1 = x, x + w
    grown = True
    while grown:
        grown = False
        for o in others:
            ox, oy, ow, oh = o.bbox
            same_line = min(y + h, oy + oh) - max(y, oy) >= 0.5 * min(h, oh)
            adjacent = ox <= x1 + 1.5 * h and ox + ow >= x0 - 1.5 * h
            if o is not region and same_line and adjacent and (ox < x0 or ox + ow > x1):
                x0, x1, grown = min(x0, ox), max(x1, ox + ow), True
    return region.model_copy(update={"bbox": [x0, y, x1 - x0, h]})


def _stamp_box(region, others, width, height):
    """A two-line stamp ("READ FIRST AT" over the site logo) is blurred whole, even when OCR read one line.

    The header line is about two-thirds the width of the logo line, and the logo sits directly below it.
    OCR often misreads a cropped logo ("PLUS.COM") with a box that does not reach the real glyphs.
    """
    x, y, w, h = region.bbox
    if any(matches_label(region.detected_text, [p]) for p in _HEADER):
        cx = x + w / 2
        return _clamp([cx - 0.8 * w, y - 0.2 * h, 1.6 * w, 2.9 * h], width, height)
    if _DOMAIN.search(region.detected_text.casefold()):
        above = [o for o in others if any(matches_label(o.detected_text, [p]) for p in _HEADER)
                 and 0 < y - o.bbox[1] <= 3 * o.bbox[3]]
        if above:
            return region.bbox  # the header's box already covers this logo line
        cx = x + w / 2
        return _clamp([cx - 0.6 * w, y - 1.8 * h, 1.2 * w, 3.0 * h], width, height)
    return region.bbox


def _span_area(regions):
    """Area of the box around all the regions: a corner watermark is small, a banner's text spans the panel."""
    x0, y0 = min(r.bbox[0] for r in regions), min(r.bbox[1] for r in regions)
    x1, y1 = max(r.bbox[0] + r.bbox[2] for r in regions), max(r.bbox[1] + r.bbox[3] for r in regions)
    return (x1 - x0) * (y1 - y0)


def decide_cleanup(width, height, regions, labels):
    """Blur promotional text inside story panels; drop panels that are only promotion."""
    text_regions = [r for r in regions if r.detected_text.strip() and len(r.bbox) == 4
                    and r.bbox[2] > 0 and r.bbox[3] > 0]
    matches = [r for r in text_regions if is_promo_text(r.detected_text, labels)]
    combined = " ".join(r.detected_text for r in text_regions)
    cues = sum(matches_label(combined, [cue]) for cue in _POSTER_CUES)
    credits = sum(bool(_CREDIT.search(r.detected_text.casefold())) for r in text_regions)
    if cues + min(credits, 2) >= 2:
        return {"action": "EXCLUDE", "regions": matches, "reason": "Cover, credits or outro page"}
    if not matches:
        return {"action": "KEEP", "regions": [], "reason": "No promotional text"}
    if len(matches) == len(text_regions) and width / max(height, 1) >= 3 and height <= 300:
        return {"action": "EXCLUDE", "regions": matches, "reason": "Thin banner with only promotional text"}
    # Unreadable OCR, or one "line" spanning most of the panel, is not a box we can trust to blur.
    trusted = [r for r in matches if r.confidence >= 0.5 and r.bbox[2] * r.bbox[3] <= width * height * 0.5]
    if not trusted:
        return {"action": "KEEP", "regions": [], "reason": "Promotional text matched but its position is unreliable"}
    if len(trusted) == len(text_regions) and _span_area(trusted) >= 0.25 * width * height:
        return {"action": "EXCLUDE", "regions": trusted, "reason": "Full-size promotional banner"}
    joined = [_join_line(r, text_regions) for r in trusted]
    boxed = [r.model_copy(update={"bbox": _stamp_box(r, text_regions, width, height)}) for r in joined]
    for r in boxed:
        r.bbox = _clamp(r.bbox, width, height)
    return {"action": "BLUR", "regions": boxed, "reason": "Promotional text in a story panel"}


def read_panel_text(ocr_engine, path, panel, labels):
    """Retry small banners at higher contrast; map OCR boxes to original pixels."""
    result = ocr_engine.extract_text(path, panel.id)
    if panel.width / max(panel.height, 1) < 3 or panel.height > 300:
        return result
    if decide_cleanup(panel.width, panel.height, result.regions, labels)["action"] == "EXCLUDE":
        return result
    from PIL import Image
    from tempfile import TemporaryDirectory
    # Keep below the native OCR maximum dimension. No original image is changed.
    scale = min(2.0, 2500 / max(panel.width, panel.height))
    with TemporaryDirectory(prefix="panelflow-ocr-") as temp:
        retry_path = Path(temp) / "banner.png"
        with Image.open(path) as image:
            image.resize((round(panel.width * scale), round(panel.height * scale))).convert("L").point(
                lambda value: 0 if value < 180 else 255).save(retry_path)
        retry = ocr_engine.extract_text(retry_path, panel.id)
    for region in retry.regions:
        x, y, w, h = region.bbox
        x1, y1 = max(0, round(x/scale)), max(0, round(y/scale))
        region.bbox = [x1, y1, min(panel.width-x1, round(w/scale)), min(panel.height-y1, round(h/scale))]
    def score(candidate):
        lines = [r for r in candidate.regions if r.detected_text.strip()]
        return (sum(is_promo_text(r.detected_text, labels) for r in lines) / max(len(lines), 1),
                sum(len(r.detected_text) for r in lines))
    return retry if score(retry) > score(result) else result


def clean_all_panels(db, project_id, **kwargs):
    """Bring every retained panel up to the current rules; unchanged panels are skipped by fingerprint."""
    ids = [row.id for row in db.query(PanelRecord.id).filter(PanelRecord.project_id == project_id,
                                                              PanelRecord.status != "IGNORED")]
    return cleanup_detected_panels(db, project_id, ids, **kwargs)


def cleanup_detected_panels(db, project_id, panel_ids, *, ocr_engine=None, cancelled=lambda: False):
    """Apply once per unchanged crop/rules; retain originals and an inspectable audit.

    Only the panel crop is changed (its original is kept under .originals); panel boxes are never re-cut.
    """
    rules = load_rules()
    if not rules.enabled:
        return {"enabled": False, "items": []}
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise ValueError("Project not found")
    labels = list(dict.fromkeys(rules.labels + (project.settings or {}).get("blur_keywords", [])))
    if not panel_ids:
        return {"enabled": True, "items": []}
    if ocr_engine is None:
        from engine.ocr.providers.registry import ocr_registry
        ocr_engine = ocr_registry.get_default_engine()
    if "mock" in ocr_engine.engine_id.lower() or not ocr_engine.is_available():
        raise RuntimeError("Automatic promotional cleanup requires real OCR. Configure OCR or disable automatic cleanup in Panel Review.")
    panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id,
                                        PanelRecord.id.in_(panel_ids)).order_by(PanelRecord.sequence).all()
    previous = (project.settings or {}).get("content_cleanup_report", {})
    live_ids = {row.id for row in db.query(PanelRecord.id).filter(PanelRecord.project_id == project_id)}
    records = {key: value for key, value in previous.get("panels", {}).items() if key in live_ids}
    fingerprint = hashlib.sha256(json.dumps([RULES_VERSION, labels], sort_keys=True).encode()).hexdigest()
    detected = (project.settings or {}).get("detected_promos") or {}
    items = []
    from engine.imaging.redaction import blur_image_boxes
    for panel in panels:
        if cancelled():
            raise RuntimeError("Automatic promotional cleanup cancelled")
        if panel.status == "IGNORED":
            continue
        path = project_path(project.workspace_path, "panels", panel.crop_filename)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        old = records.get(panel.id, {})
        if old.get("output_sha256") == digest and old.get("rules_hash") == fingerprint:
            items.append(old)
            continue
        if old.get("action") == "BLUR" and old.get("output_sha256") == digest:
            restore_image_backup(path, delete_backup=False)  # re-judge an old-rules blur from the untouched crop
        result = read_panel_text(ocr_engine, path, panel, labels)
        decision = decide_cleanup(panel.width, panel.height, result.regions, labels)
        # Watermarks the panel detector found visually (e.g. translucent 快看漫画 marks OCR cannot read).
        seen = [w for w in detected.get(panel.id, []) if decision["action"] != "EXCLUDE"]
        if seen and sum(w[2] * w[3] for w in seen) >= 0.4 * panel.width * panel.height:
            decision = {"action": "EXCLUDE", "regions": decision["regions"], "reason": "Detected promo fills the panel"}
        elif seen:
            from engine.ocr.providers.base import OCRRegion
            decision = {"action": "BLUR", "reason": decision["reason"] if decision["action"] == "BLUR"
                        else "Watermark detected in a story panel",
                        "regions": decision["regions"] + [OCRRegion(id="detected", detected_text="[detected watermark]",
                                                                    confidence=1.0, bbox=w) for w in seen]}
        item = {"panel_id": panel.id, "sequence": panel.sequence, "action": decision["action"],
                "reason": decision["reason"], "ocr_engine": ocr_engine.engine_id,
                "matches": [{"text": r.detected_text, "bbox": r.bbox, "confidence": r.confidence}
                            for r in decision["regions"]], "rules_hash": fingerprint}
        if decision["action"] == "EXCLUDE":
            panel.status = "IGNORED"
        elif decision["action"] == "BLUR":
            boxes = []
            for region in decision["regions"]:
                x, y, w, h = region.bbox
                # Padding removes glyph edges; the redaction utility retains a restorable original.
                x1, y1 = max(0, x - 4), max(0, y - 4)
                boxes.append((x1, y1, min(panel.width, x+w+4)-x1,
                              min(panel.height, y+h+4)-y1))
            blur_image_boxes(path, boxes, feather=0)
        for region in decision["regions"]:
            rid = hashlib.sha256(f"cleanup:{panel.id}:{region.bbox}:{region.detected_text}".encode()).hexdigest()[:36]
            tr = db.get(TextRegionRecord, rid)
            if tr is None:
                x, y, w, h = region.bbox
                tr = TextRegionRecord(id=rid, project_id=project_id, page_id=panel.page_id,
                                      panel_id=panel.id, x=x, y=y, width=w, height=h,
                                      raw_text=region.detected_text, raw_confidence=region.confidence,
                                      ocr_engine=ocr_engine.engine_id, sequence_global=panel.sequence, detection_method="AUTO_CLEANUP")
                db.add(tr)
            tr.status = {"EXCLUDE": "IGNORED", "BLUR": "BLURRED", "REVIEW": "NEEDS_REVIEW"}[decision["action"]]
            if decision["action"] == "BLUR":
                tr.region_type = "REDACTED"
                tr.corrected_text = "[BLURRED / REDACTED]"
        item["output_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest() if decision["action"] == "BLUR" else digest
        records[panel.id] = item
        items.append(item)
        project.settings = {**(project.settings or {}), "content_cleanup_report": {"panels": records}}
        db.commit()
    return {"enabled": True, "items": items}
