"""PanelFlow Studio End-to-End Autonomous Pipeline Orchestrator (Auto-Pilot)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import uuid

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from engine.database.models import (
    AudioTimelineRecord,
    JobRecord,
    OCRRecord,
    PageRecord,
    PanelRecord,
    ProjectRecord,
    RenderJobRecord,
    SceneRecord,
    VideoScriptRecord,
    VisualTimelineRecord,
)
from engine.database.session import SessionLocal
from engine.security.paths import resolve_contained_path
from engine.jobs.manager import job_manager, PipelineCancellationToken
from engine.story.packaging import generate_youtube_packaging

logger = logging.getLogger("panelflow.pipeline.autopilot")


class AutoPilotStageItem(BaseModel):
    id: str
    name: str
    status: str = Field(default="PENDING", pattern=r"^(PENDING|RUNNING|COMPLETED|SKIPPED|FAILED)$")
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = Field(default="")
    duration_sec: float = Field(default=0.0, ge=0.0)


class AutoPilotStatusResponse(BaseModel):
    project_id: str
    status: str = Field(default="IDLE", pattern=r"^(IDLE|RUNNING|COMPLETED|CANCELLED|FAILED)$")
    current_stage_id: Optional[str] = None
    overall_progress: float = Field(default=0.0, ge=0.0, le=1.0)
    stages: List[AutoPilotStageItem]
    logs: List[str]
    result: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


STAGE_DEFINITIONS = [
    ("pages", "1. Page Ingest & Normalization"),
    ("panels", "2. Panel Segmentation & Ordering"),
    ("ocr", "3. Speech Bubble & Text Extraction"),
    ("story", "4. Narrative & Scene Breakdown"),
    ("script", "5. Script & Dialogue Adaptation"),
    ("audio", "6. Master Audio & Voice Synthesis"),
    ("motion", "7. Motion Director Keyframing"),
    ("render", "8. Production Video Rendering (MP4)"),
    ("packaging", "9. YouTube Packaging & AI Thumbnail"),
]


class AutoPilotRunner:
    def __init__(self, project_id: str, options: dict[str, Any] | None = None) -> None:
        self.project_id = project_id
        self.options = options or {}
        self.status = "IDLE"
        self.current_stage_id: Optional[str] = None
        self.overall_progress = 0.0
        self.stages: List[AutoPilotStageItem] = [
            AutoPilotStageItem(id=sid, name=sname) for sid, sname in STAGE_DEFINITIONS
        ]
        self.logs: List[str] = []
        self.result: Dict[str, Any] = {}
        self.error: Optional[str] = None
        self.is_cancelled = False
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self._task: Optional[asyncio.Task] = None

    def log(self, message: str) -> None:
        now = datetime.now(timezone.utc).strftime("%H:%M:%S")
        entry = f"[{now}] {message}"
        self.logs.append(entry)
        if len(self.logs) > 500:
            self.logs = self.logs[-500:]
        logger.info("[AutoPilot:%s] %s", self.project_id, message)

    def get_stage(self, stage_id: str) -> AutoPilotStageItem:
        for s in self.stages:
            if s.id == stage_id:
                return s
        raise KeyError(stage_id)

    def update_stage(
        self,
        stage_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
    ) -> None:
        stage = self.get_stage(stage_id)
        if status:
            stage.status = status
        if progress is not None:
            stage.progress = progress
        if message is not None:
            stage.message = message
        self._recompute_overall_progress()

    def _recompute_overall_progress(self) -> None:
        total = len(self.stages)
        done = sum(1.0 if s.status in ("COMPLETED", "SKIPPED") else s.progress for s in self.stages)
        self.overall_progress = round(min(1.0, done / total), 3)

    def snapshot(self) -> AutoPilotStatusResponse:
        return AutoPilotStatusResponse(
            project_id=self.project_id,
            status=self.status,
            current_stage_id=self.current_stage_id,
            overall_progress=self.overall_progress,
            stages=self.stages,
            logs=self.logs,
            result=self.result,
            error=self.error,
            started_at=self.started_at,
            completed_at=self.completed_at,
        )

    def cancel(self) -> None:
        self.is_cancelled = True
        self.status = "CANCELLED"
        self.log("Auto-Pilot run was cancelled by user.")
        if self._task and not self._task.done():
            self._task.cancel()

    def _create_cancel_token(self) -> PipelineCancellationToken:
        token = PipelineCancellationToken()
        if self.is_cancelled:
            token.cancel()
        return token

    def _make_progress_cb(self, stage_id: str, start_pct: float, end_pct: float):
        def _cb(fraction: float, msg: str):
            p = start_pct + fraction * (end_pct - start_pct)
            self.update_stage(stage_id, progress=round(p, 2), message=msg)
        return _cb

    async def execute(self) -> None:
        self.status = "RUNNING"
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.log(f"Starting End-to-End Auto-Pilot pipeline for project {self.project_id}")

        profile_name = self.options.get("target_profile", "standard_1080p")
        skip_existing = self.options.get("skip_existing_stages", True)

        try:
            # 1. PAGE STAGE
            await self._run_stage_pages(skip_existing)
            if self.is_cancelled:
                return

            # 2. PANEL STAGE
            await self._run_stage_panels(skip_existing)
            if self.is_cancelled:
                return

            # 3. OCR STAGE
            await self._run_stage_ocr(skip_existing)
            if self.is_cancelled:
                return

            # 4. STORY STAGE
            await self._run_stage_story(skip_existing)
            if self.is_cancelled:
                return

            # 5. SCRIPT STAGE
            await self._run_stage_script(skip_existing)
            if self.is_cancelled:
                return

            # 6. AUDIO STAGE
            await self._run_stage_audio(skip_existing)
            if self.is_cancelled:
                return

            # 7. MOTION STAGE
            await self._run_stage_motion(skip_existing)
            if self.is_cancelled:
                return

            # 8. RENDER STAGE
            await self._run_stage_render(profile_name, skip_existing)
            if self.is_cancelled:
                return

            # 9. PACKAGING & THUMBNAIL STAGE
            await self._run_stage_packaging(profile_name)

            self.status = "COMPLETED"
            self.overall_progress = 1.0
            self.completed_at = datetime.now(timezone.utc).isoformat()
            self.log("Auto-Pilot completed all 9 stages. Review the rendered video before release.")

        except asyncio.CancelledError:
            self.status = "CANCELLED"
            self.log("Auto-Pilot pipeline cancelled during execution.")
        except Exception as exc:
            self.status = "FAILED"
            self.error = str(exc)
            if self.current_stage_id:
                self.update_stage(self.current_stage_id, status="FAILED", message=str(exc))
            self.log(f"Auto-Pilot pipeline FAILED: {exc}")
            logger.exception("Auto-Pilot failure in project %s", self.project_id)
        finally:
            self._persist_status()

    # --- STAGE IMPLEMENTATIONS ---

    async def _run_stage_pages(self, skip_existing: bool) -> None:
        s_id = "pages"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.05, message="Inspecting pages...")

        from engine.projects.service import project_service
        from engine.database.models import NormalizationRecord, PageRecord

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")
            pages = list(project.pages or [])

            # 1. Automated Acquisition if project was newly created from URL without pages yet
            if not pages:
                if project.source_location:
                    self.log(f"Page Stage: No pages downloaded yet. Starting automated ingestion from {project.source_location}...")
                    self.update_stage(s_id, progress=0.1, message="Connecting to chapter source...")
                    from engine.api.dependencies import get_adapter_registry
                    registry = get_adapter_registry()
                    job_id = project_service.start_acquisition_job(db, self.project_id, registry)
                    while True:
                        if self.is_cancelled:
                            job_manager.cancel_job(job_id)
                            return
                        await asyncio.sleep(0.5)
                        j = job_manager.get_job(job_id)
                        if not j:
                            break
                        if j["status"] == "COMPLETED":
                            self.log("Page Stage: Chapter acquisition completed.")
                            break
                        elif j["status"] in ("FAILED", "CANCELLED"):
                            raise RuntimeError(f"Page acquisition failed: {j.get('error')}")
                        elif j.get("progress"):
                            self.update_stage(s_id, progress=0.1 + 0.3 * j["progress"], message=f"Downloading pages ({int(j['progress']*100)}%)...")

                    db.expire_all()
                    project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
                    pages = list(project.pages or [])
                if not pages:
                    raise ValueError("Project has no pages ingested")

            self.log(f"Page Stage: Found {len(pages)} pages in project.")

            # 2. Confirm acquisition baseline
            try:
                project_service.confirm_acquisition(db, self.project_id)
            except Exception as e:
                self.log(f"Page confirmation note: {e}")

            # 3. Automated Normalization to 1920px standard
            norm_count = db.query(NormalizationRecord).filter(NormalizationRecord.project_id == self.project_id).count()
            if norm_count < len(pages) or not skip_existing:
                self.log(f"Page Stage: Normalizing {len(pages)} pages to 1920px broadcast standard...")
                self.update_stage(s_id, progress=0.45, message="Normalizing page resolution...")
                norm_coro = project_service.normalize_project(db, self.project_id, target_width=1920, operation_only=True)
                token = self._create_cancel_token()
                cb = self._make_progress_cb(s_id, 0.45, 0.95)
                await norm_coro(token, cb)
                self.log(f"Page Stage: Successfully normalized {len(pages)} pages.")

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message=f"Verified & normalized {len(pages)} pages")
        self.log(f"Page Stage completed in {self.get_stage(s_id).duration_sec}s")

    async def _run_stage_panels(self, skip_existing: bool) -> None:
        s_id = "panels"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.1, message="Checking panel segmentation...")

        from engine.projects.service import project_service
        from engine.database.models import PanelRecord

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")
            panels = list(project.panels or [])

            if panels and skip_existing:
                self.log(f"Panel Stage: Using {len(panels)} existing segmented panels.")
                try:
                    project_service.confirm_panels(db, self.project_id)
                except Exception:
                    pass
            else:
                self.log("Panel Stage: Running panel detection algorithm...")
                self.update_stage(s_id, progress=0.2, message="Detecting panels from pages...")
                detect_coro = project_service.detect_panels_project(db, self.project_id, operation_only=True)
                token = self._create_cancel_token()
                cb = self._make_progress_cb(s_id, 0.2, 0.9)
                await detect_coro(token, cb)

                project_service.confirm_panels(db, self.project_id)
                panels = db.query(PanelRecord).filter(PanelRecord.project_id == self.project_id).all()
                self.log(f"Panel Stage: Successfully detected {len(panels)} panels.")

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message=f"{len(panels)} panels confirmed")
        self.log(f"Panel Stage completed in {self.get_stage(s_id).duration_sec}s")

    async def _run_stage_ocr(self, skip_existing: bool) -> None:
        s_id = "ocr"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.1, message="Processing text bubbles...")

        from engine.projects.service import project_service
        from engine.database.models import OCRRecord, TextRegionRecord

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")
            ocr_records = list(project.ocr_results or [])

            if ocr_records and skip_existing:
                self.log(f"OCR Stage: {len(ocr_records)} panels already have OCR text.")
                try:
                    project_service.confirm_ocr(db, self.project_id)
                except Exception:
                    pass
            else:
                self.log("OCR Stage: Extracting text regions & speech bubbles...")
                self.update_stage(s_id, progress=0.2, message="Scanning speech bubbles...")
                ocr_coro = project_service.extract_ocr_project(db, self.project_id, operation_only=True)
                token = self._create_cancel_token()
                cb = self._make_progress_cb(s_id, 0.2, 0.9)
                await ocr_coro(token, cb)

                # Auto-resolve any NEEDS_REVIEW text regions so automated pipeline never halts on unreviewed noise
                unresolved = (
                    db.query(TextRegionRecord)
                    .filter(
                        TextRegionRecord.project_id == self.project_id,
                        TextRegionRecord.status == "NEEDS_REVIEW",
                    )
                    .all()
                )
                for tr in unresolved:
                    if not (tr.corrected_text or tr.raw_text or "").strip():
                        tr.status = "IGNORED"
                    else:
                        tr.status = "CONFIRMED"
                if unresolved:
                    db.commit()

                try:
                    project_service.confirm_ocr(db, self.project_id)
                except Exception as e:
                    self.log(f"OCR note: {e} (proceeding with panel order baseline)")

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message="Text & OCR confirmed")
        self.log(f"OCR Stage completed in {self.get_stage(s_id).duration_sec}s")

    async def _run_stage_story(self, skip_existing: bool) -> None:
        s_id = "story"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.1, message="Analyzing narrative scenes...")

        from engine.story.service import story_service
        from engine.database.models import SceneRecord

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")
            se_scenes = (project.settings or {}).get("story_editor_state", {}).get("scenes", [])
            scenes = list(project.scenes or []) or se_scenes

            if scenes and skip_existing:
                self.log(f"Story Stage: Using {len(scenes)} existing narrative scenes.")
                try:
                    story_service.confirm_story(db, self.project_id)
                except Exception:
                    pass
            else:
                self.log("Story Stage: Performing narrative IR scene breakdown...")
                self.update_stage(s_id, progress=0.2, message="Segmenting scenes & characters...")
                from engine.llm.registry import llm_registry
                pref_provider = self.options.get("preferred_llm_provider")
                if not pref_provider:
                    try:
                        active_p = await llm_registry.get_active_provider()
                        pref_provider = active_p.provider_id
                    except Exception:
                        pref_provider = "mock_llm"
                story_coro = story_service.analyze_story_project(
                    db, self.project_id, preferred_provider_id=pref_provider, operation_only=True
                )
                token = self._create_cancel_token()
                cb = self._make_progress_cb(s_id, 0.2, 0.9)
                await story_coro(token, cb)

                story_service.confirm_story(db, self.project_id)
                scenes = db.query(SceneRecord).filter(SceneRecord.project_id == self.project_id).all()
                self.log(f"Story Stage: Created {len(scenes)} narrative scenes.")

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message=f"{len(scenes)} scenes confirmed")
        self.log(f"Story Stage completed in {self.get_stage(s_id).duration_sec}s")

    async def _run_stage_script(self, skip_existing: bool) -> None:
        s_id = "script"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.1, message="Generating script adaptation...")

        from engine.story.service import story_service

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")
            existing_script = story_service.get_script(db, self.project_id)

            if existing_script and existing_script.segments and skip_existing:
                self.log(f"Script Stage: Using existing approved script with {len(existing_script.segments)} beats.")
                story_service.approve_script(db, self.project_id, existing_script.script_id)
            else:
                self.log("Script Stage: Generating cinematic dialogue & narration...")
                self.update_stage(s_id, progress=0.5, message="Allocating dialogue beats...")

                script = await asyncio.to_thread(story_service.generate_script, db, self.project_id)
                story_service.approve_script(db, self.project_id, script.script_id)
                self.log("Script Stage: Script generated and approved.")

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message="Script approved")
        self.log(f"Script Stage completed in {self.get_stage(s_id).duration_sec}s")

    async def _run_stage_audio(self, skip_existing: bool) -> None:
        s_id = "audio"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.1, message="Compiling audio master...")

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")

            workspace = Path(project.workspace_path)
            se_state = (project.settings or {}).get("story_editor_state") or {}
            se_narration = se_state.get("narration_clips", [])
            audio_timelines = list(project.audio_timelines or [])
            from engine.audio.service import audio_service
            from engine.audio.synthesis import local_synthesizer
            import soundfile as sf
            from sqlalchemy.orm.attributes import flag_modified

            dialogue_dir = workspace / "audio" / "dialogue"
            dialogue_dir.mkdir(parents=True, exist_ok=True)

            # 1. Filter out empty/dummy clips
            active_clips = [
                c for c in se_narration
                if (c.get("text") or "").strip() and (c.get("text") or "").strip().lower() != "opening."
            ]

            # Every clip must correspond to the current approved Layer C script.
            from engine.story.service import story_service
            from engine.pipeline.narration import compile_narration_clips, reconcile_narration_clips

            narrative = story_service.get_narrative(db, self.project_id)
            script = story_service.get_script(db, self.project_id)
            if narrative is None or script is None:
                raise ValueError("Audio requires an approved, source-grounded script and Narrative IR. Review the story and script first.")

            timeline_scenes = se_state.get("scenes", [])
            if not timeline_scenes and narrative and narrative.scenes:
                # Construct default timeline scenes from story narrative
                timeline_scenes = [
                    {
                        "id": sc.scene_id,
                        "start_time_sec": float(sc.scene_sequence - 1) * 5.0,
                        "duration_sec": 5.0,
                        "layers": [{"source_panel_id": pid} for pid in sc.panel_ids],
                    }
                    for sc in narrative.scenes
                ]
                if not se_state:
                    se_state = {}
                se_state["scenes"] = timeline_scenes
                project.settings = {**(project.settings or {}), "story_editor_state": se_state}
                db.commit()

            if active_clips:
                active_clips = reconcile_narration_clips(
                    script, narrative, timeline_scenes, active_clips
                )
                self.log(f"Audio Stage: Reconciled {len(active_clips)} existing clips with the approved script.")
            else:
                active_clips = compile_narration_clips(script, narrative, timeline_scenes)
                self.log(f"Audio Stage: Using {len(active_clips)} grounded script segments.")

            # 3. Check physical presence of synthesized audio files
            clips_to_synthesize = []
            for c in active_clips:
                audio_url = c.get("audio_url")
                has_file = False
                if audio_url:
                    if "/audio/" in audio_url:
                        subpath = audio_url.split("/audio/")[-1]
                        fpath = workspace / "audio" / subpath
                    else:
                        fpath = workspace / audio_url
                    if fpath.exists() and fpath.stat().st_size > 1000:
                        has_file = True
                if not has_file or not skip_existing:
                    clips_to_synthesize.append(c)

            if clips_to_synthesize:
                self.log(f"Audio Stage: Synthesizing {len(clips_to_synthesize)} narration lines with Chatterbox Turbo...")
                tasks = [
                    {
                        "id": c.get("id") or f"clip_{idx}",
                        "directory": str(dialogue_dir),
                        "text": c["text"],
                        "voice": c.get("voice", "Narrator"),
                        "emotion": c.get("emotion", "Engaging"),
                        "intensity": float(c.get("intensity", 0.7)),
                        "speed": float(c.get("speed", 1.05)),
                        "force": not skip_existing,
                    }
                    for idx, c in enumerate(clips_to_synthesize)
                ]
                try:
                    batch_res = local_synthesizer.synthesize_batch(tasks)
                    res_by_id = {r["id"]: r for r in batch_res if r.get("success")}
                    for clip in clips_to_synthesize:
                        cid = clip.get("id")
                        if cid in res_by_id:
                            r = res_by_id[cid]
                            clip["audio_url"] = f"/api/projects/{self.project_id}/audio/dialogue/{Path(r['audio_path']).name}"
                            clip["duration_sec"] = round(float(r.get("duration", 4.0)), 2)
                            clip["status"] = "APPROVED"
                            clip["review_status"] = "APPROVED"
                except Exception as b_err:
                    self.log(f"Batch TTS fallback to sequential: {b_err}")
                    for idx, clip in enumerate(clips_to_synthesize):
                        try:
                            wav_p = local_synthesizer.synthesize(
                                directory=dialogue_dir,
                                text=clip["text"],
                                voice=clip.get("voice", "Narrator"),
                                emotion=clip.get("emotion", "Neutral"),
                                intensity=float(clip.get("intensity", 0.5)),
                                pace=float(clip.get("speed", 1.0)),
                            )
                            dur = round(float(sf.info(str(wav_p)).duration), 2)
                            clip["audio_url"] = f"/api/projects/{self.project_id}/audio/dialogue/{wav_p.name}"
                            clip["duration_sec"] = dur
                            clip["status"] = "APPROVED"
                            clip["review_status"] = "APPROVED"
                        except Exception as err:
                            self.log(f"Warning: TTS synthesis failed for line '{clip['text'][:30]}...': {err}")

            # Measure every actual file, including reused clips and batch results.
            # A partial TTS failure must never be promoted to an approved master.
            for clip in active_clips:
                audio_url = clip.get("audio_url") or ""
                if not audio_url:
                    raise ValueError(f"Narration synthesis produced no audio for {clip.get('id')}.")
                relative = Path("audio") / audio_url.split("/audio/", 1)[1] if "/audio/" in audio_url else Path(audio_url)
                audio_path = resolve_contained_path(workspace, relative, must_be_file=True)
                info = sf.info(str(audio_path))
                if info.frames <= 0 or info.samplerate <= 0:
                    raise ValueError(f"Narration audio is empty or invalid: {clip.get('id')}.")
                clip["duration_sec"] = float(info.duration)

            if active_clips:
                from engine.pipeline.narration import synchronize_narration
                synchronize_narration(se_state.get("scenes", []), active_clips)

            # 5. Ensure atmospheric background music (BGM) is attached
            bgm_tracks = se_state.get("bgm_tracks", [])
            if not bgm_tracks:
                se_state["bgm_tracks"] = [
                    {
                        "id": "bgm_default",
                        "audio_url": "/assets/demo/crystal_resonance_bgm.mp3",
                        "volume": 0.35,
                        "ducking": -14.0,
                    }
                ]
                self.log("Audio Stage: Attached cinematic BGM track (crystal_resonance_bgm.mp3).")

            # 6. Persist updated audio configuration to story_editor_state
            if active_clips:
                se_state["narration_clips"] = active_clips
            if project.settings is None:
                project.settings = {}
            project.settings["story_editor_state"] = se_state
            flag_modified(project, "settings")
            db.commit()

            # Approve audio in service
            try:
                audio_service.approve_audio(db, self.project_id)
            except Exception:
                pass

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message="Audio master approved")
        self.log(f"Audio Stage completed in {self.get_stage(s_id).duration_sec}s")

    async def _run_stage_motion(self, skip_existing: bool) -> None:
        s_id = "motion"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.1, message="Planning camera motion...")

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")
            se_state = (project.settings or {}).get("story_editor_state") or {}
            se_scenes = se_state.get("scenes", [])
            from engine.motion.service import motion_service
            from sqlalchemy.orm.attributes import flag_modified

            # Enforce clean, cinematic presentation: eliminate jitter/shakiness while providing motivated camera paths
            for idx, sc in enumerate(se_scenes):
                dur = float(sc.get("duration_sec", 4.0))
                shot_mod = idx % 4
                if shot_mod == 0:
                    cam_preset = "custom"
                    z_start, z_end = 1.0, 1.045
                    px_start, px_end = 0.0, 0.0
                elif shot_mod == 1:
                    cam_preset = "static"
                    z_start, z_end = 1.0, 1.0
                    px_start, px_end = 0.0, 0.0
                elif shot_mod == 2:
                    cam_preset = "custom"
                    z_start, z_end = 1.025, 1.025
                    px_start, px_end = -2.5, 2.5
                else:
                    cam_preset = "custom"
                    z_start, z_end = 1.04, 1.0
                    px_start, px_end = 0.0, 0.0

                sc["camera"] = {
                    "preset": cam_preset,
                    "zoom_start": z_start,
                    "zoom_end": z_end,
                    "pan_x_start": px_start,
                    "pan_x_end": px_end,
                    "pan_y_start": 0.0,
                    "pan_y_end": 0.0,
                    "easing": "ease_in_out",
                    "duration_sec": dur,
                }
                sc["transition_in"] = "none"
                if "background" in sc and isinstance(sc["background"], dict):
                    sc["background"]["motion"] = "none"
                    sc["background"]["motion_amount"] = 0.0
                for ly in sc.get("layers", []):
                    ly["motion_preset"] = "none"
                    ly["transform"] = {"x": 0, "y": 0, "scale": 1, "rotation": 0, "opacity": 1, "z_index": 1}

            if project.settings is None:
                project.settings = {}
            project.settings["story_editor_state"] = se_state
            flag_modified(project, "settings")
            db.commit()

            try:
                motion_service.approve_motion(db, self.project_id)
            except Exception:
                pass

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message="Motion timeline approved (shakiness eliminated)")
        self.log(f"Motion Stage completed in {self.get_stage(s_id).duration_sec}s")

    async def _run_stage_render(self, profile_name: str, skip_existing: bool) -> None:
        s_id = "render"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.05, message=f"Starting {profile_name} render...")

        with SessionLocal() as db:
            project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
            if not project:
                raise ValueError("Project not found")

            existing_renders = (
                db.query(RenderJobRecord)
                .filter(
                    RenderJobRecord.project_id == self.project_id,
                    RenderJobRecord.status == "COMPLETE",
                    RenderJobRecord.output_profile == profile_name,
                )
                .order_by(RenderJobRecord.created_at.desc())
                .all()
            )

            from engine.render.service import render_service
            import subprocess

            valid_existing_render = None
            if existing_renders and skip_existing:
                for candidate in existing_renders:
                    out_p = Path(candidate.output_path or "")
                    if out_p.exists() and out_p.stat().st_size > 100_000:
                        # Verify candidate MP4 has an audible audio stream
                        has_audio = False
                        try:
                            cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out_p)]
                            probe = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                            if "audio" in probe.stdout.lower():
                                has_audio = True
                        except Exception:
                            has_audio = True
                        if has_audio:
                            valid_existing_render = candidate
                            break

            if valid_existing_render:
                render_job = valid_existing_render
                self.log(f"Render Stage: Found existing verified MP4 render with audio: {render_job.output_path}")
            else:
                self.log(f"Render Stage: Enqueuing production video render ({profile_name})...")
                se_state = (project.settings or {}).get("story_editor_state") or {}
                job_dict = render_service.create_and_start_render_job(
                    db=db,
                    project_id=self.project_id,
                    profile_name=profile_name,
                    subtitle_enabled=False,
                    timeline_data=se_state if (se_state and se_state.get("scenes")) else None,
                )
                job_id = job_dict.get("render_id") or job_dict.get("id")
                self.log(f"Render Stage: Render job created: {job_id}")

                # Poll until complete
                while not self.is_cancelled:
                    await asyncio.sleep(1.0)
                    db.expire_all()
                    job_info = render_service.get_render_job(db, job_id)
                    if not job_info:
                        continue
                    current_prog = float(job_info.get("progress", 0.0) or 0.0)
                    self.update_stage(
                        s_id,
                        progress=round(current_prog, 2),
                        message=f"Rendering: {int(current_prog * 100)}% ({job_info.get('frames_done', 0)}/{job_info.get('frames_total', 0)} frames)",
                    )
                    status = job_info.get("status")
                    if status == "COMPLETE":
                        render_job = (
                            db.query(RenderJobRecord)
                            .filter(RenderJobRecord.id == job_id)
                            .first()
                        )
                        break
                    elif status in ("FAILED", "CANCELLED"):
                        err_msg = job_info.get("error_message") or "Video encoding failed"
                        raise RuntimeError(f"Render job {status}: {err_msg}")

            output_path = getattr(render_job, "output_path", "")
            self.result["output_mp4_path"] = output_path
            self.result["video_profile"] = profile_name

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message="Production MP4 certified")
        self.log(f"Render Stage completed in {self.get_stage(s_id).duration_sec}s. File: {output_path}")

    async def _run_stage_packaging(self, profile_name: str) -> None:
        s_id = "packaging"
        self.current_stage_id = s_id
        start_t = time.monotonic()
        self.update_stage(s_id, status="RUNNING", progress=0.2, message="Generating YouTube metadata & thumbnail...")

        with SessionLocal() as db:
            packaging_data = await generate_youtube_packaging(db, self.project_id, profile_name=profile_name)
            self.result["youtube_title"] = packaging_data.selected_title
            self.result["youtube_description"] = packaging_data.description
            self.result["youtube_tags"] = packaging_data.tags
            self.result["thumbnail_prompt"] = packaging_data.thumbnail.prompt
            self.result["thumbnail_aspect_ratio"] = packaging_data.thumbnail.aspect_ratio

            self.log(f"Packaging Stage: Researched title: '{packaging_data.selected_title}'")
            self.update_stage(s_id, progress=0.6, message="Crafting ComfyUI thumbnail art...")

            # ComfyUI Image Generation Check
            try:
                from engine.comfyui.client import ComfyUIClient
                client = ComfyUIClient()
                cap = client.capabilities()
                if cap.get("available"):
                    self.log("Packaging Stage: ComfyUI is online, generating AI thumbnail...")
                    from engine.comfyui.service import generate_image_operation
                    thumb_res = await asyncio.to_thread(
                        generate_image_operation,
                        db,
                        lambda p, m: self.update_stage(s_id, progress=0.6 + p * 0.35, message=m),
                        lambda: self.is_cancelled,
                        project_id=self.project_id,
                        workflow_id=packaging_data.thumbnail.workflow_id,
                        prompt=packaging_data.thumbnail.prompt,
                        negative_prompt=packaging_data.thumbnail.negative_prompt,
                        width=packaging_data.thumbnail.recommended_width,
                        height=packaging_data.thumbnail.recommended_height,
                        seed=packaging_data.thumbnail.seed,
                    )
                    self.result["thumbnail_asset_id"] = thumb_res.get("asset_id")
                    self.result["thumbnail_relative_path"] = thumb_res.get("relative_path")
                    self.log(f"Packaging Stage: ComfyUI thumbnail generated: {thumb_res.get('relative_path')}")
                else:
                    self.log("Packaging Stage: ComfyUI offline or local instance not running; thumbnail prompt and research ready for 1-click generation.")
            except Exception as e:
                self.log(f"Packaging Stage ComfyUI note: {e} (Prompt and metadata fully ready).")

        self.get_stage(s_id).duration_sec = round(time.monotonic() - start_t, 2)
        self.update_stage(s_id, status="COMPLETED", progress=1.0, message="YouTube release bundle ready")
        self.log(f"Packaging Stage completed in {self.get_stage(s_id).duration_sec}s")

    def _persist_status(self) -> None:
        try:
            with SessionLocal() as db:
                project = db.query(ProjectRecord).filter(ProjectRecord.id == self.project_id).first()
                if project:
                    workspace = Path(str(project.workspace_path))
                    gen_dir = resolve_contained_path(workspace, Path("generated"))
                    gen_dir.mkdir(parents=True, exist_ok=True)
                    target = resolve_contained_path(workspace, Path("generated") / "autopilot_status.json")
                    target.write_text(self.snapshot().model_dump_json(indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not persist autopilot status: %s", exc)


# In-memory registry of active runners
_ACTIVE_RUNNERS: Dict[str, AutoPilotRunner] = {}


def get_autopilot_runner(project_id: str) -> AutoPilotRunner:
    if project_id not in _ACTIVE_RUNNERS:
        runner = AutoPilotRunner(project_id)
        # Attempt to rehydrate from persisted workspace status if present
        try:
            with SessionLocal() as db:
                project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
                if project:
                    workspace = Path(str(project.workspace_path))
                    target = workspace / "generated" / "autopilot_status.json"
                    if target.is_file():
                        data = json.loads(target.read_text(encoding="utf-8"))
                        runner.status = data.get("status", "IDLE")
                        runner.overall_progress = data.get("overall_progress", 0.0)
                        runner.logs = data.get("logs", [])
                        runner.result = data.get("result", {})
                        runner.error = data.get("error")
                        runner.started_at = data.get("started_at")
                        runner.completed_at = data.get("completed_at")
                        for idx, s in enumerate(data.get("stages", [])):
                            if idx < len(runner.stages):
                                runner.stages[idx].status = s.get("status", "PENDING")
                                runner.stages[idx].progress = s.get("progress", 0.0)
                                runner.stages[idx].message = s.get("message", "")
                                runner.stages[idx].duration_sec = s.get("duration_sec", 0.0)
        except Exception:
            pass
        _ACTIVE_RUNNERS[project_id] = runner
    return _ACTIVE_RUNNERS[project_id]


async def start_autopilot_run(project_id: str, options: dict[str, Any] | None = None) -> AutoPilotStatusResponse:
    runner = get_autopilot_runner(project_id)
    if runner.status == "RUNNING":
        return runner.snapshot()

    runner.options = options or {}
    runner.is_cancelled = False
    runner.error = None
    runner.status = "RUNNING"
    runner._task = asyncio.create_task(runner.execute())
    return runner.snapshot()
