"""Run blocking local workflow operations in the existing durable job manager."""

import asyncio
from collections.abc import Callable
from typing import Any

from engine.jobs.manager import job_manager


Operation = Callable[[Any, Callable[[float, str], None], Callable[[], bool]], dict]
OperationFactory = Callable[[str, dict], Operation]
_OPERATION_FACTORIES: dict[str, OperationFactory] = {}
_PROVIDER_FACTORIES_READY = False


def register_operation_factory(job_type: str, factory: OperationFactory) -> None:
    """Register a job-type factory that can rehydrate work after restart."""
    _OPERATION_FACTORIES[job_type] = factory


def build_operation(job_type: str, project_id: str, job_input: dict) -> Operation | None:
    global _PROVIDER_FACTORIES_READY
    if not _PROVIDER_FACTORIES_READY:
        from engine.comfyui import service as _comfyui_service  # noqa: F401
        _PROVIDER_FACTORIES_READY = True
    factory = _OPERATION_FACTORIES.get(job_type)
    return factory(project_id, job_input) if factory else None


def _runner(project_id: str, operation: Operation):
    async def run(cancel_token, progress):
        def execute():
            from engine.database.session import SessionLocal

            from engine.database.models import JobRecord
            from engine.acquisition.models import JobStatus
            from engine.jobs.manager import utc_now

            def is_cancelled():
                if cancel_token.is_cancelled:
                    return True
                job_id, lease_id = getattr(cancel_token, "job_id", None), getattr(cancel_token, "lease_id", None)
                if not job_id or not lease_id:
                    return False
                with SessionLocal() as check_db:
                    return check_db.query(JobRecord).filter(
                        JobRecord.job_id == job_id,
                        JobRecord.status == JobStatus.RUNNING.value,
                        JobRecord.worker_lease_id == lease_id,
                        JobRecord.lease_expires_at > utc_now(),
                    ).first() is None

            if is_cancelled():
                raise RuntimeError("Worker lease is no longer active")
            with SessionLocal() as db:
                return operation(db, progress, is_cancelled)

        return await asyncio.to_thread(execute)

    return run


def enqueue_project_operation(
    project_id: str,
    job_type: str,
    operation: Operation,
    priority: int = 10,
    depends_on_job_id: str | None = None,
    requires_gpu: bool = False,
    gpu_vram_mb: int = 0,
    max_retries: int = 3,
    job_input: dict | None = None,
):
    job = job_manager.create_job(
        project_id=project_id,
        job_type=job_type,
        job_input=job_input or {},
        priority=priority,
        depends_on_job_id=depends_on_job_id,
        requires_gpu=requires_gpu,
        gpu_vram_mb=gpu_vram_mb,
        max_retries=max_retries,
    )
    job_manager.enqueue_async(job.job_id, _runner(project_id, operation))
    return job.job_id


def rehydrate_job_runner(job) -> Callable | None:
    """Build a runner from persisted job type/input when a factory is available."""
    operation = build_operation(job.job_type, job.project_id, job.input or {})
    return _runner(job.project_id, operation) if operation else None


def _require_persisted_ids(payload: dict, key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Persisted job input is missing a valid {key} list")
    return value

def build_script_generation_operation(project_id: str, payload: dict):
    if not isinstance(payload.get("narrative_snapshot"), dict) or not payload["narrative_snapshot"]:
        raise ValueError("Persisted script narrative snapshot is missing")
    from engine.story.models import NarrativeDocument
    narrative_snapshot = NarrativeDocument.model_validate(payload["narrative_snapshot"]).model_dump(mode="json")
    provider_id = payload.get("provider_id")
    model_name = payload.get("model_name")
    if not isinstance(provider_id, str) or not provider_id or not isinstance(model_name, str) or not model_name:
        raise ValueError("Persisted script provider/model identity is missing")

    def operation(db, progress, is_cancelled):
        from engine.story.service import story_service

        progress(0.1, "Writing original chapter narration; waiting for language model...")
        if is_cancelled():
            raise ValueError("Narration generation cancelled")
        current = story_service.get_narrative(db, project_id)
        if current is None or current.model_dump(mode="json") != narrative_snapshot:
            raise ValueError("Persisted script narrative snapshot has changed")
        story_service.resolve_pinned_script_provider(provider_id, model_name)
        script = story_service.generate_script(
            db,
            project_id,
            payload.get("adaptation_profile", "FAITHFUL"),
            cancelled=is_cancelled,
            provider_id=provider_id,
            model_name=model_name,
        )
        progress(1.0, "Narration ready for review")
        return {"script_id": script.script_id}

    return operation


def audio_script_snapshot(db, project_id: str) -> dict:
    """Freeze the approved script inputs consumed by the audio timeline."""
    from engine.database.models import VideoScriptRecord
    script = (db.query(VideoScriptRecord).filter(VideoScriptRecord.project_id == project_id)
              .order_by(VideoScriptRecord.created_at.desc()).first())
    if script is None or script.status != "APPROVED" or not script.segments:
        raise ValueError("An approved script with segments is required for audio generation")
    ordered_segments = sorted(script.segments, key=lambda seg: (seg.sequence, seg.id))
    return {"script_id": script.id, "segments": [
        {"id": seg.id, "text": seg.text, "speaker_character_id": seg.speaker_character_id,
         "emotion": seg.emotion, "intensity": seg.intensity, "sequence": seg.sequence,
         "estimated_duration": seg.estimated_duration} for seg in ordered_segments]}


def build_audio_generation_operation(project_id: str, payload: dict):
    snapshot = payload.get("script_snapshot")
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get("script_id"), str)
            or not snapshot["script_id"] or not isinstance(snapshot.get("segments"), list)
            or not snapshot["segments"]):
        raise ValueError("Persisted audio script snapshot is missing")
    provider_id = payload.get("tts_provider_id")
    model_name = payload.get("tts_model_name")
    voice_casting = payload.get("voice_casting")
    if not isinstance(provider_id, str) or not provider_id or not isinstance(model_name, str) or not model_name:
        raise ValueError("Persisted TTS provider/model identity is missing")
    if not isinstance(voice_casting, dict) or not all(
        isinstance(key, str) and key and isinstance(value, str) and value
        for key, value in voice_casting.items()
    ):
        raise ValueError("Persisted audio voice casting is invalid")

    def operation(db, progress, is_cancelled):
        if audio_script_snapshot(db, project_id) != snapshot:
            raise ValueError("Persisted audio script snapshot has changed")
        from engine.audio.service import audio_service

        audio_service.validate_pinned_tts_provider(provider_id, model_name)

        return audio_service.generate_audio_timeline(
            db,
            project_id,
            voice_casting,
            progress,
            is_cancelled,
            tts_provider_id=provider_id,
            tts_model_name=model_name,
            voice_casting_is_resolved=True,
        )

    return operation


