"""
Narration-to-Frame Alignment & Visual Storyboard Service.
Bridges approved storyteller narration with source manga panels by:
  1. Selecting semantically relevant, highly expressive panels per spoken beat.
  2. Subdividing narration intervals across supporting panels without audio cuts.
  3. Locking shot durations directly to authoritative neural TTS speech lengths.
  4. Providing an editable, persistent two-pane visual storyboard.
  5. Strictly protecting manual user edits from automatic overwrite.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.models import (
    ProjectRecord, PanelRecord, VideoScriptRecord,
    ScriptSegmentRecord, AudioTimelineRecord,
)

logger = logging.getLogger("panelflow.story.alignment")

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


class CameraMotionConfig(BaseModel):
    type: str = "SLOW_PUSH"  # SLOW_PUSH, CHARACTER_FOCUS, REACTION_CLOSEUP, IMPACT, PAN, STATIC
    start_zoom: float = 1.0
    end_zoom: float = 1.08
    easing: str = "EASE_IN_OUT"  # EASE_IN_OUT, LINEAR, EASE_OUT


class StoryboardPanelRef(BaseModel):
    panel_id: str
    reading_order: int
    role: str = "NARRATION_FOCUS"  # ESTABLISHING, REACTION_CLOSEUP, ACTION, NARRATION_FOCUS, TRANSITION
    crop_bounds: Dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0})
    sub_duration_sec: float = 3.0
    camera_motion: CameraMotionConfig = Field(default_factory=CameraMotionConfig)
    crop_filename: str = ""
    image_url: Optional[str] = None


class StoryboardSegment(BaseModel):
    segment_id: str
    scene_id: str
    sequence: int
    text: str
    emotion: str = "NEUTRAL"
    intensity: float = 0.5
    audio_clip_path: Optional[str] = None
    measured_duration_sec: float = 3.0
    supporting_panels: List[StoryboardPanelRef] = Field(default_factory=list)
    music_cue: Dict[str, Any] = Field(default_factory=lambda: {"intent": "CALM", "ducking_gain_db": -14.0})
    sfx_cue: Dict[str, Any] = Field(default_factory=lambda: {"type": "NONE", "offset_sec": 0.0})
    manual_override: bool = False


class StoryboardDocument(BaseModel):
    project_id: str
    script_id: str
    version: str = "1.0"
    total_duration_sec: float = 0.0
    segments: List[StoryboardSegment] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class StoryboardSegmentUpdate(BaseModel):
    text: Optional[str] = None
    emotion: Optional[str] = None
    intensity: Optional[float] = None
    measured_duration_sec: Optional[float] = None
    supporting_panels: Optional[List[StoryboardPanelRef]] = None
    music_cue: Optional[Dict[str, Any]] = None
    sfx_cue: Optional[Dict[str, Any]] = None


class NarrationFrameAlignmentService:
    """
    Computes intelligent alignment between approved video script segments
    and manga panels, synchronizing visual sub-timelines to TTS speech.
    """

    def _get_storyboard_path(self, workspace_path: str) -> Path:
        return Path(workspace_path) / "story" / "storyboard.json"

    def _determine_camera_motion(self, role: str, emotion: str, intensity: float, duration: float = 3.0) -> CameraMotionConfig:
        emotion_upper = emotion.upper()
        if duration > 6.0:
            return CameraMotionConfig(type="SLOW_PUSH", start_zoom=1.0, end_zoom=1.06, easing="EASE_IN_OUT")
        if role == "REACTION_CLOSEUP" or intensity >= 0.8:
            return CameraMotionConfig(type="REACTION_CLOSEUP", start_zoom=1.05, end_zoom=1.08, easing="EASE_IN_OUT")
        elif role == "ACTION" or emotion_upper in ("ANGRY", "EXCITED", "TENSE"):
            return CameraMotionConfig(type="IMPACT", start_zoom=1.0, end_zoom=1.12, easing="EASE_OUT")
        elif role == "ESTABLISHING":
            return CameraMotionConfig(type="SLOW_PUSH", start_zoom=1.0, end_zoom=1.08, easing="EASE_IN_OUT")
        elif emotion_upper in ("CALM", "SAD", "NEUTRAL"):
            return CameraMotionConfig(type="SLOW_PUSH", start_zoom=1.0, end_zoom=1.05, easing="EASE_IN_OUT")
        return CameraMotionConfig(type="CHARACTER_FOCUS", start_zoom=1.02, end_zoom=1.06, easing="EASE_IN_OUT")

    def _score_panel(self, panel: PanelRecord, segment: ScriptSegmentRecord, is_first: bool, is_last: bool) -> float:
        score = 1.0
        # Check aspect ratio / dimensions
        aspect = panel.width / max(1.0, float(panel.height))
        # Establishing shots favor wide or full page panels at start
        if is_first and (aspect >= 1.2 or panel.panel_type == "FULL_PAGE"):
            score += 2.0

        # Close-up / reaction shots favor square or portrait panels with high emotional intensity
        if segment.intensity >= 0.7 and aspect <= 1.0:
            score += 1.5

        # Check evidence links
        evidence = segment.source_evidence or {}
        panel_ids = evidence.get("panel_ids", [])
        if panel.id in panel_ids:
            score += 3.0

        return score

    def align_script_to_frames(
        self,
        db: Session,
        project_id: str,
        script_id: Optional[str] = None,
        force_realign: bool = False,
    ) -> StoryboardDocument:
        """
        Creates or loads the storyboard document for a project.
        Maps narration segments to the most expressive manga panels and
        locks shot durations to speech. Preserves manual overrides.
        """
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not project:
            raise KeyError(f"Project '{project_id}' not found.")

        storyboard_path = self._get_storyboard_path(project.workspace_path)
        existing_doc: Optional[StoryboardDocument] = None
        if storyboard_path.exists():
            try:
                data = json.loads(storyboard_path.read_text(encoding="utf-8"))
                existing_doc = StoryboardDocument.model_validate(data)
                if not force_realign:
                    return existing_doc
            except Exception as e:
                logger.warning(f"Failed to load existing storyboard.json: {e}")

        # Fetch script
        script_query = db.query(VideoScriptRecord).filter(VideoScriptRecord.project_id == project_id)
        if script_id:
            script_record = script_query.filter(VideoScriptRecord.id == script_id).first()
        else:
            script_record = script_query.order_by(VideoScriptRecord.created_at.desc()).first()

        if not script_record:
            raise ValueError(f"No video script found for project '{project_id}'.")

        segments = (
            db.query(ScriptSegmentRecord)
            .filter(ScriptSegmentRecord.script_id == script_record.id)
            .order_by(ScriptSegmentRecord.sequence.asc())
            .all()
        )

        all_panels = (
            db.query(PanelRecord)
            .filter(PanelRecord.project_id == project_id, PanelRecord.status != "IGNORED")
            .order_by(PanelRecord.sequence.asc())
            .all()
        )
        if not all_panels:
            raise ValueError(f"No panels available for project '{project_id}'.")

        panel_map = {p.id: p for p in all_panels}

        # Check for MasterAudioTimeline to lock authoritative audio durations
        audio_rec = (
            db.query(AudioTimelineRecord)
            .filter(AudioTimelineRecord.project_id == project_id)
            .order_by(AudioTimelineRecord.created_at.desc())
            .first()
        )
        audio_durations: Dict[str, float] = {}
        audio_paths: Dict[str, str] = {}
        if audio_rec and audio_rec.timeline_json:
            for item in audio_rec.timeline_json.get("clips", []):
                seg_id = item.get("segment_id")
                if seg_id:
                    audio_durations[seg_id] = float(item.get("duration", 0.0))
                    audio_paths[seg_id] = item.get("file_path", "")

        existing_segments_map = {}
        if existing_doc:
            for es in existing_doc.segments:
                existing_segments_map[es.segment_id] = es

        storyboard_segments: List[StoryboardSegment] = []
        total_duration = 0.0

        for seg in segments:
            # Check for existing manual override
            if seg.id in existing_segments_map and existing_segments_map[seg.id].manual_override:
                preserved = existing_segments_map[seg.id]
                # Re-check audio duration lock if newly available
                if seg.id in audio_durations and audio_durations[seg.id] > 0:
                    preserved.measured_duration_sec = audio_durations[seg.id]
                    preserved.audio_clip_path = audio_paths.get(seg.id)
                    # Rescale sub-durations
                    n_sub = len(preserved.supporting_panels)
                    if n_sub > 0:
                        sub_dur = round(preserved.measured_duration_sec / n_sub, 3)
                        for p in preserved.supporting_panels:
                            p.sub_duration_sec = sub_dur
                storyboard_segments.append(preserved)
                total_duration += preserved.measured_duration_sec
                continue

            # Determine authoritative segment duration
            measured_dur = audio_durations.get(seg.id, seg.estimated_duration or 3.0)
            audio_path = audio_paths.get(seg.id)

            # Find candidate panels for this segment
            evidence = seg.source_evidence or {}
            ev_panel_ids = evidence.get("panel_ids", [])
            candidate_panels = [panel_map[pid] for pid in ev_panel_ids if pid in panel_map]

            if not candidate_panels:
                # Fallback to scene-range panels or sequence-proportional panel
                candidate_panels = all_panels[:max(1, len(all_panels) // len(segments))]

            # Pick 1-3 best panels based on scoring
            scored = []
            for idx, p in enumerate(candidate_panels):
                is_first = (idx == 0 and seg.sequence == 1)
                is_last = (idx == len(candidate_panels) - 1 and seg.sequence == len(segments))
                s = self._score_panel(p, seg, is_first, is_last)
                scored.append((s, p))

            scored.sort(key=lambda x: x[0], reverse=True)
            # Pick top 1 to 2 panels
            selected_count = 2 if measured_dur >= 5.0 and len(scored) >= 2 else 1
            chosen_panels = [p for _, p in scored[:selected_count]]

            # Distribute duration equally or proportionally across chosen panels
            sub_dur = round(measured_dur / len(chosen_panels), 3)

            panel_refs: List[StoryboardPanelRef] = []
            for p in chosen_panels:
                role = "ESTABLISHING" if (seg.sequence == 1 and p == chosen_panels[0]) else (
                    "REACTION_CLOSEUP" if seg.intensity >= 0.7 else "NARRATION_FOCUS"
                )
                motion = self._determine_camera_motion(role, seg.emotion, seg.intensity, duration=sub_dur)
                panel_refs.append(StoryboardPanelRef(
                    panel_id=p.id,
                    reading_order=p.sequence,
                    role=role,
                    crop_bounds={
                        "x": getattr(p, "normalized_x", 0.0),
                        "y": getattr(p, "normalized_y", 0.0),
                        "width": getattr(p, "normalized_width", 1.0),
                        "height": getattr(p, "normalized_height", 1.0),
                    },
                    sub_duration_sec=sub_dur,
                    camera_motion=motion,
                    crop_filename=p.crop_filename,
                    image_url=f"/api/projects/{project_id}/panels/{p.id}/image",
                ))

            # Compose music/sfx intents
            music_intent = seg.music_intent or ("TENSE" if seg.intensity >= 0.7 else "CALM")
            music_cue = {
                "intent": music_intent,
                "ducking_gain_db": -14.0 if seg.intensity < 0.8 else -16.0,
            }
            sfx_cue = {
                "type": seg.sfx_intent or "NONE",
                "offset_sec": 0.5,
            }

            storyboard_segment = StoryboardSegment(
                segment_id=seg.id,
                scene_id=seg.scene_id,
                sequence=seg.sequence,
                text=seg.text,
                emotion=seg.emotion,
                intensity=seg.intensity,
                audio_clip_path=audio_path,
                measured_duration_sec=measured_dur,
                supporting_panels=panel_refs,
                music_cue=music_cue,
                sfx_cue=sfx_cue,
                manual_override=seg.manual_override,
            )
            storyboard_segments.append(storyboard_segment)
            total_duration += measured_dur

        doc = StoryboardDocument(
            project_id=project_id,
            script_id=script_record.id,
            total_duration_sec=round(total_duration, 3),
            segments=storyboard_segments,
            updated_at=utc_now_iso(),
        )

        # Save to disk
        storyboard_path.parent.mkdir(parents=True, exist_ok=True)
        storyboard_path.write_text(json.dumps(doc.model_dump(), indent=2), encoding="utf-8")

        return doc

    def update_segment(
        self,
        db: Session,
        project_id: str,
        segment_id: str,
        update_data: StoryboardSegmentUpdate,
    ) -> StoryboardSegment:
        """
        Updates an individual storyboard segment, locking in manual user overrides.
        """
        project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not project:
            raise KeyError(f"Project '{project_id}' not found.")

        storyboard_path = self._get_storyboard_path(project.workspace_path)
        if not storyboard_path.exists():
            # Generate first
            self.align_script_to_frames(db, project_id)

        data = json.loads(storyboard_path.read_text(encoding="utf-8"))
        doc = StoryboardDocument.model_validate(data)

        target_seg = None
        for seg in doc.segments:
            if seg.segment_id == segment_id:
                target_seg = seg
                break

        if not target_seg:
            raise KeyError(f"Storyboard segment '{segment_id}' not found.")

        # Apply updates
        if update_data.text is not None:
            target_seg.text = update_data.text
        if update_data.emotion is not None:
            target_seg.emotion = update_data.emotion
        if update_data.intensity is not None:
            target_seg.intensity = max(0.0, min(1.0, update_data.intensity))
        if update_data.measured_duration_sec is not None:
            target_seg.measured_duration_sec = max(0.5, update_data.measured_duration_sec)
        if update_data.supporting_panels is not None:
            target_seg.supporting_panels = update_data.supporting_panels
        if update_data.music_cue is not None:
            target_seg.music_cue = update_data.music_cue
        if update_data.sfx_cue is not None:
            target_seg.sfx_cue = update_data.sfx_cue

        # Mark as manual user override so automatic runs preserve it
        target_seg.manual_override = True

        # Sync back to ScriptSegmentRecord in DB
        db_seg = db.query(ScriptSegmentRecord).filter(ScriptSegmentRecord.id == segment_id).first()
        if db_seg:
            db_seg.text = target_seg.text
            db_seg.emotion = target_seg.emotion
            db_seg.intensity = target_seg.intensity
            db_seg.estimated_duration = target_seg.measured_duration_sec
            db_seg.manual_override = True
            db.commit()

        # Recalculate total duration
        doc.total_duration_sec = round(sum(s.measured_duration_sec for s in doc.segments), 3)
        doc.updated_at = utc_now_iso()

        # Save to disk
        storyboard_path.write_text(json.dumps(doc.model_dump(), indent=2), encoding="utf-8")

        return target_seg


alignment_service = NarrationFrameAlignmentService()
