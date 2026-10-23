"""History strategies for reversible Story, Character, Scene, Script, and Storyboard mutations."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from engine.acquisition.models import PipelineStage
from engine.database.models import (
    AssetRecord,
    AudioTimelineRecord,
    CharacterRecord,
    EventRecord,
    NarrativeRecord,
    ProjectRecord,
    RenderJobRecord,
    SceneRecord,
    ScriptSegmentRecord,
    StoryBeatRecord,
    TextRegionRecord,
    VideoScriptRecord,
    VisualTimelineRecord,
    utc_now,
)
from engine.history.assets import RetainedAssetStore
from engine.history.contracts import HistoryFault
from engine.projects.service import project_service
from engine.story.alignment import StoryboardSegmentUpdate, alignment_service
from engine.story.dependency import PipelineEntityTier, dependency_graph
from engine.story.models import (
    NarrativeDocument,
    ScriptSegment,
    ScriptValidationReport,
    VideoScript,
)
from engine.story.script.validator import script_validator


def _row_data(row):
    """JSON-safe persistent columns; audit timestamps are regenerated on restore."""
    if row is None:
        return None
    data = {}
    for column in row.__table__.columns:
        if column.name in {"created_at", "updated_at"}:
            continue
        val = getattr(row, column.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        data[column.name] = val
    return data


def _get_narrative(db, project_id: str) -> Optional[NarrativeDocument]:
    rec = db.query(NarrativeRecord).filter(NarrativeRecord.project_id == project_id).first()
    if rec and rec.document:
        return NarrativeDocument.model_validate(rec.document)
    proj = db.get(ProjectRecord, project_id)
    if proj:
        nar_path = Path(proj.workspace_path) / "story" / "narrative.json"
        if nar_path.is_file():
            try:
                data = json.loads(nar_path.read_text(encoding="utf-8"))
                return NarrativeDocument.model_validate(data)
            except Exception:
                pass
    return None


def _validate_script(db, project_id: str, script_id: str) -> ScriptValidationReport:
    s_rec = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == script_id).first()
    if not s_rec:
        raise KeyError(f"Script not found: {script_id}")
    narrative = _get_narrative(db, project_id)
    if not narrative:
        raise ValueError("Cannot validate script: No Narrative IR found for project.")
    script_doc = VideoScript(
        script_id=s_rec.id,
        project_id=s_rec.project_id,
        adaptation_profile=s_rec.adaptation_profile,
        estimated_duration=s_rec.estimated_duration,
        segments=[
            ScriptSegment(
                segment_id=s.id,
                scene_id=s.scene_id,
                beat_id=s.beat_id,
                sequence=s.sequence,
                type=s.type,
                speaker_character_id=s.speaker_character_id,
                text=s.text,
                emotion=s.emotion,
                intensity=s.intensity,
                estimated_duration=s.estimated_duration,
                estimated_start=s.estimated_start,
                estimated_end=s.estimated_end,
                source_evidence=s.source_evidence or {},
                production_intent=s.production_intent or "",
                faithfulness_status=s.faithfulness_status or "SUPPORTED",
            )
            for s in sorted(s_rec.segments, key=lambda item: item.sequence)
        ],
        quality_metrics=s_rec.quality_metrics or {},
        status=s_rec.status,
    )
    return script_validator.validate(script_doc, narrative)


class StoryConfirmStrategy:
    """Transition project to PipelineStage.STORY_APPROVED, validating narrative and continuity."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)

        narrative = _get_narrative(db, project.id)
        if not narrative:
            raise HistoryFault("VALIDATION", "Cannot approve story: No Narrative IR exists for this project", 422)

        from engine.story.continuity import ContinuityAuditor
        current_warnings = [*narrative.continuity_warnings, *ContinuityAuditor().audit(narrative)]
        error_warnings = [w for w in current_warnings if w.severity == "ERROR" and not w.resolved]
        if error_warnings:
            raise HistoryFault(
                "VALIDATION",
                f"Cannot approve story: {len(error_warnings)} unresolved critical continuity errors exist",
                422,
            )

        operation_id = input["_history_operation_id"]
        paths = ["project.json"]
        if (Path(project.workspace_path) / "story" / "narrative.json").is_file():
            paths.append("story/narrative.json")
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "before_stage": project.current_stage,
            "after_stage": PipelineStage.STORY_APPROVED.value,
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
                store.capture_after(payload["operation_id"])
        else:
            project.current_stage = payload["before_stage"]
            project.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


