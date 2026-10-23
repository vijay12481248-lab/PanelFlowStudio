"""Reversible history strategies for the motion domain."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from engine.acquisition.models import PipelineStage
from engine.database.models import VisualTimelineRecord
from engine.history.assets import RetainedAssetStore
from engine.history.contracts import CommandStrategy, HistoryFault


class MotionPlanAcceptStrategy(CommandStrategy):
    """Accept an AI-generated or user-configured motion plan."""

    def prepare(self, db, project, input: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        plan = input.get("plan")
        if not isinstance(plan, dict):
            raise HistoryFault("VALIDATION", "Motion plan is required", 422)

        operation_id = input["_history_operation_id"]
        paths = ["motion/visual_timeline.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        rec = db.query(VisualTimelineRecord).filter_by(project_id=project.id).first()
        before_record = None
        if rec is not None:
            before_record = {
                "status": rec.status,
                "total_duration": rec.total_duration,
                "total_shots": rec.total_shots,
                "style_preset": rec.style_preset,
                "timeline_json": deepcopy(rec.timeline_json or {}),
                "overrides_json": deepcopy(rec.overrides_json or {}),
            }

        return {
            "operation_id": operation_id,
            "plan": plan,
            "before_record": before_record,
        }

    def validate(self, payload: dict[str, Any]) -> bool:
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("operation_id"), str)
            and isinstance(payload.get("plan"), dict)
        )

    def apply(self, db, project, payload: dict[str, Any], *, forward: bool) -> None:
        store = RetainedAssetStore(project.workspace_path)
        op_id = payload["operation_id"]
        rec = db.query(VisualTimelineRecord).filter_by(project_id=project.id).first()

        if forward:
            plan = payload["plan"]
            total_duration = float(plan.get("total_duration", 0.0))
            total_shots = int(plan.get("total_shots", len(plan.get("shots", []))))
            style_preset = str(plan.get("style_preset", "cinematic"))

            if rec is None:
                rec = VisualTimelineRecord(
                    project_id=project.id,
                    status="DRAFT",
                    total_duration=total_duration,
                    total_shots=total_shots,
                    style_preset=style_preset,
                    timeline_json=plan,
                    overrides_json={},
                )
                db.add(rec)
            else:
                rec.status = "DRAFT"
                rec.total_duration = total_duration
                rec.total_shots = total_shots
                rec.style_preset = style_preset
                rec.timeline_json = deepcopy(plan)
                rec.overrides_json = {}
            db.flush()

            if store.is_complete(op_id):
                store.restore(op_id, "after")
            else:
                timeline_file = Path(project.workspace_path) / "motion" / "visual_timeline.json"
                timeline_file.parent.mkdir(parents=True, exist_ok=True)
                file_data = deepcopy(plan)
                file_data["status"] = "DRAFT"
                file_data["total_duration"] = total_duration
                file_data["overrides"] = {}
                timeline_file.write_text(json.dumps(file_data, indent=2), encoding="utf-8")
                store.capture_after(op_id)
        else:
            before = payload.get("before_record")
            if before is None:
                if rec is not None:
                    db.delete(rec)
            else:
                if rec is None:
                    rec = VisualTimelineRecord(project_id=project.id)
                    db.add(rec)
                rec.status = before["status"]
                rec.total_duration = before["total_duration"]
                rec.total_shots = before["total_shots"]
                rec.style_preset = before["style_preset"]
                rec.timeline_json = deepcopy(before["timeline_json"])
                rec.overrides_json = deepcopy(before["overrides_json"])
            db.flush()
            store.restore(op_id, "before")

    def compensate(self, project, payload: dict[str, Any], *, forward: bool) -> None:
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class MotionOverridesStrategy(CommandStrategy):
    """Apply or revert per-shot motion overrides."""

    def prepare(self, db, project, input: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        overrides = input.get("overrides")
        if not isinstance(overrides, dict):
            raise HistoryFault("VALIDATION", "Overrides dict is required", 422)

        rec = db.query(VisualTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Visual timeline record not found", 404)

        operation_id = input["_history_operation_id"]
        paths = ["motion/visual_timeline.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        before_overrides = deepcopy(rec.overrides_json or {})
        after_overrides = deepcopy(before_overrides)
        after_overrides.update(overrides)

        return {
            "operation_id": operation_id,
            "before_overrides": before_overrides,
            "after_overrides": after_overrides,
        }

    def validate(self, payload: dict[str, Any]) -> bool:
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("operation_id"), str)
            and isinstance(payload.get("before_overrides"), dict)
            and isinstance(payload.get("after_overrides"), dict)
        )

    def apply(self, db, project, payload: dict[str, Any], *, forward: bool) -> None:
        store = RetainedAssetStore(project.workspace_path)
        op_id = payload["operation_id"]
        rec = db.query(VisualTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Visual timeline record not found", 404)

        if forward:
            rec.overrides_json = deepcopy(payload["after_overrides"])
            db.flush()
            if store.is_complete(op_id):
                store.restore(op_id, "after")
            else:
                timeline_file = Path(project.workspace_path) / "motion" / "visual_timeline.json"
                if timeline_file.exists():
                    data = json.loads(timeline_file.read_text(encoding="utf-8"))
                    data["overrides"] = deepcopy(payload["after_overrides"])
                    timeline_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                store.capture_after(op_id)
        else:
            rec.overrides_json = deepcopy(payload["before_overrides"])
            db.flush()
            store.restore(op_id, "before")

    def compensate(self, project, payload: dict[str, Any], *, forward: bool) -> None:
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class MotionApproveStrategy(CommandStrategy):
    """Approve visual motion timeline and advance project pipeline stage."""

    def prepare(self, db, project, input: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)

        rec = db.query(VisualTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Visual timeline record not found", 404)

        operation_id = input["_history_operation_id"]
        paths = ["motion/visual_timeline.json"]
        project_file = Path(project.workspace_path) / "project.json"
        if project_file.exists():
            paths.append("project.json")
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "operation_id": operation_id,
            "before_status": rec.status,
            "after_status": "APPROVED",
            "before_stage": project.current_stage,
            "after_stage": PipelineStage.MOTION_APPROVED.value,
        }

    def validate(self, payload: dict[str, Any]) -> bool:
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("operation_id"), str)
            and isinstance(payload.get("before_status"), str)
            and isinstance(payload.get("after_status"), str)
            and isinstance(payload.get("before_stage"), str)
            and isinstance(payload.get("after_stage"), str)
        )

    def apply(self, db, project, payload: dict[str, Any], *, forward: bool) -> None:
        store = RetainedAssetStore(project.workspace_path)
        op_id = payload["operation_id"]
        rec = db.query(VisualTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Visual timeline record not found", 404)

        if forward:
            rec.status = payload["after_status"]
            project.current_stage = payload["after_stage"]
            db.flush()
            if store.is_complete(op_id):
                store.restore(op_id, "after")
            else:
                timeline_file = Path(project.workspace_path) / "motion" / "visual_timeline.json"
                if timeline_file.exists():
                    data = json.loads(timeline_file.read_text(encoding="utf-8"))
                    data["status"] = payload["after_status"]
                    timeline_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                store.capture_after(op_id)
        else:
            rec.status = payload["before_status"]
            project.current_stage = payload["before_stage"]
            db.flush()
            store.restore(op_id, "before")

    def compensate(self, project, payload: dict[str, Any], *, forward: bool) -> None:
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")
