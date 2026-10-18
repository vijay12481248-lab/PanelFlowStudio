"""Run blocking local workflow operations in the existing durable job manager."""
import asyncio

from engine.jobs.manager import job_manager


def enqueue_project_operation(
    project_id: str,
    job_type: str,
    operation,
    priority: int = 10,
    depends_on_job_id: str | None = None,
    requires_gpu: bool = False,
    gpu_vram_mb: int = 0,
    max_retries: int = 3,
):
    job = job_manager.create_job(
        project_id=project_id,
        job_type=job_type,
        priority=priority,
        depends_on_job_id=depends_on_job_id,
        requires_gpu=requires_gpu,
        gpu_vram_mb=gpu_vram_mb,
        max_retries=max_retries,
    )

    async def run(cancel_token, progress):
        def execute():
            from engine.database.session import SessionLocal
            with SessionLocal() as db:
                return operation(db, progress, lambda: cancel_token.is_cancelled)
        return await asyncio.to_thread(execute)

    job_manager.enqueue_async(job.job_id, run)
    return job.job_id