register_operation_factory("SCRIPT_GENERATION", build_script_generation_operation)
register_operation_factory("AUDIO_GENERATION", build_audio_generation_operation)

def build_story_analysis_operation(project_id: str, payload: dict):
    panel_ids = _require_persisted_ids(payload, "panel_ids")
    if len(set(panel_ids)) != len(panel_ids):
        raise ValueError("Persisted panel_ids contain duplicates")
    provider_id = payload.get("preferred_provider")
    if not isinstance(provider_id, str) or not provider_id.strip():
        raise ValueError("Persisted story provider is missing")

    def operation(db, progress, is_cancelled):
        import asyncio
        from engine.story.service import story_service

        runner = story_service.analyze_story_project(
            db,
            project_id,
            preferred_provider_id=payload.get("preferred_provider"),
            panel_ids=payload.get("panel_ids"),
            operation_only=True,
        )

        class RecoveryToken:
            @property
            def is_cancelled(self):
                return is_cancelled()

        return asyncio.run(runner(RecoveryToken(), progress))

    return operation


register_operation_factory("STORY_ANALYSIS", build_story_analysis_operation)

def _run_rehydrated_async(runner, progress, is_cancelled):
    class RecoveryToken:
        @property
        def is_cancelled(self):
            return is_cancelled()

    return asyncio.run(runner(RecoveryToken(), progress))


def build_normalization_operation(project_id: str, payload: dict):
    page_ids = _require_persisted_ids(payload, "page_ids")

    def operation(db, progress, is_cancelled):
        from engine.projects.service import project_service

        runner = project_service.normalize_project(
            db,
            project_id,
            target_width=payload.get("target_width", 1920),
            page_ids=page_ids,
            operation_only=True,
        )
        return _run_rehydrated_async(runner, progress, is_cancelled)

    return operation


def build_panel_detection_operation(project_id: str, payload: dict):
    page_ids = _require_persisted_ids(payload, "page_ids")

    def operation(db, progress, is_cancelled):
        from engine.projects.service import project_service

        runner = project_service.detect_panels_project(
            db,
            project_id,
            reading_direction=payload.get("reading_direction", "ltr"),
            min_area_ratio=payload.get("min_area_ratio", 0.02),
            profile=payload.get("profile", "AUTO"),
            page_ids=page_ids,
            operation_only=True,
        )
        return _run_rehydrated_async(runner, progress, is_cancelled)

    return operation


def build_ocr_operation(project_id: str, payload: dict):
    panel_ids = _require_persisted_ids(payload, "panel_ids")

    def operation(db, progress, is_cancelled):
        from engine.projects.service import project_service

        runner = project_service.extract_ocr_project(
            db,
            project_id,
            engine_id=payload.get("engine_id", "mock_ocr"),
            language=payload.get("language", "en"),
            panel_ids=panel_ids,
            operation_only=True,
        )
        return _run_rehydrated_async(runner, progress, is_cancelled)

    return operation


register_operation_factory("NORMALIZATION", build_normalization_operation)
register_operation_factory("PANEL_DETECTION", build_panel_detection_operation)
register_operation_factory("OCR_EXTRACTION", build_ocr_operation)