VALID_CHANGE_STATUSES = ("NONE", "PENDING_REVIEW", "APPROVED", "REJECTED")


class CharacterUpdateStrategy:
    """Update character display name, canonical name, role, aliases, description, or status."""
    _fields = (
        "display_name", "canonical_name", "role", "aliases", "description", "status",
        "visual_traits", "reference_asset_id", "generation_params", "proposed_changes", "change_status",
    )

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        if not isinstance(input.get("character_id"), str):
            raise HistoryFault("VALIDATION", "Character ID is required", 422)

        if "change_status" in input and input["change_status"] is not None:
            if input["change_status"] not in VALID_CHANGE_STATUSES:
                raise HistoryFault("VALIDATION", f"Invalid change_status: {input['change_status']}", 422)
        if "generation_params" in input and input["generation_params"] is not None:
            if not isinstance(input["generation_params"], dict):
                raise HistoryFault("VALIDATION", "generation_params must be an object", 422)
        if "proposed_changes" in input and input["proposed_changes"] is not None:
            if not isinstance(input["proposed_changes"], dict):
                raise HistoryFault("VALIDATION", "proposed_changes must be an object", 422)

        ref_asset = None
        if "reference_asset_id" in input:
            ref_id = input["reference_asset_id"]
            if ref_id is not None:
                if not isinstance(ref_id, str):
                    raise HistoryFault("VALIDATION", "reference_asset_id must be a string", 422)
                ref_asset = db.query(AssetRecord).filter(
                    AssetRecord.id == ref_id, AssetRecord.project_id == project.id
                ).first()
                if not ref_asset:
                    raise HistoryFault("VALIDATION", f"Reference asset {ref_id} does not exist in project {project.id}", 422)

        char = (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project.id, CharacterRecord.id == input["character_id"])
            .first()
        )
        if char is None:
            raise HistoryFault("NOT_FOUND", "Character not found", 404)

        effective_input = dict(input)
        if ref_asset is not None and ref_asset.provenance:
            if "generation_params" not in input or input.get("generation_params") is None:
                asset_gen_params = ref_asset.provenance.get("generation_params")
                if asset_gen_params and isinstance(asset_gen_params, dict):
                    effective_input["generation_params"] = deepcopy(asset_gen_params)
                elif isinstance(ref_asset.provenance, dict):
                    effective_input["generation_params"] = deepcopy(ref_asset.provenance)

        ch_status = effective_input.get("change_status")
        if "proposed_changes" in effective_input and effective_input["proposed_changes"]:
            if "change_status" not in effective_input:
                effective_input["change_status"] = "PENDING_REVIEW"
        if ch_status == "APPROVED" and char.proposed_changes:
            for k, v in char.proposed_changes.items():
                if hasattr(char, k) and k not in ("id", "project_id") and k not in effective_input:
                    effective_input[k] = deepcopy(v)
            effective_input["proposed_changes"] = {}
        elif ch_status == "REJECTED":
            effective_input["proposed_changes"] = {}

        before = {}
        after = {}
        for field in self._fields:
            if field in effective_input:
                val = effective_input[field]
                curr = getattr(char, field)
                if curr != val:
                    before[field] = deepcopy(curr)
                    after[field] = deepcopy(val)

        if not before:
            return None

        before["manual_override"] = char.manual_override

        return {
            "character_id": char.id,
            "before": before,
            "after": after,
            "operation_id": input["_history_operation_id"],
        }

    def validate(self, payload):
        return (
            isinstance(payload, dict)
            and set(payload) == {"character_id", "before", "after", "operation_id"}
            and isinstance(payload["character_id"], str)
            and isinstance(payload["before"], dict)
            and isinstance(payload["after"], dict)
            and isinstance(payload["operation_id"], str)
        )

    def apply(self, db, project, payload, *, forward):
        char = (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project.id, CharacterRecord.id == payload["character_id"])
            .first()
        )
        if char is None:
            raise HistoryFault("CONFLICT", "Character was removed outside history", 409)

        target_dict = payload["after"] if forward else payload["before"]
        if "reference_asset_id" in target_dict:
            ref_id = target_dict["reference_asset_id"]
            if ref_id is not None:
                asset = db.query(AssetRecord).filter(
                    AssetRecord.id == ref_id, AssetRecord.project_id == project.id
                ).first()
                if not asset:
                    raise HistoryFault("CONFLICT", f"Referenced asset {ref_id} no longer exists in project", 409)

        if forward:
            for field, value in payload["after"].items():
                setattr(char, field, value)
            char.manual_override = True
        else:
            for field, value in payload["before"].items():
                setattr(char, field, value)

        char.updated_at = utc_now()
        db.flush()
        dependency_graph.invalidate(project.id, PipelineEntityTier.CHARACTER)

    def compensate(self, project, payload, *, forward):
        pass


