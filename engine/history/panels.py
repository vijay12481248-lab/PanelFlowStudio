"""History strategies for reversible panel mutations."""
from __future__ import annotations

from copy import deepcopy
import json
from uuid import NAMESPACE_URL, uuid4, uuid5

from PIL import Image, ImageDraw

from engine.database.models import OCRRecord, PanelRecord, PageRecord, TextRegionRecord, utc_now
from engine.history.assets import RetainedAssetStore
from engine.history.contracts import HistoryFault
from engine.imaging.panels import PanelBox, panel_detector
from engine.imaging.redaction import (
    blur_entire_image,
    blur_image_box,
    has_image_backup,
    restore_image_backup,
)
from engine.projects.service import project_service
from engine.projects.panel_selections import Selection, validate_selection
from engine.security.paths import project_path


class PanelReorderStrategy:
    def prepare(self, db, project, input):
        panel_ids = input.get("panel_ids") if isinstance(input, dict) else None
        operation_id = input.get("_history_operation_id") if isinstance(input, dict) else None
        if (not isinstance(panel_ids, list) or not all(isinstance(panel_id, str) for panel_id in panel_ids)
                or not isinstance(operation_id, str)):
            raise HistoryFault("VALIDATION", "Panel order and history operation are required", 422)
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project.id).order_by(PanelRecord.sequence).all()
        before = [panel.id for panel in panels]
        if len(panel_ids) != len(before) or set(panel_ids) != set(before):
            raise HistoryFault("VALIDATION", "Panel order must contain every project panel exactly once", 422)
        if panel_ids == before:
            return None
        store = RetainedAssetStore(project.workspace_path)
        store.capture_before(operation_id, ["panels/panels.json"])
        return {"before": before, "after": list(panel_ids), "operation_id": operation_id}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"before", "after", "operation_id"}
                and isinstance(payload["operation_id"], str)
                and all(isinstance(panel_id, str) for panel_id in payload["before"])
                and all(isinstance(panel_id, str) for panel_id in payload["after"])
                and len(payload["before"]) == len(payload["after"])
                and set(payload["before"]) == set(payload["after"]))

    def apply(self, db, project, payload, *, forward):
        order = payload["after" if forward else "before"]
        panels = db.query(PanelRecord).filter(PanelRecord.project_id == project.id).all()
        panel_map = {panel.id: panel for panel in panels}
        if set(panel_map) != set(order):
            raise HistoryFault("CONFLICT", "Panel inventory changed outside history", 409)
        for sequence, panel_id in enumerate(order, start=1):
            panel_map[panel_id].sequence = sequence
        store = RetainedAssetStore(project.workspace_path)
        if forward:
            if store.is_complete(payload["operation_id"]):
                # Redo must restore the exact persisted file, not rewrite a
                # potentially newer serialization with a different ordering.
                store.restore(payload["operation_id"], "after")
            else:
                project_service._sync_panels_json(db, project.id)
                store.capture_after(payload["operation_id"])
        else:
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        store.restore(payload["operation_id"], "before" if forward else "after")


