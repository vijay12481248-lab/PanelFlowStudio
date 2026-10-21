"""History strategies for reversible OCR and text region mutations."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import uuid

from sqlalchemy.orm.attributes import flag_modified

from engine.acquisition.models import PipelineStage
from engine.database.models import OCRRecord, PageRecord, PanelRecord, TextRegionRecord, utc_now
from engine.history.assets import RetainedAssetStore
from engine.history.contracts import HistoryFault
from engine.projects.service import project_service
from engine.security.paths import project_path


def _row_data(row):
    """JSON-safe persistent columns; audit timestamps are regenerated on restore."""
    data = {}
    for column in row.__table__.columns:
        if column.name in {"created_at", "updated_at"}:
            continue
        val = getattr(row, column.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        data[column.name] = val
    return data


def _restore_text_region(data: dict) -> TextRegionRecord:
    item = dict(data)
    for dt_col in ("corrected_at", "ocr_extracted_at"):
        if dt_col in item and isinstance(item[dt_col], str):
            item[dt_col] = datetime.fromisoformat(item[dt_col])
    return TextRegionRecord(**item, created_at=utc_now(), updated_at=utc_now())


class TextRegionCreateStrategy:
    """Create a manual text region with deterministic UUID."""
    _fields = ("x", "y", "width", "height")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        if not isinstance(input.get("panel_id"), str):
            raise HistoryFault("VALIDATION", "Panel ID is required", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        if any(field not in input or type(input[field]) is not int for field in self._fields):
            raise HistoryFault("VALIDATION", "Integer coordinates (x, y, width, height) are required", 422)
        if input["x"] < 0 or input["y"] < 0 or input["width"] < 1 or input["height"] < 1:
            raise HistoryFault("VALIDATION", "Region dimensions must be positive integers", 422)

        region_id = input.get("region_id")
        if not isinstance(region_id, str) or not region_id:
            region_id = str(uuid.uuid4())

        existing_in_panel = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id).all()
        seq_in_panel = len(existing_in_panel) + 1
        total_project_regions = db.query(TextRegionRecord).filter(TextRegionRecord.project_id == project.id).count()

        region_type = input.get("region_type", "SPEECH")
        if not isinstance(region_type, str):
            region_type = "SPEECH"

        operation_id = input["_history_operation_id"]
        paths: list[str] = []
        if (Path(project.workspace_path) / "ocr" / "ocr.json").is_file():
            paths.append("ocr/ocr.json")
        if paths:
            RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "region_id": region_id,
            "project_id": project.id,
            "page_id": panel.page_id,
            "panel_id": panel.id,
            "sequence_in_panel": seq_in_panel,
            "sequence_global": total_project_regions + 1,
            "x": input["x"],
            "y": input["y"],
            "width": input["width"],
            "height": input["height"],
            "normalized_x": round(float(input["x"]) / float(panel.width), 4) if panel.width > 0 else 0.0,
            "normalized_y": round(float(input["y"]) / float(panel.height), 4) if panel.height > 0 else 0.0,
            "normalized_width": round(float(input["width"]) / float(panel.width), 4) if panel.width > 0 else 0.0,
            "normalized_height": round(float(input["height"]) / float(panel.height), 4) if panel.height > 0 else 0.0,
            "page_x": panel.x + input["x"],
            "page_y": panel.y + input["y"],
            "page_width": input["width"],
            "page_height": input["height"],
            "region_type": region_type,
            "confidence": 1.0,
            "status": "CONFIRMED",
            "detection_method": "MANUAL",
            "paths": paths,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        required = {
            "region_id", "project_id", "page_id", "panel_id", "sequence_in_panel", "sequence_global",
            "x", "y", "width", "height", "normalized_x", "normalized_y", "normalized_width", "normalized_height",
            "page_x", "page_y", "page_width", "page_height", "region_type", "confidence", "status", "detection_method",
            "operation_id",
        }
        return isinstance(payload, dict) and required.issubset(set(payload)) and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        existing = db.query(TextRegionRecord).filter(TextRegionRecord.id == payload["region_id"]).first()
        paths = payload.get("paths", [])
        if paths:
            store = RetainedAssetStore(project.workspace_path)
        if forward:
            if existing is not None:
                raise HistoryFault("CONFLICT", "Text region already exists", 409)
            tr = TextRegionRecord(
                id=payload["region_id"],
                project_id=project.id,
                page_id=payload["page_id"],
                panel_id=payload["panel_id"],
                sequence_in_panel=payload["sequence_in_panel"],
                sequence_global=payload["sequence_global"],
                x=payload["x"],
                y=payload["y"],
                width=payload["width"],
                height=payload["height"],
                normalized_x=payload["normalized_x"],
                normalized_y=payload["normalized_y"],
                normalized_width=payload["normalized_width"],
                normalized_height=payload["normalized_height"],
                page_x=payload["page_x"],
                page_y=payload["page_y"],
                page_width=payload["page_width"],
                page_height=payload["page_height"],
                region_type=payload["region_type"],
                confidence=payload["confidence"],
                status=payload["status"],
                detection_method=payload["detection_method"],
                crop_filename="",
                crop_sha256="",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db.add(tr)
            db.flush()
            if paths:
                if store.is_complete(payload["operation_id"]):
                    store.restore(payload["operation_id"], "after")
                else:
                    store.capture_after(payload["operation_id"])
        else:
            if existing is not None:
                db.delete(existing)
                db.flush()
            if paths:
                store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        if payload.get("paths"):
            RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class TextRegionUpdateStrategy:
    """Update text region coordinates, classification, corrected text, or speaker attribution."""
    _allowed_fields = {
        "x", "y", "width", "height",
        "region_type", "status",
        "corrected_text", "corrected_by", "correction_status",
        "speaker_character_id", "speaker_confidence", "speaker_assignment_method",
    }

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        if not isinstance(input.get("region_id"), str):
            raise HistoryFault("VALIDATION", "Region ID is required", 422)

        tr = db.query(TextRegionRecord).filter(TextRegionRecord.id == input["region_id"], TextRegionRecord.project_id == project.id).first()
        if tr is None:
            raise HistoryFault("NOT_FOUND", "Text region not found", 404)

        panel = db.get(PanelRecord, tr.panel_id)
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Parent panel not found", 404)

        before = {}
        after = {}
        geom_changed = False

        for field in self._allowed_fields:
            if field in input:
                val = input[field]
                if field in ("x", "y", "width", "height"):
                    if type(val) is not int or (field in ("width", "height") and val < 1) or val < 0:
                        raise HistoryFault("VALIDATION", f"Invalid coordinate for {field}", 422)
                    if getattr(tr, field) != val:
                        geom_changed = True
                curr = getattr(tr, field)
                if curr != val:
                    before[field] = curr
                    after[field] = val

        if not before:
            return None

        # If geometry changed, also track derived coordinates
        if geom_changed:
            for deriv in ("normalized_x", "normalized_y", "normalized_width", "normalized_height",
                          "page_x", "page_y", "page_width", "page_height"):
                before[deriv] = getattr(tr, deriv)

            new_x = after.get("x", tr.x)
            new_y = after.get("y", tr.y)
            new_w = after.get("width", tr.width)
            new_h = after.get("height", tr.height)
            after["normalized_x"] = round(float(new_x) / float(panel.width), 4) if panel.width > 0 else 0.0
            after["normalized_y"] = round(float(new_y) / float(panel.height), 4) if panel.height > 0 else 0.0
            after["normalized_width"] = round(float(new_w) / float(panel.width), 4) if panel.width > 0 else 0.0
            after["normalized_height"] = round(float(new_h) / float(panel.height), 4) if panel.height > 0 else 0.0
            after["page_x"] = panel.x + new_x
            after["page_y"] = panel.y + new_y
            after["page_width"] = new_w
            after["page_height"] = new_h

        # Capture assets before if any exist
        operation_id = input["_history_operation_id"]
        paths: list[str] = []
        if tr.crop_filename and (Path(project.workspace_path) / "text_regions" / tr.crop_filename).is_file():
            paths.append(f"text_regions/{tr.crop_filename}")
        if (Path(project.workspace_path) / "ocr" / "ocr.json").is_file():
            paths.append("ocr/ocr.json")
        if paths:
            RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "region_id": tr.id,
            "before": before,
            "after": after,
            "paths": paths,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) >= {"region_id", "before", "after", "operation_id"}
            and isinstance(payload["region_id"], str)
            and isinstance(payload["before"], dict)
            and isinstance(payload["after"], dict)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        tr = db.query(TextRegionRecord).filter(TextRegionRecord.id == payload["region_id"], TextRegionRecord.project_id == project.id).first()
        if tr is None:
            raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)

        values = payload["after" if forward else "before"]
        for field, value in values.items():
            setattr(tr, field, value)

        if "corrected_text" in values:
            if forward:
                tr.corrected_at = utc_now()
                if "correction_status" not in values:
                    tr.correction_status = "EDITED"
                if "corrected_by" not in values:
                    tr.corrected_by = "USER"
            try:
                from engine.story.dependency import dependency_graph, PipelineEntityTier
                dependency_graph.invalidate(project.id, PipelineEntityTier.OCR)
            except Exception:
                pass

        if "speaker_character_id" in values:
            try:
                from engine.story.dependency import dependency_graph, PipelineEntityTier
                dependency_graph.invalidate(project.id, PipelineEntityTier.SPEAKER)
            except Exception:
                pass

        tr.updated_at = utc_now()
        db.flush()

        paths = payload.get("paths", [])
        if paths:
            store = RetainedAssetStore(project.workspace_path)
            if forward:
                if store.is_complete(payload["operation_id"]):
                    store.restore(payload["operation_id"], "after")
                else:
                    store.capture_after(payload["operation_id"])
            else:
                store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        if payload.get("paths"):
            RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class TextRegionDeleteStrategy:
    """Delete a text region with asset retention and restore on undo."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        if not isinstance(input.get("region_id"), str):
            raise HistoryFault("VALIDATION", "Region ID is required", 422)

        tr = db.query(TextRegionRecord).filter(TextRegionRecord.id == input["region_id"], TextRegionRecord.project_id == project.id).first()
        if tr is None:
            raise HistoryFault("NOT_FOUND", "Text region not found", 404)

        paths: list[str] = []
        if tr.crop_filename and (Path(project.workspace_path) / "text_regions" / tr.crop_filename).is_file():
            paths.append(f"text_regions/{tr.crop_filename}")
        if (Path(project.workspace_path) / "ocr" / "ocr.json").is_file():
            paths.append("ocr/ocr.json")

        operation_id = input["_history_operation_id"]
        if paths:
            RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "region": _row_data(tr),
            "paths": paths,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) >= {"region", "operation_id"}
            and isinstance(payload["region"], dict)
            and isinstance(payload["region"].get("id"), str)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        region_data = payload["region"]
        tr = db.query(TextRegionRecord).filter(TextRegionRecord.id == region_data["id"], TextRegionRecord.project_id == project.id).first()
        paths = payload.get("paths", [])
        if paths:
            store = RetainedAssetStore(project.workspace_path)

        if forward:
            if tr is None:
                raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
            db.delete(tr)
            db.flush()
            if paths:
                if store.is_complete(payload["operation_id"]):
                    store.restore(payload["operation_id"], "after")
                else:
                    if region_data.get("crop_filename"):
                        crop_p = Path(project.workspace_path) / "text_regions" / region_data["crop_filename"]
                        if crop_p.is_file() and not crop_p.is_symlink():
                            try:
                                crop_p.unlink()
                            except Exception:
                                pass
                    store.capture_after(payload["operation_id"])
        else:
            if tr is not None:
                raise HistoryFault("CONFLICT", "Text region already exists", 409)
            restored = _restore_text_region(region_data)
            db.add(restored)
            db.flush()
            if paths:
                store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        if payload.get("paths"):
            RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class OCRBlockUpdateStrategy:
    """Edit adapted OCR blocks on an OCRRecord, retaining ocr/ocr.json."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        if not isinstance(input.get("panel_id"), str) or not isinstance(input.get("block_id"), str):
            raise HistoryFault("VALIDATION", "Panel ID and block ID are required", 422)

        record = db.query(OCRRecord).filter(OCRRecord.panel_id == input["panel_id"], OCRRecord.project_id == project.id).first()
        if record is None:
            raise HistoryFault("NOT_FOUND", f"OCR record not found for panel {input['panel_id']}", 404)

        before_blocks = deepcopy(record.adapted_blocks or [])
        before_status = record.status

        after_blocks = [dict(b) for b in before_blocks]
        found = False
        block_id = input["block_id"]
        speaker = input.get("speaker")
        text = input.get("text", "")
        classification = input.get("classification", "dialogue")
        notes = input.get("notes", "")

        for item in after_blocks:
            if item.get("id") == block_id or item.get("raw_region_id") == block_id:
                item["speaker"] = speaker
                item["text"] = text
                item["classification"] = classification
                item["notes"] = notes
                found = True
                break

        if not found:
            after_blocks.append({
                "id": block_id,
                "raw_region_id": block_id,
                "speaker": speaker,
                "text": text,
                "classification": classification,
                "notes": notes,
            })

        if before_blocks == after_blocks and before_status == "EDITED":
            return None

        operation_id = input["_history_operation_id"]
        paths = ["ocr/ocr.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "panel_id": input["panel_id"],
            "before_blocks": before_blocks,
            "after_blocks": after_blocks,
            "before_status": before_status,
            "after_status": "EDITED",
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"panel_id", "before_blocks", "after_blocks", "before_status", "after_status", "operation_id"}
            and isinstance(payload["panel_id"], str)
            and isinstance(payload["before_blocks"], list)
            and isinstance(payload["after_blocks"], list)
            and isinstance(payload["before_status"], str)
            and isinstance(payload["after_status"], str)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        record = db.query(OCRRecord).filter(OCRRecord.panel_id == payload["panel_id"], OCRRecord.project_id == project.id).first()
        if record is None:
            raise HistoryFault("CONFLICT", f"OCR record for panel {payload['panel_id']} not found", 409)

        store = RetainedAssetStore(project.workspace_path)
        blocks = deepcopy(payload["after_blocks" if forward else "before_blocks"])
        status = payload["after_status" if forward else "before_status"]

        record.adapted_blocks = blocks
        flag_modified(record, "adapted_blocks")
        record.status = status
        record.updated_at = utc_now()
        db.flush()

        if forward:
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                project_service._sync_ocr_json(db, project.id)
                store.capture_after(payload["operation_id"])
        else:
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class OCRConfirmStrategy:
    """Approve OCR stage gate (PipelineStage.OCR_APPROVED), retaining project.json and ocr/ocr.json."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)

        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project.id).all()
        if not panels:
            raise HistoryFault("VALIDATION", "Cannot approve OCR: No panels detected or confirmed in project", 422)

        unresolved_regions = (
            db.query(TextRegionRecord)
            .filter(
                TextRegionRecord.project_id == project.id,
                TextRegionRecord.status == "NEEDS_REVIEW",
            )
            .all()
        )
        if unresolved_regions:
            raise HistoryFault(
                "VALIDATION",
                f"Cannot approve OCR: {len(unresolved_regions)} text regions have 'NEEDS_REVIEW' status",
                422,
            )

        operation_id = input["_history_operation_id"]
        paths = ["project.json", "ocr/ocr.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "before_stage": project.current_stage,
            "after_stage": PipelineStage.OCR_APPROVED.value,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"before_stage", "after_stage", "operation_id"}
            and isinstance(payload["before_stage"], str)
            and isinstance(payload["after_stage"], str)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        if forward:
            project.current_stage = payload["after_stage"]
            project.updated_at = utc_now()
            db.flush()
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                project_service._write_project_json(project)
                project_service._sync_ocr_json(db, project.id)
                store.capture_after(payload["operation_id"])
        else:
            project.current_stage = payload["before_stage"]
            project.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")
