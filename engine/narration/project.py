"""Project the locked timeline into the editor state and a new VideoScript."""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from engine.database.models import ProjectRecord, ScriptSegmentRecord, VideoScriptRecord
from engine.narration.artifacts import BeatSheet, LockedTimeline, PerformancePlan, ScriptIR, VoiceTake

# Legacy autopilot builds these inline (engine/pipeline/autopilot.py), so there is nothing to import.
_BACKGROUND = {"enabled": True, "preset": "duplicate_blur", "blur_sigma": 24.0, "brightness": 0.45,
               "foreground_fit": "contain", "edge_shadow": 0.6, "motion": "none", "motion_amount": 0.0}
_CAMERA = {"preset": "custom", "zoom_start": 1.04, "zoom_end": 1.0, "pan_x_start": 0.0, "pan_x_end": 0.0,
           "pan_y_start": 0.0, "pan_y_end": 0.0, "easing": "ease_in_out"}


def _copy_atomic(src: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def _next_version(db, project_id: str) -> str:
    top = 0
    for (v,) in db.query(VideoScriptRecord.version).filter(VideoScriptRecord.project_id == project_id):
        try:
            top = max(top, int(float(v)))
        except (TypeError, ValueError):
            pass
    return f"{top + 1}.0"


def apply_to_project(db, project_id: str, tl: LockedTimeline, script: ScriptIR, sheet: BeatSheet,
                     takes: list[VoiceTake], workspace: Path, plan: PerformancePlan) -> str:
    project = db.get(ProjectRecord, project_id)
    settings = dict(project.settings or {})
    state = dict(settings.get("story_editor_state") or {})
    old = (state.get("scenes") or [{}])[0]
    take = {t.line_id: t for t in takes}
    marks = {m.line_id: m for m in plan.lines}
    line = {ln.line_id: ln for ln in script.lines}

    scenes = []
    for sc in sheet.scenes:
        panels = [p for p in tl.panels if p.scene_id == sc.scene_id]
        if not panels:
            continue
        start, end = panels[0].start, panels[-1].end
        camera = dict(old.get("camera") or _CAMERA)
        camera["duration_sec"] = end - start
        scenes.append({
            "id": "narr_" + sc.scene_id, "start_time_sec": start, "duration_sec": end - start,
            "layers": [{
                "id": f"layer_{sc.scene_id}_{k}", "source_panel_id": p.panel_id, "start_offset_sec": p.start - start,
                "duration_sec": p.end - p.start, "visible": True,
                "transform": {"x": 0, "y": 0, "scale": 1, "rotation": 0, "opacity": 1, "z_index": 0},
                "motion_preset": "cinematic_vertical_pan"} for k, p in enumerate(panels)],
            "background": dict(old.get("background") or _BACKGROUND), "camera": camera,
            "transition_in": old.get("transition_in", "none"),
        })

    script_id = str(uuid.uuid4())
    seg_ids = {c.line_id: str(uuid.uuid4()) for c in tl.clips}
    scene_start = {s["id"]: s["start_time_sec"] for s in scenes}
    panel_scene = {p.panel_id: "narr_" + p.scene_id for p in tl.panels}
    db.add(VideoScriptRecord(id=script_id, project_id=project_id, version=_next_version(db, project_id),
                             adaptation_profile="narration_compiler", estimated_duration=tl.duration,
                             status="APPROVED"))
    db.flush()
    clips = []
    for i, c in enumerate(tl.clips):
        name = "narr_" + Path(take[c.line_id].audio_path).stem + ".wav"  # content-named: a changed line never overwrites
        _copy_atomic(take[c.line_id].audio_path, Path(workspace) / "audio" / "dialogue" / name)
        emotion = marks[c.line_id].emotion.upper()
        sid = panel_scene[c.panel_id]
        clips.append({
            "id": "narr_" + c.line_id, "scene_id": sid, "text": line[c.line_id].text,
            "speaker": "Narrator", "voice": "Narrator", "emotion": emotion, "intensity": 0.5,
            "speed": take[c.line_id].rate, "start_time_sec": c.start, "duration_sec": c.end - c.start,
            "scene_offset_sec": c.start - scene_start[sid], "volume": 1.0,
            "status": "APPROVED", "review_status": "APPROVED",
            "source_script_id": script_id, "source_segment_ids": [seg_ids[c.line_id]],
            "source_evidence": {"panel_ids": [c.panel_id], "text_region_ids": [], "confidence": 0.9},
            "audio_url": f"/api/projects/{project_id}/audio/dialogue/{name}",
        })
        db.add(ScriptSegmentRecord(
            id=seg_ids[c.line_id], script_id=script_id, project_id=project_id, scene_id=sid, sequence=i,
            type="NARRATOR", text=line[c.line_id].text, emotion=emotion, estimated_start=c.start,
            estimated_end=c.end, estimated_duration=c.end - c.start, source_evidence={"panel_ids": [c.panel_id]}))
    state.update(scenes=scenes, narration_clips=clips)
    settings["story_editor_state"] = state
    project.settings = settings
    db.commit()
    return script_id