class PanelGeometryStrategy:
    _fields = ("x", "y", "width", "height", "status", "panel_type")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel and history operation are required", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        after = {field: input.get(field, getattr(panel, field)) for field in self._fields}
        if (not all(type(after[field]) is int for field in ("x", "y", "width", "height"))
                or after["x"] < 0 or after["y"] < 0 or after["width"] < 1 or after["height"] < 1
                or any(after[field] is not None and not isinstance(after[field], str) for field in ("status", "panel_type"))):
            raise HistoryFault("VALIDATION", "Invalid panel geometry", 422)
        page = db.get(PageRecord, panel.page_id)
        if page is None or after["x"] + after["width"] > page.width or after["y"] + after["height"] > page.height:
            raise HistoryFault("VALIDATION", "Panel geometry must remain within its source page", 422)
        before = {field: getattr(panel, field) for field in self._fields}
        if before == after:
            return None
        operation_id = input["_history_operation_id"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, [f"panels/{panel.crop_filename}", "panels/panels.json"])
        return {"panel_id": panel.id, "before": before, "after": after, "operation_id": operation_id}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"panel_id", "before", "after", "operation_id"}
                and isinstance(payload["panel_id"], str) and isinstance(payload["operation_id"], str)
                and all(isinstance(payload[phase], dict) and set(payload[phase]) == set(self._fields) for phase in ("before", "after")))

    def apply(self, db, project, payload, *, forward):
        panel = db.query(PanelRecord).filter(PanelRecord.id == payload["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
        values = payload["after" if forward else "before"]
        page = db.get(PageRecord, panel.page_id)
        if page is None:
            raise HistoryFault("CONFLICT", "Panel source page was removed outside history", 409)
        for field, value in values.items():
            setattr(panel, field, value)
        panel.normalized_x = round(panel.x / float(page.width), 4)
        panel.normalized_y = round(panel.y / float(page.height), 4)
        panel.normalized_width = round(panel.width / float(page.width), 4)
        panel.normalized_height = round(panel.height / float(page.height), 4)
        panel.manually_modified = True
        panel.updated_at = utc_now()
        store = RetainedAssetStore(project.workspace_path)
        if forward:
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
                return
            source = project_path(project.workspace_path, "normalized", f"page_{page.sequence:04d}.jpg")
            if not source.is_file():
                source = project_path(project.workspace_path, "source", page.filename)
            panel_detector.extract_crop(source, PanelBox(id=panel.id, page_id=panel.page_id, sequence=panel.page_sequence,
                x=panel.x, y=panel.y, width=panel.width, height=panel.height), project_path(project.workspace_path, "panels", panel.crop_filename))
            project_service._sync_panels_json(db, project.id)
            store.capture_after(payload["operation_id"])
        else:
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")

class PanelCreateStrategy:
    """Create a manually drawn panel without leaving an unjournaled crop file."""
    _fields = ("page_id", "x", "y", "width", "height", "panel_type")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        if any(field not in input for field in self._fields):
            raise HistoryFault("VALIDATION", "Panel page and geometry are required", 422)
        page = db.query(PageRecord).filter(PageRecord.id == input["page_id"], PageRecord.project_id == project.id).first()
        if page is None:
            raise HistoryFault("NOT_FOUND", "Panel page not found", 404)
        if (not all(type(input[field]) is int for field in ("x", "y", "width", "height"))
                or input["x"] < 0 or input["y"] < 0 or input["width"] < 1 or input["height"] < 1
                or input["x"] + input["width"] > page.width or input["y"] + input["height"] > page.height
                or not isinstance(input["panel_type"], str) or not input["panel_type"]):
            raise HistoryFault("VALIDATION", "Panel geometry must fit its source page", 422)
        next_sequence = db.query(PanelRecord).filter(PanelRecord.project_id == project.id).count() + 1
        next_page_sequence = db.query(PanelRecord).filter(PanelRecord.page_id == page.id).count() + 1
        panel_id = input.get("panel_id")
        if panel_id is not None and (not isinstance(panel_id, str) or not panel_id):
            raise HistoryFault("VALIDATION", "Panel ID must be a non-empty string", 422)
        panel = {field: input[field] for field in self._fields}
        panel.update({"id": panel_id or str(uuid4()), "sequence": next_sequence, "page_sequence": next_page_sequence,
                      "crop_filename": f"panel_{next_sequence:04d}.jpg"})
        RetainedAssetStore(project.workspace_path).capture_before(input["_history_operation_id"], [f"panels/{panel['crop_filename']}", "panels/panels.json"])
        return {"panel": panel, "operation_id": input["_history_operation_id"]}

    def validate(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"panel", "operation_id"} or not isinstance(payload["operation_id"], str):
            return False
        panel = payload["panel"]
        return (isinstance(panel, dict) and set(panel) == {"id", "page_id", "x", "y", "width", "height", "panel_type", "sequence", "page_sequence", "crop_filename"}
                and all(isinstance(panel[field], str) and panel[field] for field in ("id", "page_id", "panel_type", "crop_filename"))
                and all(type(panel[field]) is int and panel[field] > 0 for field in ("width", "height", "sequence", "page_sequence"))
                and all(type(panel[field]) is int and panel[field] >= 0 for field in ("x", "y")))

    def apply(self, db, project, payload, *, forward):
        panel_data = payload["panel"]
        store = RetainedAssetStore(project.workspace_path)
        if not forward:
            panel = db.query(PanelRecord).filter(PanelRecord.id == panel_data["id"], PanelRecord.project_id == project.id).first()
            if panel is None:
                raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
            db.delete(panel)
            db.flush()
            store.restore(payload["operation_id"], "before")
            return
        page = db.query(PageRecord).filter(PageRecord.id == panel_data["page_id"], PageRecord.project_id == project.id).first()
        if page is None:
            raise HistoryFault("CONFLICT", "Panel source page was removed outside history", 409)
        if db.query(PanelRecord).filter(PanelRecord.id == panel_data["id"]).first() is not None:
            raise HistoryFault("CONFLICT", "Panel already exists", 409)
        panel = PanelRecord(**panel_data, project_id=project.id,
            normalized_x=round(panel_data["x"] / float(page.width), 4), normalized_y=round(panel_data["y"] / float(page.height), 4),
            normalized_width=round(panel_data["width"] / float(page.width), 4), normalized_height=round(panel_data["height"] / float(page.height), 4),
            reading_direction="ltr", detection_method="MANUAL", confidence=1.0, status="MANUAL", manually_modified=True,
            created_at=utc_now(), updated_at=utc_now())
        db.add(panel)
        db.flush()
        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            return
        source = project_path(project.workspace_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not source.is_file(): source = project_path(project.workspace_path, "source", page.filename)
        panel_detector.extract_crop(source, PanelBox(id=panel.id, page_id=page.id, sequence=panel.page_sequence, page_sequence=panel.page_sequence,
            x=panel.x, y=panel.y, width=panel.width, height=panel.height), project_path(project.workspace_path, "panels", panel.crop_filename))
        project_service._sync_panels_json(db, project.id)
        store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


def _row_data(row):
    """JSON-safe persistent columns; audit timestamps are regenerated on restore."""
    return {column.name: getattr(row, column.name) for column in row.__table__.columns
            if column.name not in {"created_at", "updated_at"}}


def _resequence_without_commit(db, project_id):
    sequence = 1
    pages = db.query(PageRecord).filter(PageRecord.project_id == project_id).order_by(PageRecord.sequence).all()
    for page in pages:
        panels = db.query(PanelRecord).filter(PanelRecord.page_id == page.id).order_by(PanelRecord.sequence).all()
        for page_sequence, panel in enumerate(panels, start=1):
            panel.sequence, panel.page_sequence = sequence, page_sequence
            sequence += 1


class PanelDeleteStrategy:
    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel and history operation are required", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        ocr = db.query(OCRRecord).filter(OCRRecord.panel_id == panel.id).all()
        regions = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id).all()
        RetainedAssetStore(project.workspace_path).capture_before(input["_history_operation_id"], [f"panels/{panel.crop_filename}", "panels/panels.json"])
        return {"panel": _row_data(panel), "ocr": [_row_data(row) for row in ocr], "regions": [_row_data(row) for row in regions],
                "sequences": {row.id: [row.sequence, row.page_sequence] for row in db.query(PanelRecord).filter(PanelRecord.project_id == project.id)},
                "operation_id": input["_history_operation_id"]}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"panel", "ocr", "regions", "sequences", "operation_id"}
                and isinstance(payload["panel"], dict) and isinstance(payload["ocr"], list) and isinstance(payload["regions"], list)
                and isinstance(payload["sequences"], dict) and isinstance(payload["operation_id"], str)
                and isinstance(payload["panel"].get("id"), str) and isinstance(payload["panel"].get("crop_filename"), str))

    def apply(self, db, project, payload, *, forward):
        panel_data, store = payload["panel"], RetainedAssetStore(project.workspace_path)
        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_data["id"], PanelRecord.project_id == project.id).first()
        if forward:
            if panel is None:
                raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
            db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id).delete(synchronize_session=False)
            db.query(OCRRecord).filter(OCRRecord.panel_id == panel.id).delete(synchronize_session=False)
            db.delete(panel)
            db.flush()
            _resequence_without_commit(db, project.id)
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                crop = project_path(project.workspace_path, "panels", panel_data["crop_filename"])
                if crop.exists():
                    if not crop.is_file() or crop.is_symlink():
                        raise HistoryFault("CONFLICT", "Panel crop is not a regular project file", 409)
                    crop.unlink()
                project_service._sync_panels_json(db, project.id)
                store.capture_after(payload["operation_id"])
            return
        if panel is not None:
            raise HistoryFault("CONFLICT", "Panel already exists", 409)
        db.add(PanelRecord(**panel_data, created_at=utc_now(), updated_at=utc_now()))
        for row in payload["ocr"]: db.add(OCRRecord(**row, created_at=utc_now(), updated_at=utc_now()))
        for row in payload["regions"]: db.add(TextRegionRecord(**row, created_at=utc_now(), updated_at=utc_now()))
        db.flush()
        for panel_id, sequence in payload["sequences"].items():
            current = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project.id).first()
            if current is not None: current.sequence, current.page_sequence = sequence
        store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelSelectionsStrategy:
    """Replace a panel or add page selectors as one retained, reversible batch."""
    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        panel_id, page_id = input.get("panel_id"), input.get("page_id")
        if panel_id is not None and not isinstance(panel_id, str):
            raise HistoryFault("VALIDATION", "Panel ID is invalid", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project.id).first() if panel_id else None
        if panel_id and panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        page = db.query(PageRecord).filter(PageRecord.id == (panel.page_id if panel else page_id), PageRecord.project_id == project.id).first()
        if page is None:
            raise HistoryFault("NOT_FOUND", "Source page not found", 404)
        raw = input.get("selections")
        if not isinstance(raw, list) or not 1 <= len(raw) <= 64:
            raise HistoryFault("VALIDATION", "Provide between 1 and 64 selectors", 422)
        try:
            selectors = [Selection.model_validate(value).model_dump() for value in raw]
            bounds = (0, 0, page.width, page.height) if input.get("page_bounds") or not panel else (panel.x, panel.y, panel.width, panel.height)
            for value in selectors: validate_selection(Selection.model_validate(value), bounds)
        except (TypeError, ValueError) as error:
            raise HistoryFault("VALIDATION", str(error), 422) from error
        operation_id = input["_history_operation_id"]
        additions = [{"id": str(uuid5(NAMESPACE_URL, f"panelflow:{operation_id}:{index}")),
                      "crop_filename": f"selector_{operation_id.replace('-', '')}_{index}.png"} for index in range(len(selectors))]
        paths = ["panels/panels.json", *[f"panels/{item['crop_filename']}" for item in additions]]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)
        return {"before": [_row_data(row) for row in db.query(PanelRecord).filter(PanelRecord.project_id == project.id).order_by(PanelRecord.sequence)],
                "panel_id": panel_id, "page_id": page.id, "page_bounds": bool(input.get("page_bounds")), "selectors": selectors,
                "additions": additions, "operation_id": operation_id}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"before", "panel_id", "page_id", "page_bounds", "selectors", "additions", "operation_id"}
                and isinstance(payload["before"], list) and isinstance(payload["page_id"], str) and isinstance(payload["selectors"], list)
                and isinstance(payload["additions"], list) and len(payload["selectors"]) == len(payload["additions"])
                and isinstance(payload["operation_id"], str))

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        created_ids = [item["id"] for item in payload["additions"]]
        if not forward:
            db.query(PanelRecord).filter(PanelRecord.id.in_(created_ids), PanelRecord.project_id == project.id).delete(synchronize_session=False)
            original = {item["id"]: item for item in payload["before"]}
            current = {item.id: item for item in db.query(PanelRecord).filter(PanelRecord.project_id == project.id)}
            for panel_id, data in original.items():
                if panel_id in current:
                    for field, value in data.items(): setattr(current[panel_id], field, value)
                else:
                    db.add(PanelRecord(**data, created_at=utc_now(), updated_at=utc_now()))
            db.flush(); store.restore(payload["operation_id"], "before")
            return
        page = db.query(PageRecord).filter(PageRecord.id == payload["page_id"], PageRecord.project_id == project.id).first()
        target = db.query(PanelRecord).filter(PanelRecord.id == payload["panel_id"], PanelRecord.project_id == project.id).first() if payload["panel_id"] else None
        if payload["panel_id"] and target is None:
            raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
        if any(db.query(PanelRecord).filter(PanelRecord.id == item).first() is not None for item in created_ids):
            raise HistoryFault("CONFLICT", "Selector panels already exist", 409)
        before_count = db.query(PanelRecord).filter(PanelRecord.project_id == project.id).count()
        new_panels = []
        for index, raw in enumerate(payload["selectors"]):
            selection, addition = Selection.model_validate(raw), payload["additions"][index]
            panel = target if index == 0 and target else PanelRecord(id=addition["id"], project_id=project.id, page_id=page.id,
                sequence=(target.sequence if target else before_count + index + 1), page_sequence=1,
                reading_direction=(target.reading_direction if target else "ltr"), panel_type=(target.panel_type if target else "STANDARD"))
            panel.x, panel.y, panel.width, panel.height = selection.x, selection.y, selection.width, selection.height
            panel.normalized_x, panel.normalized_y = selection.x / page.width, selection.y / page.height
            panel.normalized_width, panel.normalized_height = selection.width / page.width, selection.height / page.height
            panel.polygon_json = json.dumps(selection.points) if selection.points else None
            panel.crop_filename, panel.manually_modified, panel.detection_method, panel.status, panel.confidence = addition["crop_filename"], True, "MANUAL", "MANUAL", 1.0
            panel.updated_at = utc_now(); db.add(panel); new_panels.append((panel, selection))
        _resequence_without_commit(db, project.id); db.flush()
        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            return
        source = project_path(project.workspace_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not source.is_file(): source = project_path(project.workspace_path, "source", page.filename)
        with Image.open(source) as image:
            for panel, selection in new_panels:
                crop = image.crop((selection.x, selection.y, selection.x + selection.width, selection.y + selection.height)).convert("RGBA")
                if selection.points:
                    mask = Image.new("L", crop.size, 0); ImageDraw.Draw(mask).polygon([(x - selection.x, y - selection.y) for x, y in selection.points], fill=255); crop.putalpha(mask)
                crop.save(project_path(project.workspace_path, "panels", panel.crop_filename))
        project_service._sync_panels_json(db, project.id); store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelSplitStrategy:
    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel and history operation are required", 422)
        direction, ratio = input.get("split_type", "horizontal"), input.get("ratio", 0.5)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None: raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        if direction not in {"horizontal", "vertical"} or not isinstance(ratio, (float, int)) or isinstance(ratio, bool) or not 0 < ratio < 1:
            raise HistoryFault("VALIDATION", "Split direction or ratio is invalid", 422)
        total = panel.height if direction == "horizontal" else panel.width
        first, second = int(total * ratio), total - int(total * ratio)
        if first < 20 or second < 20: raise HistoryFault("VALIDATION", "Both split panels must be at least 20 pixels", 422)
        operation_id = input["_history_operation_id"]
        child = {"id": str(uuid5(NAMESPACE_URL, f"panelflow:split:{operation_id}")), "crop_filename": f"split_{operation_id.replace('-', '')}.jpg"}
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, [f"panels/{panel.crop_filename}", f"panels/{child['crop_filename']}", "panels/panels.json"])
        return {"before": [_row_data(row) for row in db.query(PanelRecord).filter(PanelRecord.project_id == project.id).order_by(PanelRecord.sequence)],
                "panel_id": panel.id, "split_type": direction, "ratio": float(ratio), "child": child, "operation_id": operation_id}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"before", "panel_id", "split_type", "ratio", "child", "operation_id"}
                and isinstance(payload["before"], list) and isinstance(payload["panel_id"], str) and payload["split_type"] in {"horizontal", "vertical"}
                and isinstance(payload["ratio"], float) and 0 < payload["ratio"] < 1 and isinstance(payload["child"], dict)
                and isinstance(payload["child"].get("id"), str) and isinstance(payload["child"].get("crop_filename"), str))

    def apply(self, db, project, payload, *, forward):
        store, child = RetainedAssetStore(project.workspace_path), payload["child"]
        if not forward:
            db.query(PanelRecord).filter(PanelRecord.id == child["id"], PanelRecord.project_id == project.id).delete(synchronize_session=False)
            current = {row.id: row for row in db.query(PanelRecord).filter(PanelRecord.project_id == project.id)}
            for data in payload["before"]:
                row = current.get(data["id"])
                if row is None: db.add(PanelRecord(**data, created_at=utc_now(), updated_at=utc_now()))
                else:
                    for field, value in data.items(): setattr(row, field, value)
            db.flush(); store.restore(payload["operation_id"], "before")
            return
        panel = db.query(PanelRecord).filter(PanelRecord.id == payload["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None: raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
        if db.query(PanelRecord).filter(PanelRecord.id == child["id"]).first() is not None: raise HistoryFault("CONFLICT", "Split panel already exists", 409)
        page = db.get(PageRecord, panel.page_id)
        first = int((panel.height if payload["split_type"] == "horizontal" else panel.width) * payload["ratio"])
        if payload["split_type"] == "horizontal": first_box, second_box = (panel.x, panel.y, panel.width, first), (panel.x, panel.y + first, panel.width, panel.height - first)
        else: first_box, second_box = (panel.x, panel.y, first, panel.height), (panel.x + first, panel.y, panel.width - first, panel.height)
        panel.x, panel.y, panel.width, panel.height = first_box
        panel.normalized_x, panel.normalized_y = panel.x / page.width, panel.y / page.height
        panel.normalized_width, panel.normalized_height = panel.width / page.width, panel.height / page.height
        panel.manually_modified, panel.updated_at = True, utc_now()
        added = PanelRecord(id=child["id"], project_id=project.id, page_id=page.id, sequence=panel.sequence + 1, page_sequence=panel.page_sequence + 1,
            x=second_box[0], y=second_box[1], width=second_box[2], height=second_box[3], normalized_x=second_box[0] / page.width, normalized_y=second_box[1] / page.height,
            normalized_width=second_box[2] / page.width, normalized_height=second_box[3] / page.height, crop_filename=child["crop_filename"], reading_direction=panel.reading_direction,
            detection_method="MANUAL", confidence=1.0, panel_type=panel.panel_type, status="MANUAL", manually_modified=True, created_at=utc_now(), updated_at=utc_now())
        db.add(added); _resequence_without_commit(db, project.id); db.flush()
        if store.is_complete(payload["operation_id"]): store.restore(payload["operation_id"], "after"); return
        source = project_path(project.workspace_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not source.is_file(): source = project_path(project.workspace_path, "source", page.filename)
        for item in (panel, added):
            panel_detector.extract_crop(source, PanelBox(id=item.id, page_id=item.page_id, sequence=item.page_sequence, x=item.x, y=item.y, width=item.width, height=item.height), project_path(project.workspace_path, "panels", item.crop_filename))
        project_service._sync_panels_json(db, project.id); store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelMergeStrategy:
    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_ids"), list) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel IDs and history operation are required", 422)
        panel_ids = input["panel_ids"]
        if len(panel_ids) < 2 or len(set(panel_ids)) != len(panel_ids) or not all(isinstance(value, str) for value in panel_ids):
            raise HistoryFault("VALIDATION", "Merge requires two or more unique panel IDs", 422)
        panels = db.query(PanelRecord).filter(PanelRecord.id.in_(panel_ids), PanelRecord.project_id == project.id).all()
        if len(panels) != len(panel_ids): raise HistoryFault("NOT_FOUND", "One or more panels were not found", 404)
        if len({panel.page_id for panel in panels}) != 1: raise HistoryFault("VALIDATION", "Merged panels must share a page", 422)
        operation_id = input["_history_operation_id"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, [*[f"panels/{panel.crop_filename}" for panel in panels], "panels/panels.json"])
        removed_ids = {panel.id for panel in panels}
        return {"before": [_row_data(row) for row in db.query(PanelRecord).filter(PanelRecord.project_id == project.id).order_by(PanelRecord.sequence)],
                "ocr": [_row_data(row) for row in db.query(OCRRecord).filter(OCRRecord.panel_id.in_(removed_ids))],
                "regions": [_row_data(row) for row in db.query(TextRegionRecord).filter(TextRegionRecord.panel_id.in_(removed_ids))],
                "panel_ids": panel_ids, "operation_id": operation_id}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"before", "ocr", "regions", "panel_ids", "operation_id"}
                and isinstance(payload["before"], list) and isinstance(payload["ocr"], list) and isinstance(payload["regions"], list)
                and isinstance(payload["panel_ids"], list) and len(payload["panel_ids"]) >= 2 and len(set(payload["panel_ids"])) == len(payload["panel_ids"])
                and all(isinstance(value, str) for value in payload["panel_ids"]) and isinstance(payload["operation_id"], str))

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        before = {item["id"]: item for item in payload["before"]}
        if not forward:
            current = {row.id: row for row in db.query(PanelRecord).filter(PanelRecord.project_id == project.id)}
            for panel_id, data in before.items():
                row = current.get(panel_id)
                if row is None: db.add(PanelRecord(**data, created_at=utc_now(), updated_at=utc_now()))
                else:
                    for field, value in data.items(): setattr(row, field, value)
            db.flush()
            for row in payload["ocr"]:
                if db.get(OCRRecord, row["id"]) is None: db.add(OCRRecord(**row, created_at=utc_now(), updated_at=utc_now()))
            for row in payload["regions"]:
                if db.get(TextRegionRecord, row["id"]) is None: db.add(TextRegionRecord(**row, created_at=utc_now(), updated_at=utc_now()))
            db.flush(); store.restore(payload["operation_id"], "before")
            return
        panels = [db.query(PanelRecord).filter(PanelRecord.id == panel_id, PanelRecord.project_id == project.id).first() for panel_id in payload["panel_ids"]]
        if any(panel is None for panel in panels): raise HistoryFault("CONFLICT", "Panel inventory changed outside history", 409)
        primary, others = sorted(panels, key=lambda panel: panel.sequence)[0], sorted(panels, key=lambda panel: panel.sequence)[1:]
        page = db.get(PageRecord, primary.page_id)
        x, y = min(panel.x for panel in panels), min(panel.y for panel in panels)
        width, height = max(panel.x + panel.width for panel in panels) - x, max(panel.y + panel.height for panel in panels) - y
        primary.x, primary.y, primary.width, primary.height = x, y, width, height
        primary.normalized_x, primary.normalized_y = x / page.width, y / page.height
        primary.normalized_width, primary.normalized_height = width / page.width, height / page.height
        primary.status, primary.detection_method, primary.manually_modified, primary.confidence, primary.updated_at = "MANUAL", "MANUAL", True, 1.0, utc_now()
        for panel in others:
            db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id).delete(synchronize_session=False)
            db.query(OCRRecord).filter(OCRRecord.panel_id == panel.id).delete(synchronize_session=False)
            db.delete(panel)
        db.flush(); _resequence_without_commit(db, project.id); db.flush()
        if store.is_complete(payload["operation_id"]): store.restore(payload["operation_id"], "after"); return
        source = project_path(project.workspace_path, "normalized", f"page_{page.sequence:04d}.jpg")
        if not source.is_file(): source = project_path(project.workspace_path, "source", page.filename)
        panel_detector.extract_crop(source, PanelBox(id=primary.id, page_id=primary.page_id, sequence=primary.page_sequence, x=x, y=y, width=width, height=height), project_path(project.workspace_path, "panels", primary.crop_filename))
        for panel in others:
            crop = project_path(project.workspace_path, "panels", before[panel.id]["crop_filename"])
            if crop.exists():
                if not crop.is_file() or crop.is_symlink(): raise HistoryFault("CONFLICT", "Panel crop is not a regular project file", 409)
                crop.unlink()
        project_service._sync_panels_json(db, project.id); store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelConfirmStrategy:
    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        if not db.query(PanelRecord).filter(PanelRecord.project_id == project.id).count():
            raise HistoryFault("VALIDATION", "Cannot confirm panel review with zero panels", 422)
        settings = deepcopy(project.settings or {})
        state = settings.get("story_editor_state")
        if isinstance(state, dict):
            sync = dict(state.get("panel_review_sync") or {})
            sync.update({"last_panel_confirm": utc_now().isoformat(), "panels_stale": True})
            settings["story_editor_state"] = {**state, "panel_review_sync": sync}
        operation_id = input["_history_operation_id"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, ["project.json", "panels/panels.json"])
        return {"before_stage": project.current_stage, "before_settings": deepcopy(project.settings or {}), "after_settings": settings, "operation_id": operation_id}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"before_stage", "before_settings", "after_settings", "operation_id"}
                and isinstance(payload["before_stage"], str) and isinstance(payload["before_settings"], dict)
                and isinstance(payload["after_settings"], dict) and isinstance(payload["operation_id"], str))

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        if forward:
            project.current_stage, project.settings, project.updated_at = "PANELS_DETECTED", deepcopy(payload["after_settings"]), utc_now()
            db.flush()
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                project_service._write_project_json(project)
                project_service._sync_panels_json(db, project.id)
                store.capture_after(payload["operation_id"])
        else:
            project.current_stage, project.settings, project.updated_at = payload["before_stage"], deepcopy(payload["before_settings"]), utc_now()
            db.flush(); store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelImageResetStrategy:
    """Reset an edited crop while retaining the consumed backup for undo."""
    _region_fields = ("status", "region_type", "corrected_text", "correction_status")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel and history operation are required", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        crop = project_path(project.workspace_path, "panels", panel.crop_filename)
        if not crop.is_file():
            raise HistoryFault("NOT_FOUND", "Panel crop file is missing", 404)
        regions = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id, TextRegionRecord.project_id == project.id, TextRegionRecord.status == "BLURRED").all()
        paths = [f"panels/{panel.crop_filename}", f"panels/.originals/{panel.crop_filename}"]
        for region in regions:
            if region.crop_filename:
                paths.extend([f"text_regions/{region.crop_filename}", f"text_regions/.originals/{region.crop_filename}"])
        RetainedAssetStore(project.workspace_path).capture_before(input["_history_operation_id"], list(dict.fromkeys(paths)))
        return {"panel_id": panel.id, "regions": [{"id": region.id, "before": {field: getattr(region, field) for field in self._region_fields}}
                                                  for region in regions], "operation_id": input["_history_operation_id"]}

    def validate(self, payload):
        return (isinstance(payload, dict) and set(payload) == {"panel_id", "regions", "operation_id"} and isinstance(payload["panel_id"], str)
                and isinstance(payload["regions"], list) and isinstance(payload["operation_id"], str)
                and all(isinstance(item, dict) and isinstance(item.get("id"), str) and set(item.get("before", {})) == set(self._region_fields) for item in payload["regions"]))

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        panel = db.query(PanelRecord).filter(PanelRecord.id == payload["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
        if not forward:
            for item in payload["regions"]:
                region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
                if region is None:
                    raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
                for field, value in item["before"].items():
                    setattr(region, field, value)
                region.updated_at = utc_now()
            db.flush(); store.restore(payload["operation_id"], "before")
            return
        if store.is_complete(payload["operation_id"]):
            for item in payload["regions"]:
                region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
                if region is None:
                    raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
                region.status, region.region_type = "CONFIRMED", "SPEECH"
                region.corrected_text, region.correction_status, region.updated_at = region.raw_text or "", "UNEDITED", utc_now()
            db.flush()
            store.restore(payload["operation_id"], "after")
            return
        restored = restore_image_backup(project_path(project.workspace_path, "panels", panel.crop_filename))
        for item in payload["regions"]:
            region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
            if region is None:
                raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
            region.status, region.region_type = "CONFIRMED", "SPEECH"
            region.corrected_text, region.correction_status, region.updated_at = region.raw_text or "", "UNEDITED", utc_now()
            if region.crop_filename:
                restore_image_backup(project_path(project.workspace_path, "text_regions", region.crop_filename))
        if not restored and not payload["regions"]:
            raise HistoryFault("VALIDATION", "Panel image has no resettable changes", 422)
        db.flush(); store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelBlurBoxStrategy:
    """Blur a rectangular bounding box within a panel crop."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel and history operation are required", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        crop = project_path(project.workspace_path, "panels", panel.crop_filename)
        if not crop.is_file():
            raise HistoryFault("NOT_FOUND", "Panel crop file is missing", 404)

        x = input.get("x")
        y = input.get("y")
        width = input.get("width")
        height = input.get("height")
        blur_radius = input.get("blur_radius", 24)
        feather = input.get("feather", 4)
        if not all(type(v) is int for v in (x, y, width, height, blur_radius, feather)):
            raise HistoryFault("VALIDATION", "Blur coordinates and parameters must be integers", 422)
        if width <= 0 or height <= 0 or x < 0 or y < 0 or blur_radius < 1 or feather < 0:
            raise HistoryFault("VALIDATION", "Invalid blur dimensions or parameters", 422)

        operation_id = input["_history_operation_id"]
        paths = [f"panels/{panel.crop_filename}", f"panels/.originals/{panel.crop_filename}"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)
        return {
            "panel_id": panel.id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "blur_radius": blur_radius,
            "feather": feather,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"panel_id", "x", "y", "width", "height", "blur_radius", "feather", "operation_id"}
            and isinstance(payload["panel_id"], str)
            and isinstance(payload["operation_id"], str)
            and all(type(payload[k]) is int for k in ("x", "y", "width", "height", "blur_radius", "feather"))
            and payload["width"] > 0 and payload["height"] > 0 and payload["x"] >= 0 and payload["y"] >= 0
            and payload["blur_radius"] >= 1 and payload["feather"] >= 0
        )

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        panel = db.query(PanelRecord).filter(PanelRecord.id == payload["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
        crop = project_path(project.workspace_path, "panels", panel.crop_filename)
        if not forward:
            panel.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")
            return
        panel.manually_modified = True
        panel.updated_at = utc_now()
        db.flush()
        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            return
        success = blur_image_box(crop, payload["x"], payload["y"], payload["width"], payload["height"],
                                blur_radius=payload["blur_radius"], feather=payload["feather"], backup=True)
        if not success:
            raise HistoryFault("VALIDATION", "Failed to blur image box", 422)
        store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelBlurTextStrategy:
    """Blur text regions in a panel crop and mark regions REDACTED."""
    _region_fields = ("status", "region_type", "corrected_text", "correction_status")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel and history operation are required", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        crop = project_path(project.workspace_path, "panels", panel.crop_filename)
        if not crop.is_file():
            raise HistoryFault("NOT_FOUND", "Panel crop file is missing", 404)

        query = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id, TextRegionRecord.project_id == project.id)
        region_ids = input.get("region_ids")
        if region_ids is not None:
            if not isinstance(region_ids, list) or not all(isinstance(rid, str) for rid in region_ids):
                raise HistoryFault("VALIDATION", "region_ids must be a list of strings", 422)
            query = query.filter(TextRegionRecord.id.in_(region_ids))
        regions = query.all()
        if not regions:
            raise HistoryFault("VALIDATION", "No text regions found to blur", 422)

        blur_radius = input.get("blur_radius", 24)
        feather = input.get("feather", 4)
        if not (type(blur_radius) is int and blur_radius >= 1 and type(feather) is int and feather >= 0):
            raise HistoryFault("VALIDATION", "Invalid blur parameters", 422)

        operation_id = input["_history_operation_id"]
        paths = [f"panels/{panel.crop_filename}", f"panels/.originals/{panel.crop_filename}"]
        for tr in regions:
            if tr.crop_filename:
                paths.extend([f"text_regions/{tr.crop_filename}", f"text_regions/.originals/{tr.crop_filename}"])

        RetainedAssetStore(project.workspace_path).capture_before(operation_id, list(dict.fromkeys(paths)))
        regions_payload = [
            {
                "id": tr.id,
                "x": tr.x,
                "y": tr.y,
                "width": tr.width,
                "height": tr.height,
                "crop_filename": tr.crop_filename,
                "before": {field: getattr(tr, field) for field in self._region_fields},
            }
            for tr in regions
        ]
        return {
            "panel_id": panel.id,
            "regions": regions_payload,
            "blur_radius": blur_radius,
            "feather": feather,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"panel_id", "regions", "blur_radius", "feather", "operation_id"}
            and isinstance(payload["panel_id"], str)
            and isinstance(payload["operation_id"], str)
            and type(payload["blur_radius"]) is int and type(payload["feather"]) is int
            and isinstance(payload["regions"], list)
            and all(isinstance(item, dict) and isinstance(item.get("id"), str)
                    and set(item.get("before", {})) == set(self._region_fields)
                    and all(type(item.get(k)) is int for k in ("x", "y", "width", "height"))
                    for item in payload["regions"])
        )

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        panel = db.query(PanelRecord).filter(PanelRecord.id == payload["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
        crop = project_path(project.workspace_path, "panels", panel.crop_filename)

        if not forward:
            for item in payload["regions"]:
                region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
                if region is None:
                    raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
                for field, value in item["before"].items():
                    setattr(region, field, value)
                region.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")
            return

        for item in payload["regions"]:
            region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
            if region is None:
                raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
            region.status = "BLURRED"
            region.region_type = "REDACTED"
            region.corrected_text = "[BLURRED / REDACTED]"
            region.correction_status = "VERIFIED"
            region.updated_at = utc_now()
        panel.manually_modified = True
        panel.updated_at = utc_now()
        db.flush()

        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            return

        for item in payload["regions"]:
            blur_image_box(crop, item["x"], item["y"], item["width"], item["height"],
                           blur_radius=payload["blur_radius"], feather=payload["feather"], backup=True)
            if item["crop_filename"]:
                reg_thumb = project_path(project.workspace_path, "text_regions", item["crop_filename"])
                if reg_thumb.exists():
                    blur_entire_image(reg_thumb, blur_radius=payload["blur_radius"], backup=True)

        store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelBlurEntireStrategy:
    """Blur an entire panel image and redact all contained text regions."""
    _region_fields = ("status", "region_type", "corrected_text", "correction_status")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("panel_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Panel and history operation are required", 422)
        panel = db.query(PanelRecord).filter(PanelRecord.id == input["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("NOT_FOUND", "Panel not found", 404)
        crop = project_path(project.workspace_path, "panels", panel.crop_filename)
        if not crop.is_file():
            raise HistoryFault("NOT_FOUND", "Panel crop file is missing", 404)

        blur_radius = input.get("blur_radius", 32)
        if not (type(blur_radius) is int and blur_radius >= 1):
            raise HistoryFault("VALIDATION", "Invalid blur radius", 422)

        regions = db.query(TextRegionRecord).filter(TextRegionRecord.panel_id == panel.id, TextRegionRecord.project_id == project.id).all()
        operation_id = input["_history_operation_id"]
        paths = [f"panels/{panel.crop_filename}", f"panels/.originals/{panel.crop_filename}"]
        for tr in regions:
            if tr.crop_filename:
                paths.extend([f"text_regions/{tr.crop_filename}", f"text_regions/.originals/{tr.crop_filename}"])

        RetainedAssetStore(project.workspace_path).capture_before(operation_id, list(dict.fromkeys(paths)))
        regions_payload = [
            {
                "id": tr.id,
                "crop_filename": tr.crop_filename,
                "before": {field: getattr(tr, field) for field in self._region_fields},
            }
            for tr in regions
        ]
        return {
            "panel_id": panel.id,
            "regions": regions_payload,
            "blur_radius": blur_radius,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"panel_id", "regions", "blur_radius", "operation_id"}
            and isinstance(payload["panel_id"], str)
            and isinstance(payload["operation_id"], str)
            and type(payload["blur_radius"]) is int
            and isinstance(payload["regions"], list)
            and all(isinstance(item, dict) and isinstance(item.get("id"), str)
                    and set(item.get("before", {})) == set(self._region_fields)
                    for item in payload["regions"])
        )

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        panel = db.query(PanelRecord).filter(PanelRecord.id == payload["panel_id"], PanelRecord.project_id == project.id).first()
        if panel is None:
            raise HistoryFault("CONFLICT", "Panel was removed outside history", 409)
        crop = project_path(project.workspace_path, "panels", panel.crop_filename)

        if not forward:
            for item in payload["regions"]:
                region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
                if region is None:
                    raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
                for field, value in item["before"].items():
                    setattr(region, field, value)
                region.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")
            return

        for item in payload["regions"]:
            region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
            if region is None:
                raise HistoryFault("CONFLICT", "Text region was removed outside history", 409)
            region.status = "BLURRED"
            region.region_type = "REDACTED"
            region.corrected_text = "[BLURRED / REDACTED]"
            region.correction_status = "VERIFIED"
            region.updated_at = utc_now()
        panel.manually_modified = True
        panel.updated_at = utc_now()
        db.flush()

        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            return

        blur_entire_image(crop, blur_radius=payload["blur_radius"], backup=True)
        for item in payload["regions"]:
            if item["crop_filename"]:
                reg_thumb = project_path(project.workspace_path, "text_regions", item["crop_filename"])
                if reg_thumb.exists():
                    blur_entire_image(reg_thumb, blur_radius=payload["blur_radius"], backup=True)

        store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelBatchBlurStrategy:
    """Batch blur multiple panels according to preset."""
    _region_fields = ("status", "region_type", "corrected_text", "correction_status")
    _valid_presets = {"TOP_WATERMARK", "BOTTOM_SUBSCRIBE", "ENTIRE_PANEL", "ALL_TEXT_REGIONS"}

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        preset = input.get("preset", "TOP_WATERMARK")
        if preset not in self._valid_presets:
            raise HistoryFault("VALIDATION", f"Invalid preset: {preset}", 422)

        height_px = input.get("height_px", 80)
        blur_radius = input.get("blur_radius", 24)
        feather = input.get("feather", 6)
        if not all(type(v) is int for v in (height_px, blur_radius, feather)):
            raise HistoryFault("VALIDATION", "Batch blur numeric params must be integers", 422)

        query = db.query(PanelRecord).filter(PanelRecord.project_id == project.id)
        panel_ids = input.get("panel_ids")
        if panel_ids is not None:
            if not isinstance(panel_ids, list) or not all(isinstance(pid, str) for pid in panel_ids):
                raise HistoryFault("VALIDATION", "panel_ids must be a list of strings", 422)
            query = query.filter(PanelRecord.id.in_(panel_ids))
        panels = query.all()
        if not panels:
            raise HistoryFault("VALIDATION", "No panels found for batch blur", 422)

        paths = []
        target_panel_ids = [p.id for p in panels]
        for panel in panels:
            if panel.crop_filename:
                paths.extend([f"panels/{panel.crop_filename}", f"panels/.originals/{panel.crop_filename}"])

        regions = []
        if preset in {"ENTIRE_PANEL", "ALL_TEXT_REGIONS"}:
            reg_records = db.query(TextRegionRecord).filter(
                TextRegionRecord.project_id == project.id,
                TextRegionRecord.panel_id.in_(target_panel_ids),
            ).all()
            for tr in reg_records:
                if tr.crop_filename:
                    paths.extend([f"text_regions/{tr.crop_filename}", f"text_regions/.originals/{tr.crop_filename}"])
                regions.append({
                    "id": tr.id,
                    "panel_id": tr.panel_id,
                    "x": tr.x,
                    "y": tr.y,
                    "width": tr.width,
                    "height": tr.height,
                    "crop_filename": tr.crop_filename,
                    "before": {field: getattr(tr, field) for field in self._region_fields},
                })

        operation_id = input["_history_operation_id"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, list(dict.fromkeys(paths)))
        return {
            "preset": preset,
            "height_px": height_px,
            "blur_radius": blur_radius,
            "feather": feather,
            "panel_ids": target_panel_ids,
            "regions": regions,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"preset", "height_px", "blur_radius", "feather", "panel_ids", "regions", "operation_id"}
            and payload["preset"] in self._valid_presets
            and all(type(payload[k]) is int for k in ("height_px", "blur_radius", "feather"))
            and isinstance(payload["panel_ids"], list)
            and isinstance(payload["regions"], list)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        panels = db.query(PanelRecord).filter(PanelRecord.id.in_(payload["panel_ids"]), PanelRecord.project_id == project.id).all()

        if not forward:
            for item in payload["regions"]:
                region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
                if region:
                    for field, value in item["before"].items():
                        setattr(region, field, value)
                    region.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")
            return

        preset = payload["preset"]
        height_px = payload["height_px"]
        blur_radius = payload["blur_radius"]
        feather = payload["feather"]

        for item in payload["regions"]:
            region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
            if region:
                region.status = "BLURRED"
                region.region_type = "REDACTED"
                region.corrected_text = "[BLURRED / REDACTED]"
                region.correction_status = "VERIFIED"
                region.updated_at = utc_now()

        for panel in panels:
            panel.manually_modified = True
            panel.updated_at = utc_now()
        db.flush()

        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            return

        for panel in panels:
            if not panel.crop_filename:
                continue
            crop_path = project_path(project.workspace_path, "panels", panel.crop_filename)
            if not crop_path.is_file():
                continue
            pw = panel.width or 1200
            ph = panel.height or 800

            if preset == "TOP_WATERMARK":
                h = min(height_px, max(20, int(ph * 0.25)))
                blur_image_box(crop_path, 0, 0, pw, h, blur_radius=blur_radius, feather=feather, backup=True)
            elif preset == "BOTTOM_SUBSCRIBE":
                h = min(height_px, max(20, int(ph * 0.25)))
                y = max(0, ph - h)
                blur_image_box(crop_path, 0, y, pw, h, blur_radius=blur_radius, feather=feather, backup=True)
            elif preset == "ENTIRE_PANEL":
                blur_entire_image(crop_path, blur_radius=blur_radius, backup=True)
            elif preset == "ALL_TEXT_REGIONS":
                panel_regions = [r for r in payload["regions"] if r["panel_id"] == panel.id]
                for tr in panel_regions:
                    blur_image_box(crop_path, tr["x"], tr["y"], tr["width"], tr["height"], blur_radius=blur_radius, feather=feather, backup=True)
                    if tr["crop_filename"]:
                        reg_thumb = project_path(project.workspace_path, "text_regions", tr["crop_filename"])
                        if reg_thumb.exists():
                            blur_entire_image(reg_thumb, blur_radius=blur_radius, backup=True)

        store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PanelBatchResetStrategy:
    """Batch reset image modifications across panels."""
    _region_fields = ("status", "region_type", "corrected_text", "correction_status")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        query = db.query(PanelRecord).filter(PanelRecord.project_id == project.id)
        panel_ids = input.get("panel_ids")
        if panel_ids is not None:
            if not isinstance(panel_ids, list) or not all(isinstance(pid, str) for pid in panel_ids):
                raise HistoryFault("VALIDATION", "panel_ids must be a list of strings", 422)
            query = query.filter(PanelRecord.id.in_(panel_ids))
        panels = query.all()
        if not panels:
            raise HistoryFault("VALIDATION", "No panels found for batch reset", 422)

        paths = []
        target_panel_ids = [p.id for p in panels]
        for panel in panels:
            if panel.crop_filename:
                paths.extend([f"panels/{panel.crop_filename}", f"panels/.originals/{panel.crop_filename}"])

        blurred_regions = db.query(TextRegionRecord).filter(
            TextRegionRecord.project_id == project.id,
            TextRegionRecord.panel_id.in_(target_panel_ids),
            TextRegionRecord.status == "BLURRED",
        ).all()
        for tr in blurred_regions:
            if tr.crop_filename:
                paths.extend([f"text_regions/{tr.crop_filename}", f"text_regions/.originals/{tr.crop_filename}"])

        operation_id = input["_history_operation_id"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, list(dict.fromkeys(paths)))
        regions_payload = [
            {
                "id": tr.id,
                "crop_filename": tr.crop_filename,
                "before": {field: getattr(tr, field) for field in self._region_fields},
            }
            for tr in blurred_regions
        ]
        return {
            "panel_ids": target_panel_ids,
            "regions": regions_payload,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"panel_ids", "regions", "operation_id"}
            and isinstance(payload["panel_ids"], list)
            and isinstance(payload["regions"], list)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        panels = db.query(PanelRecord).filter(PanelRecord.id.in_(payload["panel_ids"]), PanelRecord.project_id == project.id).all()

        if not forward:
            for item in payload["regions"]:
                region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
                if region:
                    for field, value in item["before"].items():
                        setattr(region, field, value)
                    region.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")
            return

        for item in payload["regions"]:
            region = db.query(TextRegionRecord).filter(TextRegionRecord.id == item["id"], TextRegionRecord.project_id == project.id).first()
            if region:
                region.status = "CONFIRMED"
                region.region_type = "SPEECH"
                region.corrected_text = region.raw_text or ""
                region.correction_status = "UNEDITED"
                region.updated_at = utc_now()
        db.flush()

        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            return

        for panel in panels:
            if panel.crop_filename:
                crop_path = project_path(project.workspace_path, "panels", panel.crop_filename)
                restore_image_backup(crop_path, delete_backup=True)

        for item in payload["regions"]:
            if item["crop_filename"]:
                reg_thumb = project_path(project.workspace_path, "text_regions", item["crop_filename"])
                restore_image_backup(reg_thumb, delete_backup=True)

        store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")

