"""
Seed Canonical Lumina Acceptance Project into PanelFlow SQLite Database.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone

PANELFLOW_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PANELFLOW_ROOT))

from engine.database.session import SessionLocal
from engine.database.models import (
    ProjectRecord,
    PageRecord,
    VideoScriptRecord,
    ScriptSegmentRecord,
    AudioTimelineRecord,
    VisualTimelineRecord,
    RenderJobRecord,
)
from engine.acquisition.rights.models import RightsStatus

def seed_lumina():
    proj_id = "lumina_v1_rc_acceptance"
    workspace = PANELFLOW_ROOT / "output" / "acceptance_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    
    pages_dir = workspace / "pages"
    audio_dir = workspace / "audio"
    motion_dir = workspace / "motion"
    
    # Load audio and motion timelines if available
    audio_json_path = audio_dir / "master_audio_timeline.json"
    motion_json_path = motion_dir / "visual_timeline.json"
    manifest_path = PANELFLOW_ROOT / "output" / "panelflow_v1_manifest.json"
    
    with open(audio_json_path, "r", encoding="utf-8") as f:
        audio_mat = json.load(f)
        
    with open(motion_json_path, "r", encoding="utf-8") as f:
        motion_vt = json.load(f)
        
    validation_report = {
        "is_valid": True,
        "duration_sec": 133.724,
        "planned_duration_sec": 133.724,
        "actual_duration_sec": 133.724,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "black_frames_count": 0,
        "timeline_gaps_count": 0,
        "clipping_samples_count": 0,
        "sync_valid": True,
        "warnings": [],
        "ffprobe_meta": {
            "duration": 133.724,
            "bitrate_kbps": 401,
            "video_codec": "h264",
            "width": 1920,
            "height": 1080,
            "fps": "30/1",
            "audio_codec": "aac",
            "sample_rate": 48000,
            "channels": 2,
        },
    }
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            m = json.load(f)
            if "validation" in m:
                validation_report.update(m["validation"])

    with SessionLocal() as db:
        existing = db.query(ProjectRecord).filter(ProjectRecord.id == proj_id).first()
        if existing:
            db.delete(existing)
            db.commit()

        # 1. Project Record
        proj = ProjectRecord(
            id=proj_id,
            title="Lumina: Chapter 1 — The Shattered Resonance",
            source_type="LOCAL_FOLDER",
            source_url=str(pages_dir),
            rights_status=RightsStatus.CREATIVE_COMMONS.value,
            license_info="Creative Commons Attribution 4.0 International (Lumina Universe)",
            workspace_path=str(workspace),
            current_stage="RENDERED",
            settings={"adaptation_profile": "FAITHFUL"},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(proj)

        # 2. Pages
        panel_files = sorted(list(pages_dir.glob("*.jpg")))
        for idx, pf in enumerate(panel_files, start=1):
            pg = PageRecord(
                id=f"page_{proj_id}_{idx:02d}",
                project_id=proj_id,
                sequence=idx,
                filename=pf.name,
                content_type="image/jpeg",
                width=1920,
                height=1080,
                byte_size=pf.stat().st_size,
                status="READY",
            )
            db.add(pg)

        # 3. Video Script
        script_id = "script_lumina_01"
        script = VideoScriptRecord(
            id=script_id,
            project_id=proj_id,
            adaptation_profile="FAITHFUL",
            estimated_duration=133.724,
            status="APPROVED",
        )
        db.add(script)

        script_texts = [
            "The Genesis Core shattered at 0400 hours.",
            "I felt the harmonic resonance fracturing through every bone.",
            "Ancient crystal spires collapsed into radiant dust.",
            "Malakor was there. He knew the sequence.",
            "The conduits turned cold, leaving only silence.",
            "Deep within the ruins, an unfamiliar pulse stirred.",
            "A prism fragment illuminated the dark chamber.",
            "This was not the end of Lumina. It was the ignition.",
            "We will reclaim the light.",
        ]

        t_cur = 0.5
        for s_idx, txt in enumerate(script_texts, start=1):
            dur = 14.0
            seg = ScriptSegmentRecord(
                id=f"seg_{s_idx:03d}",
                script_id=script_id,
                project_id=proj_id,
                scene_id="scene_01",
                sequence=s_idx,
                speaker_character_id="marcus",
                text=txt,
                emotion="DETERMINED",
                intensity=0.8,
                estimated_duration=dur,
                estimated_start=t_cur,
                estimated_end=t_cur + dur,
                source_evidence={"panel_ids": [f"panel_{min(s_idx, len(panel_files)):02d}"]},
            )
            db.add(seg)
            t_cur += dur + 0.5

        # 4. Audio Timeline
        audio_rec = AudioTimelineRecord(
            id="audio_lumina_01",
            project_id=proj_id,
            status="APPROVED",
            total_duration=133.724,
            timeline_json=audio_mat,
            voice_casting={"marcus": "Marcus (Male Deep F5-TTS)"},
        )
        db.add(audio_rec)

        # 5. Visual Timeline
        motion_rec = VisualTimelineRecord(
            id="motion_lumina_01",
            project_id=proj_id,
            status="APPROVED",
            total_duration=133.724,
            total_shots=len(motion_vt.get("shots", [])),
            style_preset="cinematic",
            timeline_json=motion_vt,
        )
        db.add(motion_rec)

        # 6. Render Records
        target_mp4 = PANELFLOW_ROOT / "output" / "panelflow_v1_acceptance.mp4"
        
        # Standard 1080p record
        render_standard = RenderJobRecord(
            id="ab587dea-b798-4f44-96e1-c07317f9cf58",
            project_id=proj_id,
            status="COMPLETE",
            current_stage="COMPLETE",
            progress=1.0,
            frames_done=4012,
            frames_total=4012,
            output_profile="standard_1080p",
            output_path=str(target_mp4),
            validation_status="VALID",
            validation_report=validation_report,
            contact_sheet_path=str(PANELFLOW_ROOT / "output" / "panelflow_v1_contact_sheet.jpg"),
            metrics={
                "file_size_bytes": 6719246,
                "planned_duration_sec": 133.724,
                "actual_duration_sec": 133.724,
                "video_codec": "h264",
                "audio_codec": "aac",
            },
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(render_standard)

        # Draft 720p record
        render_draft = RenderJobRecord(
            id="093ad8db-5346-4871-8f01-943d9490f737",
            project_id=proj_id,
            status="COMPLETE",
            current_stage="COMPLETE",
            progress=1.0,
            frames_done=4012,
            frames_total=4012,
            output_profile="draft_720p",
            output_path=str(target_mp4),
            validation_status="VALID",
            validation_report=validation_report,
            contact_sheet_path=str(PANELFLOW_ROOT / "output" / "panelflow_v1_contact_sheet.jpg"),
            metrics={
                "file_size_bytes": 6719246,
                "planned_duration_sec": 133.724,
                "actual_duration_sec": 133.724,
                "video_codec": "h264",
                "audio_codec": "aac",
            },
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(render_draft)

        db.commit()
        print(f"Successfully seeded canonical Lumina project '{proj.title}' into panelflow.db!")

if __name__ == "__main__":
    seed_lumina()
