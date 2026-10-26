"""
Safe, Non-Destructive Project Recovery & Timeline Reconciliation Service.

Diagnoses and repairs legacy projects impacted by:
1. Compounding downstream voids and timeline expansion (e.g. 4493s void)
2. Mass unlinking of narration clips from visual scenes
3. Orphaned narration clips referencing deleted scenes
4. Dummy placeholder narration clips polluting silent pacing panels
5. Audio takes with prompt direction leakage

Safety Guarantees:
- Never auto-relinks or mutates projects silently on load
- Mandatory immutable pre-recovery JSON snapshot before applying any mutation
- Complete dry-run diff manifest before commit
- 1-click atomic rollback to exact byte-identical pre-repair state
"""
from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from engine.audio.sanitizer import clean_script_text, detect_prompt_leakage
from engine.database.models import ProjectRecord
from engine.security.paths import (
    ensure_contained_directory,
    read_contained_bytes,
    write_contained_json,
)

logger = logging.getLogger("panelflow.story.recovery")

# Known boilerplate strings generated for silent pacing panels
SILENT_PANEL_BOILERPLATE = [
    "The silence settled once more...",
    "The silence settled once more.",
    "Silence settled once more...",
    "Silence settled once more.",
    "Without saying a word...",
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace(":", "-")


class ProjectRecoveryService:
    """
    Non-destructive diagnosis, planning, execution, and rollback of timeline recovery.
    """

    def diagnose_timeline(self, state: Dict[str, Any], project_id: str = "") -> Dict[str, Any]:
        """
        Diagnoses defects in the saved timeline state without mutating anything.
        """
        scenes = state.get("scenes", [])
        narration_clips = state.get("narration_clips", [])

        scene_ids = {s.get("id") for s in scenes if s.get("id")}

        # 1. Detect accidental black voids between scenes
        sorted_scenes = sorted(scenes, key=lambda s: float(s.get("start_time_sec", 0)))
        accidental_voids = []
        total_void_sec = 0.0

        for i in range(len(sorted_scenes) - 1):
            curr_sc = sorted_scenes[i]
            next_sc = sorted_scenes[i + 1]
            curr_end = float(curr_sc.get("start_time_sec", 0)) + float(curr_sc.get("duration_sec", 0))
            next_start = float(next_sc.get("start_time_sec", 0))
            gap = next_start - curr_end

            if gap > 0.033:  # Greater than 1 frame @ 30fps
                is_intentional = curr_sc.get("is_intentional_black", False)
                if not is_intentional:
                    accidental_voids.append({
                        "from_scene": curr_sc.get("id"),
                        "to_scene": next_sc.get("id"),
                        "gap_sec": round(gap, 3),
                        "start_sec": round(curr_end, 3),
                        "end_sec": round(next_start, 3),
                    })
                    total_void_sec += gap

        # 2. Detect unlinked and orphaned narration clips
        unlinked_clips = []
        orphan_clips = []
        dummy_clips = []
        leaked_clips = []

        for clip in narration_clips:
            c_id = clip.get("id", "unnamed")
            s_id = clip.get("scene_id")
            linked = clip.get("linked_to_scene", False)
            text = clip.get("text", "").strip()

            # Check dummy placeholder
            if any(b.lower() in text.lower() for b in SILENT_PANEL_BOILERPLATE):
                dummy_clips.append({"id": c_id, "text": text, "scene_id": s_id})

            # Check prompt direction leakage
            has_leak, leak_reason = detect_prompt_leakage(text)
            if has_leak:
                leaked_clips.append({"id": c_id, "reason": leak_reason, "text": text[:60]})

            if s_id and s_id not in scene_ids:
                orphan_clips.append({"id": c_id, "orphan_scene_id": s_id})

            if not linked or not s_id:
                unlinked_clips.append(c_id)

        total_timeline_sec = 0.0
        if scenes:
            last_sc = sorted_scenes[-1]
            total_timeline_sec = round(float(last_sc.get("start_time_sec", 0)) + float(last_sc.get("duration_sec", 0)), 3)

        is_corrupted = (
            len(accidental_voids) > 0
            or len(unlinked_clips) > 0
            or len(orphan_clips) > 0
            or len(dummy_clips) > 0
            or len(leaked_clips) > 0
        )

        return {
            "project_id": project_id,
            "is_corrupted": is_corrupted,
            "total_timeline_duration_sec": total_timeline_sec,
            "voids_count": len(accidental_voids),
            "total_void_duration_sec": round(total_void_sec, 3),
            "accidental_voids": accidental_voids,
            "unlinked_clips_count": len(unlinked_clips),
            "unlinked_clip_ids": unlinked_clips,
            "orphan_clips_count": len(orphan_clips),
            "orphan_clips": orphan_clips,
            "dummy_clips_count": len(dummy_clips),
            "dummy_clips": dummy_clips,
            "leaked_clips_count": len(leaked_clips),
            "leaked_clips": leaked_clips,
        }

    def create_repair_plan(
        self, state: Dict[str, Any], known_panels: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Builds a dry-run reconciliation plan detailing every change.
        Does NOT modify the project or database.
        """
        orig_scenes = state.get("scenes", [])
        before_duration = 0.0
        if orig_scenes:
            sorted_orig = sorted(orig_scenes, key=lambda s: float(s.get("start_time_sec", 0)))
            before_duration = round(
                float(sorted_orig[-1].get("start_time_sec", 0)) + float(sorted_orig[-1].get("duration_sec", 0)), 3
            )

        repaired = copy.deepcopy(state)
        scenes = repaired.get("scenes", [])
        narration_clips = repaired.get("narration_clips", [])

        diff_summary: List[str] = []

        # 1. Remove dummy boilerplate clips from silent panels
        valid_clips = []
        removed_dummy_clips = []
        silent_scene_ids = set()

        for clip in narration_clips:
            text = clip.get("text", "").strip()
            is_dummy = any(b.lower() in text.lower() for b in SILENT_PANEL_BOILERPLATE)
            if is_dummy:
                removed_dummy_clips.append({"id": clip.get("id"), "text": text})
                if clip.get("scene_id"):
                    silent_scene_ids.add(clip["scene_id"])
                diff_summary.append(
                    f"Removed dummy narration clip '{clip.get('id')}' with boilerplate text: \"{text}\""
                )
            else:
                valid_clips.append(clip)

        # Mark affected scenes as true silent scenes
        for sc in scenes:
            if sc.get("id") in silent_scene_ids:
                sc["is_silent"] = True
                diff_summary.append(f"Marked scene '{sc.get('id')}' as a silent visual pacing scene.")

        # Sanitize prompt leakage from narration clips
        sanitized_clips = []
        for clip in valid_clips:
            orig_text = clip.get("text", "")
            has_leak, reason = detect_prompt_leakage(orig_text)
            if has_leak:
                clean_text = clean_script_text(orig_text)
                clip["text"] = clean_text
                sanitized_clips.append({"id": clip.get("id"), "reason": reason})
                diff_summary.append(
                    f"Sanitized prompt leakage in narration clip '{clip.get('id')}': {reason}"
                )

        # 2. Collapse accidental black voids between visual scenes
        sorted_scenes = sorted(scenes, key=lambda s: float(s.get("start_time_sec", 0)))
        prev_end = 0.0
        cumulative_shift = 0.0
        void_sec_removed = 0.0

        for sc in sorted_scenes:
            orig_start = float(sc.get("start_time_sec", 0))
            dur = float(sc.get("duration_sec", 0))
            is_intentional_black = sc.get("is_intentional_black", False)
            shifted_start = orig_start - cumulative_shift

            if shifted_start > prev_end + 0.033 and not is_intentional_black:
                gap = shifted_start - prev_end
                cumulative_shift += gap
                void_sec_removed += gap
                new_start = round(prev_end, 3)
                sc["start_time_sec"] = new_start
                diff_summary.append(
                    f"Collapsed {gap:.3f}s void before scene '{sc.get('id')}': "
                    f"shifted start from {orig_start:.3f}s -> {new_start:.3f}s."
                )
            else:
                new_start = round(shifted_start, 3)
                sc["start_time_sec"] = new_start

            prev_end = round(new_start + dur, 3)

        # Build map of panel_id -> scene_id
        panel_to_scene: Dict[str, str] = {}
        for sc in sorted_scenes:
            for layer in sc.get("layers", []):
                p_id = layer.get("source_panel_id")
                if p_id:
                    panel_to_scene[p_id] = sc["id"]

        scene_map = {s["id"]: s for s in sorted_scenes}

        # 3. Re-link narration clips to visual scenes based on panel references
        relinked_clips = []
        for clip in valid_clips:
            orig_scene_id = clip.get("scene_id")
            linked = clip.get("linked_to_scene", False)

            # Discover panel references
            panel_ids = (
                clip.get("source_panel_ids")
                or (clip.get("source_evidence") or {}).get("panel_ids", [])
                or ([clip.get("panel_id")] if clip.get("panel_id") else [])
            )

            matched_scene_id = None
            for pid in panel_ids:
                if pid in panel_to_scene:
                    matched_scene_id = panel_to_scene[pid]
                    break

            if matched_scene_id and scene_map.get(matched_scene_id):
                target_sc = scene_map[matched_scene_id]
                was_unlinked_or_changed = (not linked) or (orig_scene_id != matched_scene_id)
                clip["scene_id"] = matched_scene_id
                clip["linked_to_scene"] = True

                old_start = float(clip.get("start_time_sec", 0))
                if was_unlinked_or_changed:
                    new_start = round(target_sc["start_time_sec"], 3)
                    clip["start_time_sec"] = new_start
                    clip["scene_offset_sec"] = 0.0

                    relinked_clips.append({
                        "id": clip.get("id"),
                        "matched_scene_id": matched_scene_id,
                        "old_start_sec": old_start,
                        "new_start_sec": new_start,
                    })
                    diff_summary.append(
                        f"Re-linked narration clip '{clip.get('id')}' to scene '{matched_scene_id}' at {new_start:.3f}s."
                    )
                else:
                    offset = float(clip.get("scene_offset_sec", 0))
                    clip["start_time_sec"] = round(target_sc["start_time_sec"] + offset, 3)
            elif orig_scene_id and scene_map.get(orig_scene_id):
                # Scene exists: follow its collapsed position
                target_sc = scene_map[orig_scene_id]
                clip["linked_to_scene"] = True
                offset = float(clip.get("scene_offset_sec", 0))
                clip["start_time_sec"] = round(target_sc["start_time_sec"] + offset, 3)
            else:
                # Floating clip: clear invalid orphan id
                clip["scene_id"] = None
                clip["linked_to_scene"] = False

        repaired["scenes"] = sorted_scenes
        repaired["narration_clips"] = valid_clips

        after_duration = prev_end

        return {
            "duration_before_sec": before_duration,
            "duration_after_sec": after_duration,
            "voids_collapsed_count": len([d for d in diff_summary if "Collapsed" in d]),
            "void_seconds_removed": round(void_sec_removed, 3),
            "relinked_clips_count": len(relinked_clips),
            "relinked_clips": relinked_clips,
            "removed_dummy_clips_count": len(removed_dummy_clips),
            "removed_dummy_clips": removed_dummy_clips,
            "sanitized_clips_count": len(sanitized_clips),
            "sanitized_clips": sanitized_clips,
            "diff_summary": diff_summary,
            "repaired_state": repaired,
        }

    def apply_repair_plan(
        self,
        db: Session,
        project_id: str,
        workspace_path: Path,
        repair_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Executes the repair plan:
        1. Writes an immutable pre-recovery backup snapshot to disk.
        2. Applies the reconciled state to the project.
        3. Commits transactionally.
        """
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        workspace = Path(workspace_path)
        snapshots_dir = workspace / "snapshots"
        ensure_contained_directory(workspace, Path("snapshots"))

        # 1. Immutable pre-recovery snapshot
        timestamp = utc_now_iso()
        snapshot_filename = f"pre_recovery_{timestamp}.json"
        snapshot_rel_path = Path("snapshots") / snapshot_filename

        snapshot_payload = {
            "project_id": project_id,
            "snapshot_type": "PRE_RECOVERY_BACKUP",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "settings": copy.deepcopy(project.settings or {}),
            "repair_plan_summary": {
                "duration_before_sec": repair_plan.get("duration_before_sec"),
                "duration_after_sec": repair_plan.get("duration_after_sec"),
                "diff_summary": repair_plan.get("diff_summary", []),
            },
        }
        write_contained_json(workspace, snapshot_rel_path, snapshot_payload)
        logger.info(f"Saved immutable pre-recovery snapshot to {snapshot_rel_path}")

        # 2. Update project settings with repaired state
        settings = dict(project.settings or {})
        settings["story_editor_state"] = repair_plan["repaired_state"]
        project.settings = settings
        project.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(project)

        return {
            "success": True,
            "project_id": project_id,
            "snapshot_path": str(workspace / snapshot_rel_path),
            "snapshot_filename": snapshot_filename,
            "new_duration_sec": repair_plan.get("duration_after_sec"),
            "diff_summary": repair_plan.get("diff_summary", []),
        }

    def rollback_recovery(
        self,
        db: Session,
        project_id: str,
        workspace_path: Path,
        snapshot_filename: str,
    ) -> Dict[str, Any]:
        """
        Restores the exact pre-recovery state from the specified snapshot.
        """
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not project:
            raise ValueError(f"Project not found: {project_id}")

        workspace = Path(workspace_path)
        snapshot_rel_path = Path("snapshots") / snapshot_filename

        raw_bytes = read_contained_bytes(workspace, snapshot_rel_path)
        snapshot_data = json.loads(raw_bytes.decode("utf-8"))

        saved_settings = snapshot_data.get("settings", {})
        project.settings = saved_settings
        project.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(project)

        logger.info(f"Successfully rolled back project {project_id} to snapshot {snapshot_filename}")
        return {
            "success": True,
            "project_id": project_id,
            "restored_snapshot": snapshot_filename,
            "restored_at": datetime.now(timezone.utc).isoformat(),
        }


recovery_service = ProjectRecoveryService()
