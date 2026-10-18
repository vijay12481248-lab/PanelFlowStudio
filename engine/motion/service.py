"""
Motion Director Service for PanelFlow Studio.
Coordinates shot planning, visual timeline generation, overrides, and motion approval gates.
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from PIL import Image

from engine.database.models import (
    ProjectRecord,
    VideoScriptRecord,
    AudioTimelineRecord,
    VisualTimelineRecord,
    PanelRecord,
    PageRecord,
)
from engine.acquisition.models.models import PipelineStage
from engine.motion.director import MotionDirector
from engine.motion.models.input_contract import (
    MotionDirectorInput,
    VisualSource,
    MasterAudioTimeline,
    MotionStyleProfile,
)
from engine.motion.models.camera import NormalizedRect, TargetResolution
from engine.motion.models.enums import MotionPreset, EasingFunction, MotionType
from engine.motion.models.overrides import MotionOverrides, ShotOverride
from engine.story.models import (
    VideoScript,
    SceneEntity,
    CharacterEntity,
    CharacterRole,
)


def utc_now():
    return datetime.now(timezone.utc)


class MotionService:
    """
    Orchestrates MotionDirector planning, timeline caching, shot overrides, and approval.
    """

    def __init__(self):
        self.director = MotionDirector()

    def get_motion_timeline(self, db: Session, project_id: str) -> Optional[Dict[str, Any]]:
        record = (
            db.query(VisualTimelineRecord)
            .filter(VisualTimelineRecord.project_id == project_id)
            .order_by(VisualTimelineRecord.created_at.desc())
            .first()
        )
        if not record:
            return None

        return {
            "id": record.id,
            "project_id": record.project_id,
            "status": record.status,
            "total_duration": record.total_duration,
            "total_shots": record.total_shots,
            "style_preset": record.style_preset,
            "timeline": record.timeline_json,
            "overrides": record.overrides_json,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    def plan_motion_timeline(
        self,
        db: Session,
        project_id: str,
        style_preset: str = "cinematic",
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        # 1. Load Audio Timeline
        audio_rec = (
            db.query(AudioTimelineRecord)
            .filter(AudioTimelineRecord.project_id == project_id)
            .order_by(AudioTimelineRecord.created_at.desc())
            .first()
        )
        if not audio_rec:
            raise ValueError("No audio timeline found. Complete audio generation first.")
        if audio_rec.status != "APPROVED":
            raise ValueError("Approve the current audio timeline before planning motion.")

        mat = MasterAudioTimeline.model_validate(audio_rec.timeline_json)

        # 2. Load Script
        script_rec = (
            db.query(VideoScriptRecord)
            .filter(VideoScriptRecord.project_id == project_id)
            .order_by(VideoScriptRecord.created_at.desc())
            .first()
        )
        if not script_rec:
            raise ValueError("No video script found.")

        valid_emotions = {
            'NEUTRAL', 'HAPPY', 'SAD', 'ANGRY', 'AFRAID', 'SURPRISED',
            'DISGUSTED', 'CONFUSED', 'DETERMINED', 'EXCITED', 'CALM',
            'TENSE', 'GRIEVING', 'SARCASTIC'
        }
        segments_payload = []
        for s in script_rec.segments:
            emo = (s.emotion or "NEUTRAL").upper()
            if emo not in valid_emotions:
                emo = "NEUTRAL"
            segments_payload.append({
                "segment_id": s.id,
                "scene_id": s.scene_id or "scene_01",
                "beat_id": s.beat_id,
                "sequence": s.sequence,
                "type": s.type,
                "speaker_character_id": s.speaker_character_id,
                "text": s.text,
                "emotion": emo,
                "intensity": s.intensity if s.intensity is not None else 0.5,
                "estimated_duration": s.estimated_duration or 2.0,
                "estimated_start": s.estimated_start or 0.0,
                "estimated_end": s.estimated_end or (s.estimated_duration or 2.0),
                "source_evidence": s.source_evidence or {},
                "production_intent": s.production_intent or "",
                "music_intent": s.music_intent,
                "sfx_intent": s.sfx_intent,
                "motion_intent": s.motion_intent,
                "faithfulness_status": s.faithfulness_status or "SUPPORTED",
                "manual_override": bool(s.manual_override),
            })

        script = VideoScript.model_validate(
            {
                "script_id": script_rec.id,
                "project_id": project_id,
                "version": script_rec.version,
                "adaptation_profile": script_rec.adaptation_profile,
                "segments": segments_payload,
            }
        )

        # 3. Build Visual Sources from project panels / pages
        workspace = Path(proj.workspace_path)
        visual_sources: List[VisualSource] = []

        # Check pages / panels in DB
        pages = db.query(PageRecord).filter(PageRecord.project_id == project_id).order_by(PageRecord.sequence).all()
        visual_storytelling = bool((proj.settings or {}).get("visual_storytelling"))
        if visual_storytelling:
            # Discover non-story panel exclusions from coverage report or metadata
            excluded_pids = set()
            cov_path = workspace / "story" / "panels_coverage_report.json"
            if cov_path.exists():
                try:
                    cdata = json.loads(cov_path.read_text(encoding="utf-8"))
                    for it in cdata.get("items", []):
                        if it.get("classification") != "STORY_PANEL":
                            excluded_pids.add(it.get("panel_id"))
                except Exception:
                    pass
            panels = db.query(PanelRecord).filter(PanelRecord.project_id == project_id, PanelRecord.status != "IGNORED").order_by(PanelRecord.sequence).all()
            for panel in panels:
                if panel.id in excluded_pids:
                    continue
                crop = workspace / "panels" / panel.crop_filename
                if not crop.exists():
                    raise ValueError(f"Panel crop missing: {panel.id}. Regenerate panel crops before motion planning.")
                visual_sources.append(VisualSource(
                    asset_id=panel.id, panel_id=panel.id, page_id=panel.page_id,
                    sequence_global=panel.sequence, file_path=str(crop),
                    width=panel.width, height=panel.height,
                    panel_bounds=NormalizedRect(x=0, y=0, width=1, height=1),
                    provenance={"source_page": panel.page_id, "bbox": [panel.x, panel.y, panel.width, panel.height]},
                ))
        elif pages:
            for p in pages:
                page_img_path = workspace / "pages" / p.filename
                if not page_img_path.exists():
                    page_img_path = workspace / p.filename
                w = p.width or 1920
                h = p.height or 1080

                visual_sources.append(
                    VisualSource(
                        asset_id=f"page_{p.sequence:02d}",
                        panel_id=f"panel_{p.sequence:02d}",
                        page_id=p.id,
                        sequence_global=p.sequence,
                        file_path=str(page_img_path) if page_img_path.exists() else None,
                        width=w,
                        height=h,
                        panel_bounds=NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0),
                    )
                )
        else:
            # Fallback: scan workspace for images
            img_files = sorted(list(workspace.glob("*.jpg")) + list(workspace.glob("*.png")))
            for idx, f in enumerate(img_files, start=1):
                with Image.open(f) as im:
                    w, h = im.size
                visual_sources.append(
                    VisualSource(
                        asset_id=f"page_{idx:02d}",
                        panel_id=f"panel_{idx:02d}",
                        sequence_global=idx,
                        file_path=str(f),
                        width=w,
                        height=h,
                    )
                )

        if not visual_sources:
            raise ValueError("No visual source images found in project workspace.")

        # 4. Configure Style Profile
        style_factory = {
            "subtle": MotionStyleProfile.subtle,
            "cinematic": MotionStyleProfile.cinematic,
            "energetic": MotionStyleProfile.energetic,
            "minimal": MotionStyleProfile.minimal,
        }.get(style_preset.lower(), MotionStyleProfile.cinematic)
        style = style_factory()

        # 5. Build Scenes & Characters
        scenes = [
            SceneEntity(
                scene_id="scene_01",
                sequence=1,
                title="Main Sequence",
                summary="Primary motion narrative sequence.",
                panel_start="panel_01",
                panel_end=f"panel_{len(visual_sources):02d}",
                character_ids=["char_marcus"],
            )
        ]
        characters = [
            CharacterEntity(
                character_id="char_marcus",
                display_name="Marcus",
                canonical_name="Marcus",
                role=CharacterRole.PROTAGONIST,
            )
        ]

        beats = []
        if visual_storytelling:
            from engine.story.service import story_service
            narrative = story_service.get_narrative(db, project_id)
            if not narrative:
                raise ValueError("Chapter story missing; analyze and approve story first.")
            scenes, characters, beats = narrative.scenes, narrative.characters, narrative.beats
            # Keep chapter movement restrained regardless of legacy cinematic presets.
            style.max_zoom = min(style.max_zoom, 1.08)
            style.max_pan_distance = min(style.max_pan_distance, 0.08)
            style.effect_intensity = 0.0
            style.parallax_strength = 0.0

        # 6. Apply Overrides if supplied
        manual_overrides = None
        if overrides:
            manual_overrides = MotionOverrides.model_validate(overrides)

        input_data = MotionDirectorInput(
            project_id=project_id,
            script=script,
            visual_sources=visual_sources,
            master_audio_timeline=mat,
            scenes=scenes,
            beats=beats,
            characters=characters,
            target_resolution=TargetResolution.standard_1080p(),
            style_profile=style,
            manual_overrides=manual_overrides,
        )

        timeline = self.director.plan_visual_timeline(input_data, force_regenerate=True)

        # Save sidecar JSON
        motion_dir = workspace / "motion"
        motion_dir.mkdir(parents=True, exist_ok=True)
        vt_json_path = motion_dir / "visual_timeline.json"
        with open(vt_json_path, "w", encoding="utf-8") as f:
            f.write(timeline.model_dump_json(indent=2))

        # Persist record in SQLite
        rec = VisualTimelineRecord(
            project_id=project_id,
            status="DRAFT",
            total_duration=timeline.total_duration_sec,
            total_shots=timeline.total_shots,
            style_preset=style_preset,
            timeline_json=timeline.model_dump(),
            overrides_json=overrides or {},
        )
        db.add(rec)

        # Update project stage to SHOT_PLAN_GENERATED
        proj.current_stage = PipelineStage.SHOT_PLAN_GENERATED.value
        proj.updated_at = utc_now()
        db.commit()
        db.refresh(rec)

        return {
            "id": rec.id,
            "project_id": rec.project_id,
            "status": rec.status,
            "total_duration": timeline.total_duration_sec,
            "total_shots": timeline.total_shots,
            "style_preset": style_preset,
            "warnings_count": len(timeline.warnings),
            "timeline": timeline.model_dump(),
        }

    def approve_motion(self, db: Session, project_id: str) -> bool:
        record = (
            db.query(VisualTimelineRecord)
            .filter(VisualTimelineRecord.project_id == project_id)
            .order_by(VisualTimelineRecord.created_at.desc())
            .first()
        )
        if not record:
            raise ValueError("No visual timeline found to approve.")
        if record.status == "STALE":
            raise ValueError("Motion is stale; regenerate it from the current approved audio.")

        record.status = "APPROVED"
        record.updated_at = utc_now()

        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if proj:
            proj.current_stage = PipelineStage.MOTION_APPROVED.value
            proj.updated_at = utc_now()

        db.commit()
        return True


motion_service = MotionService()
