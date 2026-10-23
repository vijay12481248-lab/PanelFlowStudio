"""History strategies for reversible page mutations."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from engine.database.models import (
    NormalizationRecord,
    OCRRecord,
    PageRecord,
    PanelRecord,
    TextRegionRecord,
    utc_now,
)
from engine.history.assets import RetainedAssetStore
from engine.history.contracts import HistoryFault
from engine.projects.service import project_service
from engine.security.paths import project_path


def _row_data(row):
    """JSON-safe persistent columns; audit timestamps are regenerated on restore."""
    return {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name not in {"created_at", "updated_at"}
    }


class PageReorderStrategy:
    """Reorder pages within a project."""

    def prepare(self, db, project, input):
        page_ids = input.get("page_ids") if isinstance(input, dict) else None
        operation_id = input.get("_history_operation_id") if isinstance(input, dict) else None
        if (not isinstance(page_ids, list) or not all(isinstance(pid, str) for pid in page_ids)
                or not isinstance(operation_id, str)):
            raise HistoryFault("VALIDATION", "Page order and history operation are required", 422)

        pages = db.query(PageRecord).filter(PageRecord.project_id == project.id).order_by(PageRecord.sequence).all()
        before = [p.id for p in pages]
        if len(page_ids) != len(before) or set(page_ids) != set(before):
            raise HistoryFault("VALIDATION", "Page order must contain every project page exactly once", 422)
        if page_ids == before:
            return None

        paths = ["manifest.json"]
        if project_path(project.workspace_path, "panels", "panels.json").is_file():
            paths.append("panels/panels.json")

        store = RetainedAssetStore(project.workspace_path)
        store.capture_before(operation_id, paths)
        return {"before": before, "after": list(page_ids), "operation_id": operation_id}

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"before", "after", "operation_id"}
            and isinstance(payload["operation_id"], str)
            and all(isinstance(pid, str) for pid in payload["before"])
            and all(isinstance(pid, str) for pid in payload["after"])
            and len(payload["before"]) == len(payload["after"])
            and set(payload["before"]) == set(payload["after"])
        )

    def apply(self, db, project, payload, *, forward):
        order = payload["after" if forward else "before"]
        pages = db.query(PageRecord).filter(PageRecord.project_id == project.id).all()
        page_map = {p.id: p for p in pages}
        if set(page_map) != set(order):
            raise HistoryFault("CONFLICT", "Page inventory changed outside history", 409)

        for sequence, page_id in enumerate(order, start=1):
            page_map[page_id].sequence = sequence

        from engine.history.panels import _resequence_without_commit
        _resequence_without_commit(db, project.id)
        db.flush()

        store = RetainedAssetStore(project.workspace_path)
        if forward:
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                project_service.sync_manifest_with_db(db, project.id)
                project_service._sync_panels_json(db, project.id)
                store.capture_after(payload["operation_id"])
        else:
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PageRotateStrategy:
    """Rotate a page image in-place and update its dimensions and hash."""
    _meta_fields = ("width", "height", "sha256", "byte_size")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("page_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Page and history operation are required", 422)
        degrees = input.get("degrees", 90)
        if degrees not in (90, 180, 270, -90, -180, -270):
            raise HistoryFault("VALIDATION", f"Unsupported rotation degrees: {degrees}", 422)

        page = db.query(PageRecord).filter(PageRecord.id == input["page_id"], PageRecord.project_id == project.id).first()
        if page is None:
            raise HistoryFault("NOT_FOUND", "Page not found", 404)

        source_path = project_path(project.workspace_path, "source", page.filename)
        if not source_path.is_file():
            raise HistoryFault("NOT_FOUND", "Page source file missing", 404)

        paths = [f"source/{page.filename}", "manifest.json"]
        norm_path = project_path(project.workspace_path, "normalized", page.filename)
        if norm_path.is_file():
            paths.append(f"normalized/{page.filename}")

        operation_id = input["_history_operation_id"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)
        before = {field: getattr(page, field) for field in self._meta_fields}
        return {
            "page_id": page.id,
            "degrees": degrees,
            "before": before,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"page_id", "degrees", "before", "operation_id"}
            and isinstance(payload["page_id"], str)
            and payload["degrees"] in (90, 180, 270, -90, -180, -270)
            and isinstance(payload["before"], dict)
            and set(payload["before"]) == set(self._meta_fields)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        page = db.query(PageRecord).filter(PageRecord.id == payload["page_id"], PageRecord.project_id == project.id).first()
        if page is None:
            raise HistoryFault("CONFLICT", "Page was removed outside history", 409)

        store = RetainedAssetStore(project.workspace_path)
        if not forward:
            for field, value in payload["before"].items():
                setattr(page, field, value)
            db.flush()
            store.restore(payload["operation_id"], "before")
            return

        if store.is_complete(payload["operation_id"]):
            store.restore(payload["operation_id"], "after")
            source_path = project_path(project.workspace_path, "source", page.filename)
            from engine.acquisition.downloader.validation import validate_image_bytes
            from engine.security.paths import read_contained_bytes
            data = read_contained_bytes(project.workspace_path, source_path)
            meta = validate_image_bytes(data, page.filename)
            page.width, page.height, page.sha256, page.byte_size = meta["width"], meta["height"], meta["sha256"], meta["byte_size"]
            db.flush()
            return

        from engine.acquisition.downloader.validation import rotate_image_file
        source_path = project_path(project.workspace_path, "source", page.filename)
        meta = rotate_image_file(source_path, payload["degrees"])
        page.width, page.height, page.sha256, page.byte_size = meta["width"], meta["height"], meta["sha256"], meta["byte_size"]

        norm_path = project_path(project.workspace_path, "normalized", page.filename)
        if norm_path.is_file():
            rotate_image_file(norm_path, payload["degrees"])

        db.flush()
        project_service.sync_manifest_with_db(db, project.id)
        store.capture_after(payload["operation_id"])

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class PageDeleteStrategy:
    """Soft/durable deletion of a page, its files, panels, and OCR text records."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("page_id"), str) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "Page and history operation are required", 422)

        page = db.query(PageRecord).filter(PageRecord.id == input["page_id"], PageRecord.project_id == project.id).first()
        if page is None:
            raise HistoryFault("NOT_FOUND", "Page not found", 404)

        panels = db.query(PanelRecord).filter(PanelRecord.page_id == page.id).all()
        panel_ids = [p.id for p in panels]
        ocr = db.query(OCRRecord).filter(OCRRecord.panel_id.in_(panel_ids)).all() if panel_ids else []
        regions = db.query(TextRegionRecord).filter(TextRegionRecord.page_id == page.id).all()
        normalizations = db.query(NormalizationRecord).filter(NormalizationRecord.page_id == page.id).all()

        paths = [
            f"source/{page.filename}",
            "manifest.json",
            "project.json",
        ]
        norm_path = project_path(project.workspace_path, "normalized", page.filename)
        if norm_path.is_file():
            paths.append(f"normalized/{page.filename}")

        if project_path(project.workspace_path, "panels", "panels.json").is_file():
            paths.append("panels/panels.json")

        for p in panels:
            if p.crop_filename:
                paths.extend([f"panels/{p.crop_filename}", f"panels/.originals/{p.crop_filename}"])

        for r in regions:
            if r.crop_filename:
                paths.extend([f"text_regions/{r.crop_filename}", f"text_regions/.originals/{r.crop_filename}"])

        operation_id = input["_history_operation_id"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, list(dict.fromkeys(paths)))

        all_pages = db.query(PageRecord).filter(PageRecord.project_id == project.id).order_by(PageRecord.sequence).all()
        all_panels = db.query(PanelRecord).filter(PanelRecord.project_id == project.id).order_by(PanelRecord.sequence).all()

        page_data = _row_data(page)
        if isinstance(page_data.get("downloaded_at"), datetime):
            page_data["downloaded_at"] = page_data["downloaded_at"].isoformat()

        return {
            "page": page_data,
            "normalizations": [_row_data(n) for n in normalizations],
            "panels": [_row_data(p) for p in panels],
            "ocr": [_row_data(o) for o in ocr],
            "regions": [_row_data(r) for r in regions],
            "page_sequences": {p.id: p.sequence for p in all_pages},
            "panel_sequences": {p.id: [p.sequence, p.page_sequence] for p in all_panels},
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"page", "normalizations", "panels", "ocr", "regions", "page_sequences", "panel_sequences", "operation_id"}
            and isinstance(payload["page"], dict)
            and isinstance(payload["page"].get("id"), str)
            and isinstance(payload["page"].get("filename"), str)
            and isinstance(payload["normalizations"], list)
            and isinstance(payload["panels"], list)
            and isinstance(payload["ocr"], list)
            and isinstance(payload["regions"], list)
            and isinstance(payload["page_sequences"], dict)
            and isinstance(payload["panel_sequences"], dict)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        page_id = payload["page"]["id"]

        if forward:
            page = db.query(PageRecord).filter(PageRecord.id == page_id, PageRecord.project_id == project.id).first()
            if page is None:
                raise HistoryFault("CONFLICT", "Page was removed outside history", 409)

            panel_ids = [p["id"] for p in payload["panels"]]
            if panel_ids:
                db.query(OCRRecord).filter(OCRRecord.panel_id.in_(panel_ids)).delete(synchronize_session=False)
            db.query(TextRegionRecord).filter(TextRegionRecord.page_id == page_id).delete(synchronize_session=False)
            db.query(NormalizationRecord).filter(NormalizationRecord.page_id == page_id).delete(synchronize_session=False)
            db.query(PanelRecord).filter(PanelRecord.page_id == page_id).delete(synchronize_session=False)
            db.delete(page)
            db.flush()

            # Resequence remaining pages 1..N
            remaining_pages = db.query(PageRecord).filter(PageRecord.project_id == project.id).order_by(PageRecord.sequence).all()
            for seq, p in enumerate(remaining_pages, start=1):
                p.sequence = seq

            from engine.history.panels import _resequence_without_commit
            _resequence_without_commit(db, project.id)
            db.flush()

            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                from engine.security.paths import unlink_contained_file
                source_path = Path("source") / payload["page"]["filename"]
                try:
                    unlink_contained_file(project.workspace_path, source_path)
                except Exception:
                    pass
                project_service.sync_manifest_with_db(db, project.id)
                project_service._sync_panels_json(db, project.id)
                store.capture_after(payload["operation_id"])
        else:
            existing_page = db.query(PageRecord).filter(PageRecord.id == page_id).first()
            if existing_page is not None:
                raise HistoryFault("CONFLICT", "Page already exists", 409)

            page_dict = dict(payload["page"])
            if "downloaded_at" in page_dict and isinstance(page_dict["downloaded_at"], str):
                page_dict["downloaded_at"] = datetime.fromisoformat(page_dict["downloaded_at"])

            restored_page = PageRecord(**page_dict)
            db.add(restored_page)

            for pid, seq in payload["page_sequences"].items():
                p = db.query(PageRecord).filter(PageRecord.id == pid, PageRecord.project_id == project.id).first()
                if p:
                    p.sequence = seq

            for n_data in payload["normalizations"]:
                db.add(NormalizationRecord(**n_data, created_at=utc_now()))

            for p_data in payload["panels"]:
                db.add(PanelRecord(**p_data, created_at=utc_now(), updated_at=utc_now()))

            for pid, seqs in payload["panel_sequences"].items():
                panel = db.query(PanelRecord).filter(PanelRecord.id == pid, PanelRecord.project_id == project.id).first()
                if panel:
                    panel.sequence, panel.page_sequence = seqs

            for o_data in payload["ocr"]:
                db.add(OCRRecord(**o_data, created_at=utc_now(), updated_at=utc_now()))

            for r_data in payload["regions"]:
                db.add(TextRegionRecord(**r_data, created_at=utc_now(), updated_at=utc_now()))

            db.flush()
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")
