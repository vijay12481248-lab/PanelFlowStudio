"""Durable queue integration: each episode is a job in the existing JobManager (survives restarts, retries, cancels)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from engine.anime.review.channels import channel_store
from engine.anime.review.pipeline import ReviewJobSpec, run_review
from engine.jobs.workflow import enqueue_project_operation, register_operation_factory

JOB_TYPE = "ANIME_REVIEW"


def build_review_operation(project_id: str, payload: dict):
    spec = ReviewJobSpec(**payload)

    def operation(db, progress, is_cancelled):
        from engine.llm.registry import llm_registry

        provider = llm_registry.get_ollama_provider()  # local first, no cloud/mock fallback
        if not asyncio.run(provider.health_check()):
            raise RuntimeError("Ollama is not reachable")
        return run_review(spec, channel_store.get(spec.channel_id), provider, progress, is_cancelled)

    return operation


register_operation_factory(JOB_TYPE, build_review_operation)


def enqueue_review(db, spec: ReviewJobSpec) -> tuple[str, str]:
    """Creates the tracking project (rights recorded on it) and queues the job. Returns (project_id, job_id)."""
    from engine.projects.service import project_service

    spec.rights.validate_for_acquisition()
    channel_store.get(spec.channel_id)  # fail fast on a typo instead of inside the worker
    project = project_service.create_project(
        db, spec.title, "LOCAL_FOLDER", spec.rights.status, source_url=spec.source,
        license_info=spec.rights.permission_notes or "",
        project_settings={"project_path": spec.workspace, "kind": "anime_review", "channel_id": spec.channel_id})
    payload = spec.model_dump(mode="json")
    job_id = enqueue_project_operation(project.id, JOB_TYPE, build_review_operation(project.id, payload),
                                       requires_gpu=True, gpu_vram_mb=4000, max_retries=1, job_input=payload)
    return project.id, job_id
