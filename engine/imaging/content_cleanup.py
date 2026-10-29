"""Reusable, conservative OCR cleanup for newly detected episode panels."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from engine.config.settings import settings
from engine.database.models import PanelRecord, ProjectRecord, TextRegionRecord
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


def decide_cleanup(width, height, regions, labels):
    """Never exclude artwork merely because it contains a website label."""
    text_regions = [r for r in regions if r.detected_text.strip()]
    matches = [r for r in text_regions if matches_label(r.detected_text, labels)]
    if not matches:
        return {"action": "KEEP", "regions": [], "reason": "No label matched"}
    valid = [r for r in matches if r.confidence >= 0.85 and len(r.bbox) == 4
             and r.bbox[0] >= 0 and r.bbox[1] >= 0 and r.bbox[2] > 0 and r.bbox[3] > 0
             and r.bbox[0] + r.bbox[2] <= width and r.bbox[1] + r.bbox[3] <= height]
    # Only a thin banner with exclusively promotional OCR lines can be dropped.
    if (len(valid) == len(text_regions) and width / max(height, 1) >= 3
            and height <= 300):
        return {"action": "EXCLUDE", "regions": valid, "reason": "Thin banner with only matching promotional text"}
    combined = " ".join(r.detected_text for r in text_regions)
    poster_cues = ["head over to our website", "support us", "updates in real time", "discord.gg"]
    if sum(matches_label(combined, [cue]) for cue in poster_cues) >= 2:
        return {"action": "REVIEW", "regions": matches,
                "reason": "Possible promotional cover or outro with artwork; review whole panel"}
    localized = [r for r in valid if r.bbox[2] * r.bbox[3] <= width * height * 0.15]
    if len(localized) != len(matches):
        return {"action": "REVIEW", "regions": matches, "reason": "Uncertain OCR or text covers too much artwork"}
    return {"action": "BLUR", "regions": localized, "reason": "Localized label in a retained panel"}


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
        return (sum(matches_label(r.detected_text, labels) for r in lines) / max(len(lines), 1),
                sum(len(r.detected_text) for r in lines))
    return retry if score(retry) > score(result) else result


def cleanup_detected_panels(db, project_id, panel_ids, *, ocr_engine=None, cancelled=lambda: False):
    """Apply once per unchanged crop/rules; retain originals and an inspectable audit.

    Call only on newly detected panels. Existing edited/linked pages are protected
    by the detection service, so this does not silently rewrite an existing cut.
    """
    rules = load_rules()
    if not rules.enabled:
        return {"enabled": False, "items": []}
    project = db.get(ProjectRecord, project_id)
    if project is None:
        raise ValueError("Project not found")
    labels = list(dict.fromkeys(rules.labels + (project.settings or {}).get("blur_keywords", [])))
    if not panel_ids or not labels:
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
    fingerprint = hashlib.sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()
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
        result = read_panel_text(ocr_engine, path, panel, labels)
        decision = decide_cleanup(panel.width, panel.height, result.regions, labels)
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