class CharacterMergeStrategy:
    """Merge source character into target character, reassigning text regions and events."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        source_id = input.get("source_character_id")
        target_id = input.get("target_character_id")
        if not isinstance(source_id, str) or not isinstance(target_id, str) or source_id == target_id:
            raise HistoryFault("VALIDATION", "Valid distinct source and target character IDs are required", 422)

        source = db.query(CharacterRecord).filter(CharacterRecord.project_id == project.id, CharacterRecord.id == source_id).first()
        target = db.query(CharacterRecord).filter(CharacterRecord.project_id == project.id, CharacterRecord.id == target_id).first()
        if source is None or target is None:
            raise HistoryFault("NOT_FOUND", "Source or target character not found", 404)

        regions = (
            db.query(TextRegionRecord)
            .filter(TextRegionRecord.project_id == project.id, TextRegionRecord.speaker_character_id == source_id)
            .all()
        )
        reassigned_region_ids = [r.id for r in regions]

        events_actor = db.query(EventRecord).filter(EventRecord.project_id == project.id, EventRecord.actor_character_id == source_id).all()
        actor_event_ids = [ev.id for ev in events_actor]

        events_target = db.query(EventRecord).filter(EventRecord.project_id == project.id, EventRecord.target_character_id == source_id).all()
        target_event_ids = [ev.id for ev in events_target]

        merged_aliases = list(set((target.aliases or []) + (source.aliases or []) + [source.display_name]))

        return {
            "source": _row_data(source),
            "target_id": target_id,
            "target_aliases_before": list(target.aliases or []),
            "target_aliases_after": merged_aliases,
            "target_manual_override_before": target.manual_override,
            "reassigned_region_ids": reassigned_region_ids,
            "actor_event_ids": actor_event_ids,
            "target_event_ids": target_event_ids,
            "operation_id": input["_history_operation_id"],
        }

    def validate(self, payload):
        required = {"source", "target_id", "target_aliases_before", "target_aliases_after",
                    "target_manual_override_before", "reassigned_region_ids", "actor_event_ids",
                    "target_event_ids", "operation_id"}
        return isinstance(payload, dict) and required.issubset(set(payload)) and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        target = db.query(CharacterRecord).filter(CharacterRecord.project_id == project.id, CharacterRecord.id == payload["target_id"]).first()
        if target is None:
            raise HistoryFault("CONFLICT", "Target character was removed outside history", 409)

        source_id = payload["source"]["id"]
        target_id = payload["target_id"]

        if forward:
            source = db.query(CharacterRecord).filter(CharacterRecord.project_id == project.id, CharacterRecord.id == source_id).first()
            if source is not None:
                db.delete(source)

            # Reassign to target
            for rid in payload["reassigned_region_ids"]:
                reg = db.get(TextRegionRecord, rid)
                if reg:
                    reg.speaker_character_id = target_id

            for eid in payload["actor_event_ids"]:
                ev = db.get(EventRecord, eid)
                if ev:
                    ev.actor_character_id = target_id

            for eid in payload["target_event_ids"]:
                ev = db.get(EventRecord, eid)
                if ev:
                    ev.target_character_id = target_id

            target.aliases = list(payload["target_aliases_after"])
            target.manual_override = True
            target.updated_at = utc_now()
        else:
            # Recreate source
            existing_source = db.query(CharacterRecord).filter(CharacterRecord.project_id == project.id, CharacterRecord.id == source_id).first()
            if existing_source is None:
                source_data = dict(payload["source"])
                source_data.setdefault("reference_asset_id", None)
                source_data.setdefault("generation_params", {})
                source_data.setdefault("proposed_changes", {})
                source_data.setdefault("change_status", "NONE")
                db.add(CharacterRecord(**source_data, created_at=utc_now(), updated_at=utc_now()))

            # Reassign back to source
            for rid in payload["reassigned_region_ids"]:
                reg = db.get(TextRegionRecord, rid)
                if reg:
                    reg.speaker_character_id = source_id

            for eid in payload["actor_event_ids"]:
                ev = db.get(EventRecord, eid)
                if ev:
                    ev.actor_character_id = source_id

            for eid in payload["target_event_ids"]:
                ev = db.get(EventRecord, eid)
                if ev:
                    ev.target_character_id = source_id

            target.aliases = list(payload["target_aliases_before"])
            target.manual_override = payload["target_manual_override_before"]
            target.updated_at = utc_now()

        db.flush()
        dependency_graph.invalidate(project.id, PipelineEntityTier.CHARACTER)

    def compensate(self, project, payload, *, forward):
        pass


class CharacterSplitStrategy:
    """Split character identity across specified panels into a new character."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        character_id = input.get("character_id")
        new_name = input.get("new_name")
        panel_ids = input.get("panel_ids", [])
        if not isinstance(character_id, str) or not isinstance(new_name, str) or not new_name.strip():
            raise HistoryFault("VALIDATION", "Character ID and new name are required", 422)

        if "change_status" in input and input["change_status"] is not None:
            if input["change_status"] not in VALID_CHANGE_STATUSES:
                raise HistoryFault("VALIDATION", f"Invalid change_status: {input['change_status']}", 422)
        if "generation_params" in input and input["generation_params"] is not None:
            if not isinstance(input["generation_params"], dict):
                raise HistoryFault("VALIDATION", "generation_params must be an object", 422)
        if "proposed_changes" in input and input["proposed_changes"] is not None:
            if not isinstance(input["proposed_changes"], dict):
                raise HistoryFault("VALIDATION", "proposed_changes must be an object", 422)

        if "change_status" in input and input["change_status"] is not None:
            if input["change_status"] not in VALID_CHANGE_STATUSES:
                raise HistoryFault("VALIDATION", f"Invalid change_status: {input['change_status']}", 422)
        if "generation_params" in input and input["generation_params"] is not None:
            if not isinstance(input["generation_params"], dict):
                raise HistoryFault("VALIDATION", "generation_params must be an object", 422)
        if "proposed_changes" in input and input["proposed_changes"] is not None:
            if not isinstance(input["proposed_changes"], dict):
                raise HistoryFault("VALIDATION", "proposed_changes must be an object", 422)

        orig = db.query(CharacterRecord).filter(CharacterRecord.project_id == project.id, CharacterRecord.id == character_id).first()
        if orig is None:
            raise HistoryFault("NOT_FOUND", "Character not found", 404)

        if "reference_asset_id" in input:
            ref_id = input["reference_asset_id"]
            if ref_id is not None:
                if not isinstance(ref_id, str):
                    raise HistoryFault("VALIDATION", "reference_asset_id must be a string", 422)
                asset = db.query(AssetRecord).filter(
                    AssetRecord.id == ref_id, AssetRecord.project_id == project.id
                ).first()
                if not asset:
                    raise HistoryFault("VALIDATION", f"Reference asset {ref_id} does not exist in project {project.id}", 422)

        new_char_id = input.get("new_character_id") or f"char_{uuid.uuid4().hex[:8]}"
        new_char_data = {
            "id": new_char_id,
            "project_id": project.id,
            "display_name": new_name,
            "canonical_name": new_name,
            "aliases": [],
            "description": f"Separated identity from {orig.display_name}",
            "visual_traits": [],
            "role": orig.role,
            "first_panel_id": panel_ids[0] if panel_ids else None,
            "reference_panel_ids": panel_ids[:2] if panel_ids else [],
            "reference_asset_id": input.get("reference_asset_id"),
            "generation_params": input.get("generation_params") or {},
            "proposed_changes": input.get("proposed_changes") or {},
            "change_status": input.get("change_status") or "NONE",
            "status": "MANUAL",
            "manual_override": True,
        }

        reassigned_region_ids: list[str] = []
        for pid in panel_ids:
            regs = (
                db.query(TextRegionRecord)
                .filter(TextRegionRecord.panel_id == pid, TextRegionRecord.speaker_character_id == character_id)
                .all()
            )
            reassigned_region_ids.extend(r.id for r in regs)

        return {
            "orig_character_id": character_id,
            "new_character": new_char_data,
            "reassigned_region_ids": reassigned_region_ids,
            "operation_id": input["_history_operation_id"],
        }

    def validate(self, payload):
        required = {"orig_character_id", "new_character", "reassigned_region_ids", "operation_id"}
        return isinstance(payload, dict) and required.issubset(set(payload)) and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        new_char_id = payload["new_character"]["id"]
        orig_id = payload["orig_character_id"]

        if forward:
            ref_id = payload["new_character"].get("reference_asset_id")
            if ref_id is not None:
                asset = db.query(AssetRecord).filter(
                    AssetRecord.id == ref_id, AssetRecord.project_id == project.id
                ).first()
                if not asset:
                    raise HistoryFault("CONFLICT", f"Referenced asset {ref_id} no longer exists in project", 409)

            existing = db.query(CharacterRecord).filter(CharacterRecord.id == new_char_id).first()
            if existing is not None:
                raise HistoryFault("CONFLICT", "New character already exists", 409)
            db.add(CharacterRecord(**payload["new_character"], created_at=utc_now(), updated_at=utc_now()))

            for rid in payload["reassigned_region_ids"]:
                reg = db.get(TextRegionRecord, rid)
                if reg:
                    reg.speaker_character_id = new_char_id
        else:
            for rid in payload["reassigned_region_ids"]:
                reg = db.get(TextRegionRecord, rid)
                if reg:
                    reg.speaker_character_id = orig_id

            existing = db.query(CharacterRecord).filter(CharacterRecord.id == new_char_id).first()
            if existing is not None:
                db.delete(existing)

        db.flush()
        dependency_graph.invalidate(project.id, PipelineEntityTier.CHARACTER)

    def compensate(self, project, payload, *, forward):
        pass


