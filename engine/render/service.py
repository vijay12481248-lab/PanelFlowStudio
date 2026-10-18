"""
Render Service for PanelFlow Studio.
Manages render job creation, background execution, real-time progress events,
cancellation, validation auditing, and render history persistence.
"""
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
import json
import uuid
import threading
import time
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from engine.database.session import SessionLocal
from engine.database.models import (
    ProjectRecord,
    VisualTimelineRecord,
    AudioTimelineRecord,
    RenderJobRecord,
    PageRecord,
    PanelRecord,
)
from engine.acquisition.models.models import PipelineStage
from engine.motion.models.timeline import VisualTimeline
from engine.motion.models.input_contract import MasterAudioTimeline
from engine.render.engine import RenderEngine
from engine.render.models.profiles import RenderProfile
from engine.render.models.render_plan import RenderPlan, RenderAudioTrack
from engine.render.models.enums import MusicDurationPolicy, RenderStage, RenderStatus


def utc_now():
    return datetime.now(timezone.utc)


class RenderService:
    """
    Coordinates rendering execution, background thread lifecycle, progress broadcasting,
    cancellation, and post-render validation auditing.
    """

    def __init__(self):
        self.render_engine = RenderEngine()
        self._active_cancels: Dict[str, threading.Event] = {}
        self._active_progress: Dict[str, Dict[str, Any]] = {}
        self._subscribers: List[asyncio.Queue] = []
        self._cleanup_orphaned_jobs()

    def _cleanup_orphaned_jobs(self):
        try:
            with SessionLocal() as db:
                orphans = (
                    db.query(RenderJobRecord)
                    .filter(RenderJobRecord.status.in_([RenderStatus.QUEUED.value, RenderStatus.RUNNING.value]))
                    .all()
                )
                for o in orphans:
                    o.status = RenderStatus.FAILED.value
                    o.current_stage = "FAILED"
                    o.error_code = "ORPHANED_JOB"
                    o.error_message = "Engine process was restarted while render was in progress"
                    o.completed_at = utc_now()
                if orphans:
                    db.commit()
        except Exception:
            pass

    def get_render_job(self, db: Session, render_id: str) -> Optional[Dict[str, Any]]:
        job = db.query(RenderJobRecord).filter(RenderJobRecord.id == render_id).first()
        if not job:
            return None

        # Overlay real-time in-memory progress if currently active
        live = self._active_progress.get(render_id, {})
        val_rep = job.validation_report
        if isinstance(val_rep, str):
            try:
                val_rep = json.loads(val_rep)
            except Exception:
                pass

        return {
            "render_id": job.id,
            "project_id": job.project_id,
            "status": live.get("status", job.status),
            "current_stage": live.get("current_stage", job.current_stage),
            "progress": live.get("progress", job.progress),
            "frames_done": live.get("frames_done", job.frames_done),
            "frames_total": live.get("frames_total", job.frames_total),
            "elapsed_sec": live.get("elapsed_sec", 0.0),
            "output_profile": job.output_profile,
            "output_path": job.output_path,
            "error_code": job.error_code,
            "error_message": job.error_message,
            "validation_status": job.validation_status,
            "validation_report": val_rep,
            "render_plan_hash": job.render_plan_hash,
            "visual_timeline_hash": job.visual_timeline_hash,
            "master_audio_timeline_hash": job.master_audio_timeline_hash,
            "contact_sheet_path": job.contact_sheet_path,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def list_project_renders(self, db: Session, project_id: str) -> List[Dict[str, Any]]:
        jobs = (
            db.query(RenderJobRecord)
            .filter(RenderJobRecord.project_id == project_id)
            .order_by(RenderJobRecord.created_at.desc())
            .all()
        )
        res = []
        for j in jobs:
            val_rep = j.validation_report
            if isinstance(val_rep, str):
                try:
                    val_rep = json.loads(val_rep)
                except Exception:
                    pass

            item = {
                "render_id": j.id,
                "project_id": j.project_id,
                "status": j.status,
                "current_stage": j.current_stage,
                "progress": j.progress,
                "frames_done": j.frames_done,
                "frames_total": j.frames_total,
                "output_profile": j.output_profile,
                "output_path": j.output_path,
                "error_code": j.error_code,
                "error_message": j.error_message,
                "validation_status": j.validation_status,
                "validation_report": val_rep,
                "contact_sheet_path": j.contact_sheet_path,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            if j.id in self._active_progress:
                live = self._active_progress[j.id]
                item["status"] = live.get("status", item["status"])
                item["current_stage"] = live.get("current_stage", item["current_stage"])
                item["progress"] = live.get("progress", item["progress"])
                item["frames_done"] = live.get("frames_done", item["frames_done"])
                item["frames_total"] = live.get("frames_total", item["frames_total"])
                item["elapsed_sec"] = live.get("elapsed_sec")
            res.append(item)
        return res

    def preflight_check_timeline(self, db: Session, project_id: str, timeline_data: Dict[str, Any]) -> Dict[str, Any]:
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project not found: {project_id}")
        workspace = Path(proj.workspace_path)
        from engine.render.compiler import timeline_compiler
        return timeline_compiler.preflight_validate(timeline_data, project_id, workspace)

    def create_and_start_render_job(
        self,
        db: Session,
        project_id: str,
        profile_name: str = "standard_1080p",
        custom_output_path: Optional[str] = None,
        subtitle_enabled: bool = False,
        bgm_volume_db: float = -10.0,
        dialogue_gain_db: float = 0.0,
        is_draft: bool = False,
        timeline_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new RenderJobRecord and kicks off background rendering.
        Supports both direct StoryEditorState (Schema v2) and legacy database timeline records.
        """
        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project not found: {project_id}")

        # Check if an active render job is already running for this project
        active = (
            db.query(RenderJobRecord)
            .filter(
                RenderJobRecord.project_id == project_id,
                RenderJobRecord.status.in_([RenderStatus.QUEUED.value, RenderStatus.RUNNING.value]),
            )
            .first()
        )
        if active:
            if active.id in self._active_progress and self._active_progress[active.id].get("status") == "RUNNING":
                return self.get_render_job(db, active.id)
            else:
                active.status = RenderStatus.FAILED.value
                active.current_stage = "FAILED"
                active.error_code = "ORPHANED_JOB"
                active.error_message = "Engine process was restarted while render was in progress"
                active.completed_at = utc_now()
                db.commit()

        workspace = Path(proj.workspace_path)
        renders_dir = workspace / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)
        render_id = str(uuid.uuid4())

        # Resolve aspect ratio and profile
        aspect = "16:9"
        if timeline_data:
            aspect = timeline_data.get("aspect_ratio", "16:9")

        chosen_profile_name = "draft_720p" if is_draft else profile_name

        if chosen_profile_name == "vertical_shorts":
            profile = RenderProfile.vertical_shorts()
        elif chosen_profile_name == "square_feed":
            profile = RenderProfile.square_feed()
        elif chosen_profile_name == "draft_720p":
            if aspect == "9:16":
                profile = RenderProfile(width=720, height=1280, fps=30, crf=26, preset="ultrafast")
            elif aspect == "1:1":
                profile = RenderProfile(width=720, height=720, fps=30, crf=26, preset="ultrafast")
            else:
                profile = RenderProfile.draft_720p()
        elif aspect == "9:16":
            profile = RenderProfile.vertical_shorts()
        elif aspect == "1:1":
            profile = RenderProfile.square_feed()
        else:
            profile = RenderProfile.standard_1080p()

        if custom_output_path:
            out_file = Path(custom_output_path)
        else:
            out_file = renders_dir / f"{proj.title.replace(' ', '_').lower()}_{chosen_profile_name}_{render_id[:8]}.mp4"

        # Check if timeline_data is passed directly from Video-First Story Editor
        if timeline_data and timeline_data.get("scenes"):
            from engine.render.compiler import timeline_compiler
            plan = timeline_compiler.compile(
                state=timeline_data,
                project_id=project_id,
                workspace_path=workspace,
                profile=profile,
                subtitle_enabled=subtitle_enabled,
                bgm_volume_db=bgm_volume_db,
                dialogue_gain_db=dialogue_gain_db,
            )
            vt_hash = f"story_editor_v2_{render_id[:8]}"
            mat_hash = f"audio_story_editor_{render_id[:8]}"
        else:
            # 1. Load active Visual Timeline from DB
            vt_rec = (
                db.query(VisualTimelineRecord)
                .filter(VisualTimelineRecord.project_id == project_id)
                .order_by(VisualTimelineRecord.created_at.desc())
                .first()
            )
            if not vt_rec:
                raise ValueError("No VisualTimeline found. Supply editor timeline or complete motion planning first.")
            if vt_rec.status != "APPROVED":
                raise ValueError("Approve the current motion timeline before rendering.")

            vt = VisualTimeline.model_validate(vt_rec.timeline_json)

            # 2. Load active Audio Timeline from DB
            at_rec = (
                db.query(AudioTimelineRecord)
                .filter(AudioTimelineRecord.project_id == project_id)
                .order_by(AudioTimelineRecord.created_at.desc())
                .first()
            )
            if not at_rec:
                raise ValueError("No MasterAudioTimeline found. Complete audio generation first.")
            if at_rec.status != "APPROVED":
                raise ValueError("Approve the current audio timeline before rendering.")

            mat = MasterAudioTimeline.model_validate(at_rec.timeline_json)

            # 4. Resolve source visual paths map
            assets_map = {}
            pages = db.query(PageRecord).filter(PageRecord.project_id == project_id).order_by(PageRecord.sequence).all()
            for p in pages:
                candidates = [
                    workspace / "normalized" / p.filename,
                    workspace / "source" / p.filename,
                    workspace / "pages" / p.filename,
                    workspace / p.filename,
                ]
                img_p = next((c for c in candidates if c.exists()), candidates[-1])
                assets_map[f"page_{p.sequence:02d}"] = str(img_p)

            for panel in db.query(PanelRecord).filter(PanelRecord.project_id == project_id).all():
                if panel.crop_filename:
                    crop_path = workspace / "panels" / panel.crop_filename
                    if crop_path.exists():
                        assets_map[panel.id] = str(crop_path)
                        assets_map[f"panel_{panel.sequence:04d}"] = str(crop_path)
                        assets_map[f"panel_{panel.sequence}"] = str(crop_path)

            # If any panel file was removed/missing, fallback to first available story panel
            available_panels = sorted(list((workspace / "panels").glob("panel_*.jpg")))
            default_panel = str(available_panels[0].resolve()) if available_panels else ""

            storyboard_p = workspace / "story" / "storyboard.json"
            if storyboard_p.exists():
                try:
                    sb_data = json.loads(storyboard_p.read_text(encoding="utf-8"))
                    for seg in sb_data.get("segments", []):
                        for sp in seg.get("supporting_panels", []):
                            pid = sp.get("panel_id")
                            cf = sp.get("crop_filename")
                            if pid:
                                cp = workspace / "panels" / cf if cf else None
                                assets_map[pid] = str(cp) if (cp and cp.exists()) else default_panel
                except Exception:
                    pass

            coverage_p = workspace / "story" / "panels_coverage_report.json"
            if coverage_p.exists():
                try:
                    cov_data = json.loads(coverage_p.read_text(encoding="utf-8"))
                    for item in cov_data.get("items", []):
                        pid = item.get("panel_id")
                        img_name = item.get("source_image") or item.get("crop_filename")
                        if pid and pid not in assets_map:
                            cp = workspace / "panels" / img_name if img_name else None
                            assets_map[pid] = str(cp) if (cp and cp.exists()) else default_panel
                except Exception:
                    pass

            # Ensure every shot in visual timeline resolves to a valid file
            for s in vt.all_shots():
                cur_target = assets_map.get(s.source_asset_id)
                if not cur_target or not Path(cur_target).exists():
                    if default_panel:
                        assets_map[s.source_asset_id] = default_panel

            # 5. Resolve background music
            bgm_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "cinematics" / "intro" / "audio" / "someone_stayed_ace_master.ogg"
            if not bgm_path.exists():
                bgm_path = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "cinematics" / "intro" / "audio" / "someone_stayed_chamber.wav"

            if (proj.settings or {}).get("visual_storytelling"):
                bgm_path = Path((proj.settings or {}).get("chapter_music_path") or workspace / "audio" / "chapter_music.wav")
            sfx_tracks = []
            audio_plan_path = workspace / "audio" / "chapter_audio_plan.json"
            if (proj.settings or {}).get("visual_storytelling") and audio_plan_path.exists():
                import soundfile as sf
                audio_plan = json.loads(audio_plan_path.read_text(encoding="utf-8"))
                if audio_plan.get("music", {}).get("path"):
                    bgm_path = Path(audio_plan["music"]["path"])
                for cue in audio_plan.get("sfx", []):
                    cue_path = Path(cue["path"])
                    if cue_path.is_file():
                        sfx_tracks.append(RenderAudioTrack(
                            track_type="sfx", file_path=str(cue_path), start_time=cue["time"],
                            end_time=min(mat.total_duration_sec, cue["time"] + sf.info(str(cue_path)).duration),
                            gain_db=cue.get("gain_db", -12.0),
                        ))

            # Compile RenderPlan
            plan = self.render_engine.compile_render_plan(
                timeline=vt,
                master_audio=mat,
                source_assets_map=assets_map,
                bgm_path=str(bgm_path) if bgm_path.exists() else None,
                profile=profile,
                music_policy=MusicDurationPolicy.LOOP,
                sfx_tracks=sfx_tracks,
                subtitle_enabled=subtitle_enabled,
            )
            vt_hash = vt.hash or vt.timeline_id
            mat_hash = mat.timeline_id

        # Preflight verification
        ready, issues = self.render_engine.preflight_check(plan)
        if not ready:
            raise RuntimeError(f"Preflight check failed: {'; '.join(issues)}")

        # Create RenderJobRecord
        record = RenderJobRecord(
            id=render_id,
            project_id=project_id,
            status=RenderStatus.QUEUED.value,
            current_stage=RenderStage.PREPARING.value,
            progress=0.0,
            frames_done=0,
            frames_total=plan.total_frames,
            output_profile=chosen_profile_name,
            output_path=str(out_file),
            render_plan_hash=plan.hash,
            visual_timeline_hash=vt_hash,
            master_audio_timeline_hash=mat_hash,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        # Register cancel event
        cancel_evt = threading.Event()
        self._active_cancels[render_id] = cancel_evt

        # Initialize live progress state
        self._active_progress[render_id] = {
            "status": "QUEUED",
            "current_stage": "PREPARING",
            "progress": 0.0,
            "frames_done": 0,
            "frames_total": plan.total_frames,
            "elapsed_sec": 0.0,
        }

        # Spawn background execution thread
        t = threading.Thread(
            target=self._run_render_worker,
            args=(render_id, project_id, plan, out_file, cancel_evt),
            daemon=True,
        )
        t.start()

        return self.get_render_job(db, render_id)

    def cancel_render_job(self, db: Session, render_id: str) -> bool:
        cancel_evt = self._active_cancels.get(render_id)
        if cancel_evt:
            cancel_evt.set()

        job = db.query(RenderJobRecord).filter(RenderJobRecord.id == render_id).first()
        if job and job.status not in (RenderStatus.COMPLETE.value, RenderStatus.FAILED.value):
            job.status = RenderStatus.CANCELLED.value
            job.current_stage = "CANCELLED"
            job.completed_at = utc_now()
            job.error_message = "Render was cancelled by user request"
            db.commit()

            if render_id in self._active_progress:
                self._active_progress[render_id]["status"] = "CANCELLED"
                self._active_progress[render_id]["current_stage"] = "CANCELLED"
            return True
        return False

    def _run_render_worker(
        self,
        render_id: str,
        project_id: str,
        plan: RenderPlan,
        output_file: Path,
        cancel_evt: threading.Event,
    ):
        """Worker thread executing frame piping, audio mixing, and post-render validation."""
        start_time = time.time()
        if hasattr(self.render_engine, "composer") and hasattr(self.render_engine.composer, "clear_cache"):
            self.render_engine.composer.clear_cache()

        def cancel_check() -> bool:
            return cancel_evt.is_set()

        def progress_cb(stage: RenderStage, frames_done: int, total_frames: int, pct: float):
            elapsed = time.time() - start_time
            state = {
                "render_id": render_id,
                "project_id": project_id,
                "status": "RUNNING" if stage != RenderStage.COMPLETE else "COMPLETE",
                "current_stage": stage.value,
                "progress": pct,
                "frames_done": frames_done,
                "frames_total": total_frames,
                "elapsed_sec": round(elapsed, 1),
            }
            self._active_progress[render_id] = state
            self._broadcast_event(state)

        try:
            with SessionLocal() as db:
                job = db.query(RenderJobRecord).filter(RenderJobRecord.id == render_id).first()
                if job:
                    job.status = RenderStatus.RUNNING.value
                    job.current_stage = RenderStage.COMPOSING.value
                    job.started_at = utc_now()
                    db.commit()

            workspace_dir = output_file.parent / f"work_{render_id[:8]}"
            audit_report = self.render_engine.execute_render(
                plan=plan,
                output_mp4_path=output_file,
                workspace_dir=workspace_dir,
                progress_cb=progress_cb,
                cancel_token=cancel_check,
            )

            # Update DB with final audit
            with SessionLocal() as db:
                job = db.query(RenderJobRecord).filter(RenderJobRecord.id == render_id).first()
                proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()

                if cancel_evt.is_set():
                    if job:
                        job.status = RenderStatus.CANCELLED.value
                        job.current_stage = "CANCELLED"
                        job.completed_at = utc_now()
                        db.commit()
                    return

                if audit_report.is_valid:
                    if job:
                        job.status = RenderStatus.COMPLETE.value
                        job.current_stage = "COMPLETE"
                        job.progress = 100.0
                        job.frames_done = plan.total_frames
                        job.completed_at = utc_now()
                        job.validation_status = "VALID"
                        rep_dict = audit_report.model_dump()
                        qf = rep_dict.get("quality_flags", {})
                        rep_dict["duration_sec"] = audit_report.actual_duration_sec
                        rep_dict["black_frames_count"] = qf.get("black_frames", 0)
                        rep_dict["timeline_gaps_count"] = qf.get("timeline_gaps", 0)
                        rep_dict["clipping_samples_count"] = qf.get("audio_clipping_events", 0)
                        rep_dict["sync_valid"] = qf.get("av_sync_offset_ms", 0) == 0
                        job.validation_report = rep_dict
                        job.contact_sheet_path = audit_report.contact_sheet_path
                        job.metrics = {
                            "file_size_bytes": audit_report.file_size_bytes,
                            "planned_duration_sec": audit_report.planned_duration_sec,
                            "actual_duration_sec": audit_report.actual_duration_sec,
                            "video_codec": audit_report.ffprobe_meta.get("video_codec"),
                            "audio_codec": audit_report.ffprobe_meta.get("audio_codec"),
                        }
                    if proj:
                        proj.current_stage = PipelineStage.RENDERED.value
                        proj.updated_at = utc_now()
                    db.commit()

                    if render_id in self._active_progress:
                        self._active_progress[render_id]["status"] = "COMPLETE"
                        self._active_progress[render_id]["current_stage"] = "COMPLETE"
                        self._active_progress[render_id]["progress"] = 100.0

                else:
                    if job:
                        job.status = RenderStatus.FAILED.value
                        job.current_stage = "FAILED"
                        job.completed_at = utc_now()
                        job.validation_status = "INVALID"
                        job.validation_report = audit_report.model_dump()
                        job.error_code = "VALIDATION_FAILED"
                        job.error_message = "; ".join(audit_report.warnings)
                        db.commit()

        except Exception as e:
            with SessionLocal() as db:
                job = db.query(RenderJobRecord).filter(RenderJobRecord.id == render_id).first()
                if job:
                    if cancel_evt.is_set():
                        job.status = RenderStatus.CANCELLED.value
                        job.current_stage = "CANCELLED"
                        job.completed_at = utc_now()
                        job.error_message = "Render was cancelled by user request"
                    else:
                        job.status = RenderStatus.FAILED.value
                        job.current_stage = "FAILED"
                        job.completed_at = utc_now()
                        job.error_code = "ENCODE_EXCEPTION"
                        job.error_message = str(e)
                    db.commit()

            if render_id in self._active_progress:
                if cancel_evt.is_set():
                    self._active_progress[render_id]["status"] = "CANCELLED"
                    self._active_progress[render_id]["current_stage"] = "CANCELLED"
                else:
                    self._active_progress[render_id]["status"] = "FAILED"
                    self._active_progress[render_id]["error_message"] = str(e)

        finally:
            self._active_cancels.pop(render_id, None)

    def _broadcast_event(self, event: Dict[str, Any]):
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass

    def subscribe(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self._subscribers:
            self._subscribers.remove(q)


render_service = RenderService()
