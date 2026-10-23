"""Bridge approved Layer C scripts to editor clips without authoring new claims.

Panel provenance is a routing contract, not proof that a generated sentence is
true. The story/script review gates remain responsible for content approval.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math
from typing import Any

from engine.story.models import NarrativeDocument, SegmentType, VideoScript


def compile_narration_clips(
    script: VideoScript, narrative: NarrativeDocument, scenes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if script.project_id != narrative.project_id or not script.is_approved:
        raise ValueError("Narration requires an approved script for this narrative project.")
    if any(segment.type in (SegmentType.NARRATOR, SegmentType.CHARACTER_DIALOGUE)
           and segment.faithfulness_status == "UNSUPPORTED" for segment in script.segments):
        raise ValueError("The approved script contains an unsupported spoken segment.")
    from engine.story.script.validator import script_validator
    checked_script = script.model_copy(deep=True)
    if not script_validator.validate(checked_script, narrative).passed:
        raise ValueError("The approved script no longer passes source grounding; review it before synthesis.")
    script = checked_script
    known_panels = {o.panel_id for o in narrative.observations}
    region_panels = {u.text_region_id: u.panel_id for u in narrative.utterances}
    scene_panels = {
        scene["id"]: {layer.get("source_panel_id") for layer in scene.get("layers", [])} - {None, ""}
        for scene in scenes
    }
    if len(scene_panels) != len(scenes):
        raise ValueError("Timeline contains duplicate scene IDs.")
    names = {c.character_id: c.canonical_name or c.display_name for c in narrative.characters}
    clips = []
    seen_segments = set()
    covered = set()
    for segment in sorted(script.segments, key=lambda item: item.sequence):
        if segment.type not in (SegmentType.NARRATOR, SegmentType.CHARACTER_DIALOGUE):
            continue
        if segment.segment_id in seen_segments:
            raise ValueError(f"Duplicate script segment ID: {segment.segment_id}")
        seen_segments.add(segment.segment_id)
        evidence = segment.source_evidence
        panel_ids = set(evidence.panel_ids)
        if (not segment.text.strip() or segment.faithfulness_status != "SUPPORTED"
                or not panel_ids or not panel_ids <= known_panels
                or not math.isfinite(evidence.confidence) or evidence.confidence <= 0):
            raise ValueError(f"Segment {segment.segment_id} needs reviewed source grounding.")
        if any(region_panels.get(rid) not in panel_ids for rid in evidence.text_region_ids):
            raise ValueError(f"Segment {segment.segment_id} cites text outside its source panels.")
        candidates = [sid for sid, panels in scene_panels.items() if panel_ids <= panels]
        if segment.scene_id in candidates:
            scene_id = segment.scene_id
        elif len(candidates) == 1:
            scene_id = candidates[0]
        else:
            raise ValueError(f"Segment {segment.segment_id} cannot map unambiguously to a timeline scene.")
        scene = next(scene for scene in scenes if scene["id"] == scene_id)
        speaker = names.get(segment.speaker_character_id, "Narrator")
        covered.add(scene_id)
        clips.append({
            "id": f"narration_{script.script_id}_{segment.segment_id}",
            "scene_id": scene_id,
            "text": segment.text,
            "speaker": speaker,
            "voice": speaker,
            "emotion": segment.emotion.value,
            "intensity": segment.intensity,
            "speed": segment.target_pace,
            "start_time_sec": float(scene.get("start_time_sec", 0.0)),
            "duration_sec": segment.estimated_duration,
            "volume": 1.0,
            "status": "APPROVED",
            "review_status": "APPROVED",
            "source_script_id": script.script_id,
            "source_segment_ids": [segment.segment_id],
            "source_evidence": evidence.model_dump(),
            "audio_url": None,
        })
    missing = set(scene_panels) - covered
    if not clips or missing:
        raise ValueError(f"Approved narration does not cover timeline scenes: {sorted(missing)}. Review the script.")
    return clips


def reconcile_narration_clips(
    script: VideoScript, narrative: NarrativeDocument, scenes: list[dict[str, Any]],
    clips: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Upgrade matching legacy clips while preserving creator media and settings."""
    expected = compile_narration_clips(script, narrative, scenes)
    remaining = list(expected)
    result = []
    for clip in clips:
        candidates = [item for item in remaining
                      if item["scene_id"] == clip.get("scene_id") and item["text"] == clip.get("text")]
        if clip.get("source_segment_ids"):
            candidates = [item for item in candidates if item["source_segment_ids"] == clip["source_segment_ids"]]
        if len(candidates) != 1:
            raise ValueError(f"Narration clip {clip.get('id')} differs from the approved script. Review the edited narration.")
        match = candidates[0]
        remaining.remove(match)
        retained = deepcopy(clip)
        for field in ("source_script_id", "source_segment_ids", "source_evidence"):
            retained[field] = deepcopy(match[field])
        result.append(retained)
    if remaining:
        raise ValueError("Narration clips do not cover the approved script. Review missing segments.")
    return result


def synchronize_narration(scenes: list[dict[str, Any]], clips: list[dict[str, Any]]) -> None:
    """Retime speech sequentially within each scene, with one 0.35s cushion.

    Call only after measuring actual files. Validate everything before mutating
    either list so a failed synthesis cannot partially rewrite a creator's cut.
    Scenes without speech retain their intentional duration.
    """
    scene_ids = {scene["id"] for scene in scenes}
    if len(scene_ids) != len(scenes):
        raise ValueError("Timeline contains duplicate scene IDs.")
    grouped = defaultdict(list)
    for clip in clips:
        duration = float(clip.get("duration_sec", 0))
        if clip.get("scene_id") not in scene_ids or not math.isfinite(duration) or duration <= 0:
            raise ValueError(f"Narration clip {clip.get('id')} lacks a valid scene or measured duration.")
        grouped[clip["scene_id"]].append(clip)
    for scene in scenes:
        if scene["id"] not in grouped:
            duration = float(scene.get("duration_sec", 0))
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"Silent scene {scene['id']} needs a positive duration.")
    running_time = 0.0
    for scene in scenes:
        scene["start_time_sec"] = round(running_time, 6)
        cursor = running_time
        for clip in grouped[scene["id"]]:
            clip["start_time_sec"] = round(cursor, 6)
            cursor += float(clip["duration_sec"])
        if grouped[scene["id"]]:
            scene["duration_sec"] = round(cursor - running_time + 0.35, 6)
        running_time += float(scene["duration_sec"])