class SceneMergeStrategy:
    """Merge scene 2 into scene 1, reassigning beats and boundaries."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        s1_id = input.get("scene_id_1")
        s2_id = input.get("scene_id_2")
        if not isinstance(s1_id, str) or not isinstance(s2_id, str) or s1_id == s2_id:
            raise HistoryFault("VALIDATION", "Distinct scene IDs are required", 422)

        s1 = db.query(SceneRecord).filter(SceneRecord.project_id == project.id, SceneRecord.id == s1_id).first()
        s2 = db.query(SceneRecord).filter(SceneRecord.project_id == project.id, SceneRecord.id == s2_id).first()
        if not s1 or not s2:
            raise HistoryFault("NOT_FOUND", "One or both scenes not found", 404)

        beats = db.query(StoryBeatRecord).filter(StoryBeatRecord.scene_id == s2.id).all()
        beat_ids = [b.id for b in beats]

        s1_before = {
            "panel_end": s1.panel_end,
            "summary": s1.summary,
            "character_ids": list(s1.character_ids or []),
            "manual_override": s1.manual_override,
        }
        s1_after = {
            "panel_end": s2.panel_end,
            "summary": f"{s1.summary} {s2.summary}".strip(),
            "character_ids": list(set((s1.character_ids or []) + (s2.character_ids or []))),
            "manual_override": True,
        }

        return {
            "s1_id": s1.id,
            "s1_before": s1_before,
            "s1_after": s1_after,
            "s2": _row_data(s2),
            "beat_ids": beat_ids,
            "operation_id": input["_history_operation_id"],
        }

    def validate(self, payload):
        required = {"s1_id", "s1_before", "s1_after", "s2", "beat_ids", "operation_id"}
        return isinstance(payload, dict) and required.issubset(set(payload)) and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        s1 = db.query(SceneRecord).filter(SceneRecord.project_id == project.id, SceneRecord.id == payload["s1_id"]).first()
        if s1 is None:
            raise HistoryFault("CONFLICT", "Scene 1 was removed outside history", 409)

        s2_id = payload["s2"]["id"]
        if forward:
            s2 = db.query(SceneRecord).filter(SceneRecord.project_id == project.id, SceneRecord.id == s2_id).first()
            if s2:
                db.delete(s2)

            for bid in payload["beat_ids"]:
                beat = db.get(StoryBeatRecord, bid)
                if beat:
                    beat.scene_id = s1.id

            for field, val in payload["s1_after"].items():
                setattr(s1, field, val)
        else:
            existing_s2 = db.query(SceneRecord).filter(SceneRecord.project_id == project.id, SceneRecord.id == s2_id).first()
            if existing_s2 is None:
                db.add(SceneRecord(**payload["s2"]))

            for bid in payload["beat_ids"]:
                beat = db.get(StoryBeatRecord, bid)
                if beat:
                    beat.scene_id = s2_id

            for field, val in payload["s1_before"].items():
                setattr(s1, field, val)

        db.flush()
        dependency_graph.invalidate(project.id, PipelineEntityTier.SCENE)

    def compensate(self, project, payload, *, forward):
        pass


class ScriptSegmentUpdateStrategy:
    """Update script segment text, speaker, emotion, intensity, and duration, retiming script."""
    _fields = ("text", "speaker_character_id", "emotion", "intensity", "estimated_duration")

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        segment_id = input.get("segment_id")
        script_id = input.get("script_id")
        if not isinstance(segment_id, str) or not isinstance(script_id, str):
            raise HistoryFault("VALIDATION", "Segment and Script IDs are required", 422)

        seg = (
            db.query(ScriptSegmentRecord)
            .filter(
                ScriptSegmentRecord.id == segment_id,
                ScriptSegmentRecord.script_id == script_id,
                ScriptSegmentRecord.project_id == project.id,
            )
            .first()
        )
        if seg is None:
            raise HistoryFault("NOT_FOUND", "Script segment not found", 404)

        script_record = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == script_id, VideoScriptRecord.project_id == project.id).first()
        if script_record is None:
            raise HistoryFault("NOT_FOUND", "Video script not found", 404)

        before_seg = {field: getattr(seg, field) for field in self._fields}
        before_seg["manual_override"] = seg.manual_override

        after_seg = dict(before_seg)
        for field in ("text", "speaker_character_id", "emotion", "intensity", "estimated_duration"):
            if field in input and input[field] is not None:
                after_seg[field] = input[field]

        if "text" in input and input["text"] is not None and "estimated_duration" not in input:
            from engine.story.script.duration import estimate_segment_duration
            after_seg["estimated_duration"] = estimate_segment_duration(input["text"], segment_type=seg.type)

        after_seg["manual_override"] = True

        # Timing map for all segments before & after
        sorted_segs = sorted(script_record.segments, key=lambda s: s.sequence)
        before_timings = {s.id: {"start": s.estimated_start, "end": s.estimated_end, "duration": s.estimated_duration} for s in sorted_segs}

        # Calculate after timings
        after_timings = {}
        elapsed = 0.0
        for s in sorted_segs:
            dur = after_seg["estimated_duration"] if s.id == segment_id else s.estimated_duration
            after_timings[s.id] = {"start": round(elapsed, 3), "end": round(elapsed + dur, 3), "duration": dur}
            elapsed += dur

        before_script = {
            "status": script_record.status,
            "estimated_duration": script_record.estimated_duration,
        }
        after_script = {
            "status": "DRAFT",
            "estimated_duration": round(elapsed, 3),
        }

        # Downstream timeline statuses
        active_audio = db.query(AudioTimelineRecord).filter(AudioTimelineRecord.project_id == project.id).order_by(AudioTimelineRecord.created_at.desc()).first()
        active_motion = db.query(VisualTimelineRecord).filter(VisualTimelineRecord.project_id == project.id).order_by(VisualTimelineRecord.created_at.desc()).first()
        latest_complete = db.query(RenderJobRecord).filter(RenderJobRecord.project_id == project.id, RenderJobRecord.status == "COMPLETE").order_by(RenderJobRecord.created_at.desc()).first()

        return {
            "script_id": script_id,
            "segment_id": segment_id,
            "before_seg": before_seg,
            "after_seg": after_seg,
            "before_script": before_script,
            "after_script": after_script,
            "before_timings": before_timings,
            "after_timings": after_timings,
            "active_audio_id": active_audio.id if active_audio else None,
            "active_audio_before_status": active_audio.status if active_audio else None,
            "active_motion_id": active_motion.id if active_motion else None,
            "active_motion_before_status": active_motion.status if active_motion else None,
            "latest_complete_id": latest_complete.job_id if latest_complete else None,
            "latest_complete_before_status": latest_complete.status if latest_complete else None,
            "operation_id": input["_history_operation_id"],
        }

    def validate(self, payload):
        required = {"script_id", "segment_id", "before_seg", "after_seg", "before_script", "after_script",
                    "before_timings", "after_timings", "operation_id"}
        return isinstance(payload, dict) and required.issubset(set(payload)) and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        seg = (
            db.query(ScriptSegmentRecord)
            .filter(
                ScriptSegmentRecord.id == payload["segment_id"],
                ScriptSegmentRecord.script_id == payload["script_id"],
                ScriptSegmentRecord.project_id == project.id,
            )
            .first()
        )
        if seg is None:
            raise HistoryFault("CONFLICT", "Script segment was removed outside history", 409)

        script_record = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == payload["script_id"], VideoScriptRecord.project_id == project.id).first()
        if script_record is None:
            raise HistoryFault("CONFLICT", "Video script was removed outside history", 409)

        seg_values = payload["after_seg" if forward else "before_seg"]
        for field, val in seg_values.items():
            setattr(seg, field, val)

        script_values = payload["after_script" if forward else "before_script"]
        script_record.status = script_values["status"]
        script_record.estimated_duration = script_values["estimated_duration"]
        script_record.updated_at = utc_now()

        timings = payload["after_timings" if forward else "before_timings"]
        for s in script_record.segments:
            if s.id in timings:
                s.estimated_start = timings[s.id]["start"]
                s.estimated_end = timings[s.id]["end"]
                s.estimated_duration = timings[s.id]["duration"]

        if forward:
            if payload.get("active_audio_id"):
                rec = db.get(AudioTimelineRecord, payload["active_audio_id"])
                if rec:
                    rec.status = "STALE"
                    rec.updated_at = utc_now()
            if payload.get("active_motion_id"):
                rec = db.get(VisualTimelineRecord, payload["active_motion_id"])
                if rec:
                    rec.status = "STALE"
                    rec.updated_at = utc_now()
            if payload.get("latest_complete_id"):
                rec = db.get(RenderJobRecord, payload["latest_complete_id"])
                if rec:
                    rec.status = "STALE"
        else:
            if payload.get("active_audio_id") and payload.get("active_audio_before_status"):
                rec = db.get(AudioTimelineRecord, payload["active_audio_id"])
                if rec:
                    rec.status = payload["active_audio_before_status"]
            if payload.get("active_motion_id") and payload.get("active_motion_before_status"):
                rec = db.get(VisualTimelineRecord, payload["active_motion_id"])
                if rec:
                    rec.status = payload["active_motion_before_status"]
            if payload.get("latest_complete_id") and payload.get("latest_complete_before_status"):
                rec = db.get(RenderJobRecord, payload["latest_complete_id"])
                if rec:
                    rec.status = payload["latest_complete_before_status"]

        db.flush()
        dependency_graph.invalidate(project.id, PipelineEntityTier.SCRIPT)

    def compensate(self, project, payload, *, forward):
        pass


class ScriptApproveStrategy:
    """Validate and approve video script, advancing project stage to PipelineStage.SCRIPT_APPROVED."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        script_id = input.get("script_id")
        if not isinstance(script_id, str):
            raise HistoryFault("VALIDATION", "Script ID is required", 422)

        s_rec = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == script_id, VideoScriptRecord.project_id == project.id).first()
        if s_rec is None:
            raise HistoryFault("NOT_FOUND", "Script not found", 404)

        report = _validate_script(db, project.id, script_id)
        if not report.passed:
            raise HistoryFault(
                "VALIDATION",
                f"Cannot approve script: {report.unsupported_segments} statements have unsupported claims",
                422,
            )

        operation_id = input["_history_operation_id"]
        paths = ["project.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "script_id": script_id,
            "before_script_status": s_rec.status,
            "after_script_status": "APPROVED",
            "before_stage": project.current_stage,
            "after_stage": PipelineStage.SCRIPT_APPROVED.value,
            "operation_id": operation_id,
        }

    def validate(self, payload):
        required = {"script_id", "before_script_status", "after_script_status", "before_stage", "after_stage", "operation_id"}
        return isinstance(payload, dict) and required.issubset(set(payload)) and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        s_rec = db.query(VideoScriptRecord).filter(VideoScriptRecord.id == payload["script_id"], VideoScriptRecord.project_id == project.id).first()
        if s_rec is None:
            raise HistoryFault("CONFLICT", "Script was removed outside history", 409)

        store = RetainedAssetStore(project.workspace_path)
        if forward:
            s_rec.status = payload["after_script_status"]
            s_rec.updated_at = utc_now()
            project.current_stage = payload["after_stage"]
            project.updated_at = utc_now()
            db.flush()
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                project_service._write_project_json(project)
                store.capture_after(payload["operation_id"])
        else:
            s_rec.status = payload["before_script_status"]
            s_rec.updated_at = utc_now()
            project.current_stage = payload["before_stage"]
            project.updated_at = utc_now()
            db.flush()
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class StoryboardSegmentUpdateStrategy:
    """Update storyboard segment in story/storyboard.json and sync with ScriptSegmentRecord."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)
        segment_id = input.get("segment_id")
        updates = input.get("updates")
        if not isinstance(segment_id, str) or not isinstance(updates, dict):
            raise HistoryFault("VALIDATION", "Segment ID and updates dict are required", 422)

        storyboard_path = Path(project.workspace_path) / "story" / "storyboard.json"
        if not storyboard_path.exists():
            try:
                alignment_service.align_script_to_frames(db, project.id)
            except Exception as e:
                raise HistoryFault("VALIDATION", f"Cannot align storyboard: {e}", 422)

        if not storyboard_path.exists():
            raise HistoryFault("NOT_FOUND", "Storyboard file not found", 404)

        operation_id = input["_history_operation_id"]
        paths = ["story/storyboard.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        db_seg = db.query(ScriptSegmentRecord).filter(ScriptSegmentRecord.id == segment_id).first()

        return {
            "segment_id": segment_id,
            "updates": updates,
            "before_db_seg": _row_data(db_seg),
            "operation_id": operation_id,
        }

    def validate(self, payload):
        required = {"segment_id", "updates", "operation_id"}
        return isinstance(payload, dict) and required.issubset(set(payload)) and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        segment_id = payload["segment_id"]

        if forward:
            update_data = StoryboardSegmentUpdate.model_validate(payload["updates"])
            alignment_service.update_segment(db, project.id, segment_id, update_data)
            db.flush()
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                store.capture_after(payload["operation_id"])
        else:
            store.restore(payload["operation_id"], "before")
            if payload.get("before_db_seg"):
                db_seg = db.query(ScriptSegmentRecord).filter(ScriptSegmentRecord.id == segment_id).first()
                if db_seg:
                    for field, val in payload["before_db_seg"].items():
                        setattr(db_seg, field, val)
                    db.flush()

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")


class StoryboardRealignStrategy:
    """Force realignment of narration to manga panels, retaining previous storyboard.json."""

    def prepare(self, db, project, input):
        if not isinstance(input, dict) or not isinstance(input.get("_history_operation_id"), str):
            raise HistoryFault("VALIDATION", "History operation is required", 422)

        storyboard_path = Path(project.workspace_path) / "story" / "storyboard.json"
        if not storyboard_path.exists():
            try:
                alignment_service.align_script_to_frames(db, project.id)
            except Exception as e:
                raise HistoryFault("VALIDATION", f"Cannot align storyboard: {e}", 422)

        operation_id = input["_history_operation_id"]
        paths = ["story/storyboard.json"]
        RetainedAssetStore(project.workspace_path).capture_before(operation_id, paths)

        return {
            "operation_id": operation_id,
        }

    def validate(self, payload):
        return isinstance(payload, dict) and set(payload) == {"operation_id"} and isinstance(payload["operation_id"], str)

    def apply(self, db, project, payload, *, forward):
        store = RetainedAssetStore(project.workspace_path)
        if forward:
            if store.is_complete(payload["operation_id"]):
                store.restore(payload["operation_id"], "after")
            else:
                alignment_service.align_script_to_frames(db, project.id, force_realign=True)
                store.capture_after(payload["operation_id"])
        else:
            store.restore(payload["operation_id"], "before")

    def compensate(self, project, payload, *, forward):
        RetainedAssetStore(project.workspace_path).restore(payload["operation_id"], "before" if forward else "after")
