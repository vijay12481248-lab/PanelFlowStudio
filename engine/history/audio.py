"""Reversible history strategies for the audio domain."""
from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from engine.acquisition.models import PipelineStage
from engine.database.models import AudioTimelineRecord
from engine.history.assets import RetainedAssetStore
from engine.history.contracts import CommandStrategy, HistoryFault


class AudioDraftAcceptStrategy(CommandStrategy):
    """Accept an audio draft timeline and track master audio timeline assets."""

    def prepare(self, db, project, input: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        draft = input.get("draft")
        if not isinstance(draft, dict):
            raise HistoryFault("VALIDATION", "Audio draft is required", 422)

        operation_id = input["_history_operation_id"]
        paths = ["audio/master_audio_timeline.json"]
        audio_dir = Path(project.workspace_path) / "audio"
        if audio_dir.exists():
            for wav in audio_dir.glob("*.wav"):
                paths.append(wav.relative_to(project.workspace_path).as_posix())

        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        rec = db.query(AudioTimelineRecord).filter_by(project_id=project.id).first()
        before_record = None
        if rec is not None:
            before_record = {
                "status": rec.status,
                "total_duration": rec.total_duration,
                "timeline_json": deepcopy(rec.timeline_json or {}),
                "voice_casting": deepcopy(rec.voice_casting or {}),
            }

        return {
            "operation_id": operation_id,
            "draft": draft,
            "before_record": before_record,
        }

    def validate(self, payload: dict[str, Any]) -> bool:
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("operation_id"), str)
            and isinstance(payload.get("draft"), dict)
        )

    def apply(self, db, project, payload: dict[str, Any], *, forward: bool) -> None:
        store = RetainedAssetStore(project.workspace_path)
        op_id = payload["operation_id"]
        rec = db.query(AudioTimelineRecord).filter_by(project_id=project.id).first()

        if forward:
            draft = payload["draft"]
            total_duration = float(draft.get("total_duration", 0.0))
            if rec is None:
                rec = AudioTimelineRecord(
                    project_id=project.id,
                    status="DRAFT",
                    total_duration=total_duration,
                    timeline_json=draft,
                )
                db.add(rec)
            else:
                rec.status = "DRAFT"
                rec.total_duration = total_duration
                rec.timeline_json = deepcopy(draft)
            db.flush()

            if store.is_complete(op_id):
                store.restore(op_id, "after")
            else:
                timeline_file = Path(project.workspace_path) / "audio" / "master_audio_timeline.json"
                timeline_file.parent.mkdir(parents=True, exist_ok=True)
                file_data = deepcopy(draft)
                file_data["status"] = "DRAFT"
                file_data["total_duration"] = total_duration
                timeline_file.write_text(json.dumps(file_data, indent=2), encoding="utf-8")
                store.capture_after(op_id)
        else:
            before = payload.get("before_record")
            if before is None:
                if rec is not None:
                    db.delete(rec)
            else:
                if rec is None:
                    rec = AudioTimelineRecord(project_id=project.id)
                    db.add(rec)
                rec.status = before["status"]
                rec.total_duration = before["total_duration"]
                rec.timeline_json = deepcopy(before["timeline_json"])
            db.flush()
            store.restore(op_id, "before")

    def compensate(self, project, payload: dict[str, Any], *, forward: bool) -> None:
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class AudioSynthesizedAcceptStrategy(CommandStrategy):
    """Accept synthesized audio clips, update audio timeline intervals and retain clips."""

    def prepare(self, db, project, input: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        result = input.get("result")
        if not isinstance(result, dict):
            raise HistoryFault("VALIDATION", "Synthesized audio result is required", 422)

        rec = db.query(AudioTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Audio timeline record not found", 404)

        operation_id = input["_history_operation_id"]
        store = RetainedAssetStore(project.workspace_path)
        paths = ["audio/master_audio_timeline.json"]
        audio_files = result.get("audio_files", [])
        for f in audio_files:
            clean = Path(f).as_posix()
            if clean not in paths:
                paths.append(clean)

        store.capture_before(operation_id, paths)

        # If caller mutated audio_files before executing command, find pre-mutation versions in previous store operations
        op_dir = store.root / operation_id
        for f in audio_files:
            clean = Path(f).as_posix()
            for prev_op in sorted(store.root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                if prev_op.name == operation_id or not prev_op.is_dir():
                    continue
                prev_file = prev_op / "after" / clean
                if not prev_file.exists():
                    prev_file = prev_op / "before" / clean
                if prev_file.exists():
                    dest = op_dir / "before" / clean
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(prev_file, dest)
                    break

        before_record = {
            "status": rec.status,
            "total_duration": rec.total_duration,
            "timeline_json": deepcopy(rec.timeline_json or {}),
        }

        return {
            "operation_id": operation_id,
            "result": result,
            "before_record": before_record,
        }

    def validate(self, payload: dict[str, Any]) -> bool:
        return (
            isinstance(payload, dict)
            and isinstance(payload.get("operation_id"), str)
            and isinstance(payload.get("result"), dict)
            and isinstance(payload.get("before_record"), dict)
        )

    def apply(self, db, project, payload: dict[str, Any], *, forward: bool) -> None:
        store = RetainedAssetStore(project.workspace_path)
        op_id = payload["operation_id"]
        rec = db.query(AudioTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Audio timeline record not found", 404)

        if forward:
            result = payload["result"]
            rec.total_duration = float(result.get("total_duration", rec.total_duration))
            tl = deepcopy(rec.timeline_json or {})
            if "intervals" in result:
                tl["intervals"] = deepcopy(result["intervals"])
            if "audio_files" in result:
                tl["audio_files"] = deepcopy(result["audio_files"])
            rec.timeline_json = tl
            db.flush()

            if store.is_complete(op_id):
                store.restore(op_id, "after")
            else:
                timeline_file = Path(project.workspace_path) / "audio" / "master_audio_timeline.json"
                if timeline_file.exists():
                    data = json.loads(timeline_file.read_text(encoding="utf-8"))
                    data["total_duration"] = rec.total_duration
                    data["intervals"] = tl.get("intervals", [])
                    data["audio_files"] = tl.get("audio_files", [])
                    timeline_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                store.capture_after(op_id)
        else:
            before = payload["before_record"]
            rec.status = before["status"]
            rec.total_duration = before["total_duration"]
            rec.timeline_json = deepcopy(before["timeline_json"])
            db.flush()
            store.restore(op_id, "before")

    def compensate(self, project, payload: dict[str, Any], *, forward: bool) -> None:
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class AudioApproveStrategy(CommandStrategy):
    """Approve master audio timeline and advance project pipeline stage."""

    def prepare(self, db, project, input: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)

        rec = db.query(AudioTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Audio timeline record not found", 404)

        operation_id = input["_history_operation_id"]
        paths = ["audio/master_audio_timeline.json"]
        project_file = Path(project.workspace_path) / "project.json"
        if project_file.exists():
            paths.append("project.json")
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "operation_id": operation_id,
            "before_status": rec.status,
            "after_status": "APPROVED",
            "before_stage": project.current_stage,
            "after_stage": PipelineStage.AUDIO_APPROVED.value,
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
        rec = db.query(AudioTimelineRecord).filter_by(project_id=project.id).first()
        if rec is None:
            raise HistoryFault("NOT_FOUND", "Audio timeline record not found", 404)

        if forward:
            rec.status = payload["after_status"]
            project.current_stage = payload["after_stage"]
            db.flush()
            if store.is_complete(op_id):
                store.restore(op_id, "after")
            else:
                timeline_file = Path(project.workspace_path) / "audio" / "master_audio_timeline.json"
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
