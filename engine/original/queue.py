"""Durable queue for original-story episodes (same JobManager as the anime reviews: survives restarts, retries, cancels)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from engine.anime.review.channels import channel_store
from engine.jobs.workflow import enqueue_project_operation, register_operation_factory
from engine.original.episode import run_episode
from engine.original.series import Episode, SeriesStore

JOB_TYPE = "ORIGINAL_EPISODE"


class EpisodeJobSpec(BaseModel):
    root: str  # series store root
    series_id: str
    number: int
    scenes: int | None = None
    check: bool = True
    refine: bool = False  # opt-in review -> repair/redraw loop for the pictures (see engine/original/refine.py)
    animate: bool = False  # opt-in: animate key beats with the fast H3 workflow (see engine/original/animate.py)
    title: str = ""


def _runner_factory():
    from engine.original.art import ComfyRunner

    return ComfyRunner()  # raises a clear error when ComfyUI or its models are missing


def build_episode_operation(project_id: str, payload: dict):
    spec = EpisodeJobSpec(**payload)

    def operation(db, progress, is_cancelled):
        from engine.llm.registry import llm_registry

        store = SeriesStore(Path(spec.root))
        series = store.get(spec.series_id)
        provider = llm_registry.get_ollama_provider()  # local first, no cloud or mock fallback
        if not asyncio.run(provider.health_check()):
            raise RuntimeError("Ollama is not reachable")
        channel = channel_store.get(series.channel_id) if series.channel_id else None
        return run_episode(store, spec.series_id, spec.number, channel, provider, _runner_factory, progress, is_cancelled,
                           spec.scenes, spec.check, spec.refine, spec.animate)

    return operation


register_operation_factory(JOB_TYPE, build_episode_operation)


def enqueue_episodes(db, store: SeriesStore, series_id: str, count: int, publish_at: list[str], scenes: int | None = None,
                     check: bool = True, refine: bool = False, animate: bool = False) -> list[dict]:
    """Queue `count` consecutive episodes. Each is its own job; an episode waits for the previous one's summary."""
    from engine.projects.service import project_service

    series = store.get(series_id)
    if series.channel_id:
        channel_store.get(series.channel_id)  # fail now, not inside the worker
    out = []
    first = series.next_number()
    for i in range(count):
        n = first + i
        ep = Episode(number=n, publish_at=publish_at[i] if i < len(publish_at) else None, status="queued",
                     workspace=str(store.episode_dir(series_id, n)))
        store.update_episode(series_id, ep)
        project = project_service.create_project(
            db, f"{series.name} - episode {n}", "LOCAL_FOLDER", "USER_OWNED", license_info="Original story created with AI tools",
            project_settings={"project_path": str(store.episode_dir(series_id, n) / "_project"), "kind": "original_episode",
                              "series_id": series_id})
        spec = EpisodeJobSpec(root=str(store.root), series_id=series_id, number=n, scenes=scenes, check=check, refine=refine, animate=animate,
                              title=f"{series.name} - episode {n}")
        payload = spec.model_dump(mode="json")
        job_id = enqueue_project_operation(project.id, JOB_TYPE, build_episode_operation(project.id, payload),
                                           requires_gpu=False, max_retries=2, job_input=payload)
        out.append({"episode": n, "job_id": job_id, "project_id": project.id, "publish_at": ep.publish_at})
    return out
