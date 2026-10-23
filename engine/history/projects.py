"""History strategies for project lifecycle mutations."""
from __future__ import annotations

from engine.acquisition.models import PipelineStage
from engine.database.models import PageRecord, utc_now
from engine.history.assets import RetainedAssetStore
from engine.history.contracts import HistoryFault
from engine.projects.service import project_service


class ProjectConfirmStrategy:
    """Transition project to PipelineStage.ACQUIRED, retaining project.json and manifest.json."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)

        ready_count = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project.id, PageRecord.status == "READY")
            .count()
        )
        if ready_count == 0:
            raise HistoryFault("VALIDATION", "Cannot confirm acquisition with zero ready pages", 422)

        operation_id = input["_history_operation_id"]
        paths = ["project.json", "manifest.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "before_stage": project.current_stage,
            "after_stage": PipelineStage.ACQUIRED.value,
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
                project_service.sync_manifest_with_db(db, project.id)
                store.capture_after(payload["operation_id"])
        else:
            project.current_stage = payload["before_stage"]
            project.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")
