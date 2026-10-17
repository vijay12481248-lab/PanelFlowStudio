import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable, Coroutine, Any
from sqlalchemy.orm import Session

from engine.database.session import SessionLocal
from engine.database.models import JobRecord
from engine.acquisition.models import JobStatus, JobType
from engine.acquisition.downloader.pipeline import PipelineCancellationToken

logger = logging.getLogger(__name__)

def utc_now():
    return datetime.now(timezone.utc)

class JobManager:
    def __init__(self):
        self._active_tokens: dict[str, PipelineCancellationToken] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}

    def recover_interrupted_jobs(self) -> int:
        """
        Scans SQLite database for any jobs left in RUNNING or QUEUED status
        due to an ungraceful shutdown or crash, and marks them FAILED.
        """
        with SessionLocal() as db:
            interrupted_jobs = (
                db.query(JobRecord)
                .filter(JobRecord.status.in_([JobStatus.RUNNING.value, JobStatus.QUEUED.value]))
                .all()
            )
            count = len(interrupted_jobs)
            for j in interrupted_jobs:
                j.status = JobStatus.FAILED.value
                j.finished_at = utc_now()
                j.error = "Application was terminated while job was in progress"
                j.message = "Interrupted by system shutdown or restart"
            if count > 0:
                db.commit()
                logger.info(f"Recovered and marked {count} interrupted jobs as FAILED")
            return count

    def create_job(
        self,
        project_id: str,
        job_type: JobType | str,
        job_input: dict | None = None,
    ) -> JobRecord:
        with SessionLocal() as db:
            job = JobRecord(
                project_id=project_id,
                job_type=job_type.value if isinstance(job_type, JobType) else job_type,
                status=JobStatus.QUEUED.value,
                progress=0.0,
                message="Job queued",
                input=job_input or {},
                output={},
                created_at=utc_now(),
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            # Create a detached copy or dict
            job_dict = {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "job_type": job.job_type,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "created_at": job.created_at,
            }
            return job

    def update_job_progress(
        self,
        job_id: str,
        progress: float,
        message: str,
        output_patch: dict | None = None,
    ) -> None:
        with SessionLocal() as db:
            job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if job and job.status == JobStatus.RUNNING.value:
                job.progress = max(0.0, min(1.0, progress))
                job.message = message
                if output_patch:
                    current_output = dict(job.output or {})
                    current_output.update(output_patch)
                    job.output = current_output
                db.commit()

    def get_job(self, job_id: str) -> dict | None:
        with SessionLocal() as db:
            job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if not job:
                return None
            return {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "job_type": job.job_type,
                "status": job.status,
                "progress": job.progress,
                "message": job.message,
                "input": job.input,
                "output": job.output,
                "error": job.error,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            }

    def list_project_jobs(self, project_id: str) -> list[dict]:
        with SessionLocal() as db:
            jobs = (
                db.query(JobRecord)
                .filter(JobRecord.project_id == project_id)
                .order_by(JobRecord.created_at.desc())
                .all()
            )
            return [
                {
                    "job_id": j.job_id,
                    "project_id": j.project_id,
                    "job_type": j.job_type,
                    "status": j.status,
                    "progress": j.progress,
                    "message": j.message,
                    "input": j.input,
                    "output": j.output,
                    "error": j.error,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                }
                for j in jobs
            ]

    def cancel_job(self, job_id: str) -> bool:
        token = self._active_tokens.get(job_id)
        if token:
            token.cancel()
        task = self._active_tasks.get(job_id)
        if task and not task.done():
            task.cancel()

        with SessionLocal() as db:
            job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if job and job.status in (JobStatus.QUEUED.value, JobStatus.RUNNING.value):
                job.status = JobStatus.CANCELLED.value
                job.finished_at = utc_now()
                job.message = "Job was cancelled by user"
                db.commit()
                return True
        return False

    def is_job_active(self, job_id: str) -> bool:
        """Returns True if the background runner is still executing."""
        return job_id in self._active_tokens

    def enqueue_async(
        self,
        job_id: str,
        coro_fn: Callable[[PipelineCancellationToken, Callable[[float, str], None]], Coroutine[Any, Any, dict]],
    ) -> None:
        """
        Enqueues an asynchronous runner in the event loop with progress reporting and cancellation.
        """
        token = PipelineCancellationToken()
        self._active_tokens[job_id] = token

        def progress_cb(pct: float, msg: str):
            self.update_job_progress(job_id, pct, msg)

        async def runner():
            with SessionLocal() as db:
                job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                if not job:
                    return
                # If already cancelled while in queue, do not transition to RUNNING!
                if job.status == JobStatus.CANCELLED.value or token.is_cancelled:
                    return
                job.status = JobStatus.RUNNING.value
                job.started_at = utc_now()
                job.message = "Job started"
                db.commit()

            try:
                output = await coro_fn(token, progress_cb)
                with SessionLocal() as db:
                    job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                    if job:
                        if token.is_cancelled or job.status == JobStatus.CANCELLED.value:
                            job.status = JobStatus.CANCELLED.value
                            job.message = "Job cancelled by user"
                        else:
                            job.status = JobStatus.SUCCEEDED.value
                            job.progress = 1.0
                            job.message = "Job completed successfully"
                            job.output = output or {}
                        job.finished_at = utc_now()
                        db.commit()
            except asyncio.CancelledError:
                with SessionLocal() as db:
                    job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                    if job:
                        job.status = JobStatus.CANCELLED.value
                        job.message = "Job execution cancelled"
                        job.finished_at = utc_now()
                        db.commit()
            except Exception as e:
                logger.exception(f"Job {job_id} failed with error: {e}")
                with SessionLocal() as db:
                    job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                    if job:
                        if token.is_cancelled or job.status == JobStatus.CANCELLED.value:
                            job.status = JobStatus.CANCELLED.value
                            job.message = "Job cancelled by user"
                        else:
                            job.status = JobStatus.FAILED.value
                            job.error = str(e)
                            job.message = f"Job failed: {str(e)}"
                        job.finished_at = utc_now()
                        db.commit()
            finally:
                self._active_tokens.pop(job_id, None)
                self._active_tasks.pop(job_id, None)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(runner())
            self._active_tasks[job_id] = task
        except RuntimeError:
            import threading
            def bg_thread():
                asyncio.run(runner())
            t = threading.Thread(target=bg_thread, daemon=True)
            t.start()


job_manager = JobManager()