def build_acquisition_operation(project_id: str, payload: dict):
    required = ("source", "chapter_id", "adapter_id", "page_delay_sec", "chapter", "candidates")
    if any(key not in payload for key in required):
        raise ValueError("Persisted acquisition snapshot is incomplete")
    from engine.acquisition.models import ChapterInfo, PageCandidate
    if not isinstance(payload["chapter"], dict) or not isinstance(payload["candidates"], list) or not payload["candidates"]:
        raise ValueError("Persisted acquisition snapshot is invalid")
    chapter = ChapterInfo.model_validate(payload["chapter"])
    candidates = [PageCandidate.model_validate(item) for item in payload["candidates"]]
    if chapter.id != payload["chapter_id"] or len({item.sequence for item in candidates}) != len(candidates):
        raise ValueError("Persisted acquisition snapshot does not match selected chapter")

    def operation(db, progress, is_cancelled):
        from engine.acquisition.adapters.registry import get_default_registry
        from engine.projects.service import project_service

        runner = project_service.start_acquisition_job(
            db,
            project_id,
            get_default_registry(),
            source_override=payload.get("source"),
            chapter_id=payload.get("chapter_id"),
            adapter_id=payload.get("adapter_id"),
            page_delay_sec=payload.get("page_delay_sec"),
            chapter_snapshot=chapter.model_dump(mode="json"),
            candidate_snapshot=[item.model_dump(mode="json") for item in candidates],
            operation_only=True,
        )
        return _run_rehydrated_async(runner, progress, is_cancelled)

    return operation


def build_retry_pages_operation(project_id: str, payload: dict):
    page_ids = _require_persisted_ids(payload, "page_ids")
    if not isinstance(payload.get("source"), str) or not payload.get("source") or not isinstance(payload.get("adapter_id"), str) or not payload.get("adapter_id"):
        raise ValueError("Persisted retry input is incomplete")

    def operation(db, progress, is_cancelled):
        from engine.acquisition.adapters.registry import get_default_registry
        from engine.projects.service import project_service

        runner = project_service.retry_failed_pages(
            db,
            project_id,
            get_default_registry(),
            page_ids=page_ids,
            source_override=payload.get("source"),
            adapter_id=payload.get("adapter_id"),
            operation_only=True,
        )
        return _run_rehydrated_async(runner, progress, is_cancelled)

    return operation


register_operation_factory("ACQUISITION", build_acquisition_operation)
register_operation_factory("RETRY_PAGES", build_retry_pages_operation)


def build_narration_draft_operation(project_id: str, payload: dict):
    from pathlib import Path
    scenes_data = payload.get("scenes", [])
    provider_id = payload.get("provider_id")
    model_name = payload.get("model_name")
    mode = payload.get("mode", "full")
    existing_page_scripts = payload.get("existing_page_scripts")

    def operation(db, progress, is_cancelled):
        from engine.database.models import (
            ProjectRecord,
            PanelRecord,
            PageRecord,
            CharacterRecord,
        )
        from engine.story.narration import story_narration_service

        proj = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
        if not proj:
            raise ValueError(f"Project {project_id} not found")

        progress(0.05, "Initializing 3-Tier Narration Pipeline...")
        if is_cancelled():
            raise ValueError("Narration draft cancelled by user")

        db_pages = (
            db.query(PageRecord)
            .filter(PageRecord.project_id == project_id, PageRecord.status != "FAILED")
            .order_by(PageRecord.sequence.asc())
            .all()
        )
        db_characters = (
            db.query(CharacterRecord)
            .filter(CharacterRecord.project_id == project_id)
            .all()
        )
        pages_data = [
            {
                "id": p.id,
                "sequence": p.sequence,
                "filename": p.filename,
                "panels_count": p.panels_count or 1,
            }
            for p in db_pages
        ]
        characters_data = [
            {
                "id": c.id,
                "name": c.display_name,
                "canonical_name": c.canonical_name or c.display_name,
                "role": c.role,
                "description": c.description,
            }
            for c in db_characters
        ]

        def on_step_progress(pct: float, msg: str):
            if is_cancelled():
                raise ValueError("Narration draft cancelled by user")
            progress(pct, msg)

        async def run_draft():
            return await story_narration_service.generate_narration_draft(
                project_id=project_id,
                scenes_data=scenes_data,
                pages_data=pages_data,
                characters_data=characters_data,
                provider_id=provider_id,
                model_name=model_name,
                workspace_path=Path(proj.workspace_path) if proj.workspace_path else None,
                mode=mode,
                existing_page_scripts=existing_page_scripts,
                progress_callback=on_step_progress,
                is_cancelled=is_cancelled,
            )

        progress(0.10, "Starting 3-tier narration synthesis...")
        plan = asyncio.run(run_draft())

        # Persist narration plan to project story workspace
        if proj.workspace_path:
            plan_path = Path(proj.workspace_path) / "story" / "narration_plan.json"
            try:
                plan_path.parent.mkdir(parents=True, exist_ok=True)
                plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            except Exception:
                pass

        progress(1.0, "3-Tier narration generated successfully.")
        return {"status": "SUCCEEDED", "plan": plan.model_dump()}

    return operation


register_operation_factory("NARRATION_DRAFT", build_narration_draft_operation)

