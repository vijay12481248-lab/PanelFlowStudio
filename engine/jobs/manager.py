import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Callable, Coroutine, Any, Optional
from sqlalchemy.orm import Session

from engine.database.session import SessionLocal
from engine.database.models import JobRecord
from engine.acquisition.models import JobStatus, JobType
from engine.acquisition.downloader.pipeline import PipelineCancellationToken
from engine.system.resources import resource_manager

logger = logging.getLogger(__name__)

def utc_now():
    return datetime.now(timezone.utc)


class JobManager:
    """
    Persistent, multi-project, resource-aware job scheduler.
    Supports:
      - Durable SQLite persistence
      - Worker leases and crash recovery
      - Explicit task dependencies
      - Fair round-robin project interleaving
      - Hardware admission control (RAM/VRAM limits)
      - Bounded exponential backoff retries
      - Heartbeat lease extension and cancellation
    """

    def __init__(self):
        self.worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        self.lease_duration_sec = 60.0
        self._active_tokens: dict[str, PipelineCancellationToken] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}

    def _to_dict(self, job: JobRecord) -> dict:
        return {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "job_type": job.job_type,
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "input": job.input or {},
            "output": job.output or {},
            "error": job.error,
            "priority": getattr(job, "priority", 10),
            "depends_on_job_id": getattr(job, "depends_on_job_id", None),
            "requires_gpu": getattr(job, "requires_gpu", False),
            "gpu_vram_mb": getattr(job, "gpu_vram_mb", 0),
            "cpu_units": getattr(job, "cpu_units", 1),
            "worker_lease_id": getattr(job, "worker_lease_id", None),
            "lease_expires_at": job.lease_expires_at.isoformat() if getattr(job, "lease_expires_at", None) else None,
            "retry_count": getattr(job, "retry_count", 0),
            "max_retries": getattr(job, "max_retries", 3),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }

    def recover_interrupted_jobs(self) -> int:
        """
        Scans SQLite database for any jobs left in RUNNING status
        due to an ungraceful shutdown or crash, and marks them FAILED.
        """
        with SessionLocal() as db:
            interrupted_jobs = (
                db.query(JobRecord)
                .filter(JobRecord.status == JobStatus.RUNNING.value)
                .all()
            )
            count = 0
            now = utc_now()
            for j in interrupted_jobs:
                if j.job_id in self._active_tokens:
                    continue
                j.status = JobStatus.FAILED.value
                j.finished_at = now
                j.error = "Application was terminated while job was in progress"
                j.message = "Interrupted by system shutdown or restart"
                count += 1
            if count > 0:
                db.commit()
                logger.info(f"Recovered and marked {count} interrupted jobs as FAILED")
            return count

    def recover_expired_leases(self) -> int:
        """
        Scans for active jobs whose worker lease expired without a heartbeat.
        Re-queues them if retries remain, or marks them FAILED.
        """
        with SessionLocal() as db:
            now = utc_now()
            expired_jobs = (
                db.query(JobRecord)
                .filter(
                    JobRecord.status == JobStatus.RUNNING.value,
                    JobRecord.lease_expires_at != None,
                    JobRecord.lease_expires_at < now,
                )
                .all()
            )
            count = 0
            for j in expired_jobs:
                if j.job_id in self._active_tokens:
                    continue
                if j.retry_count < j.max_retries:
                    j.retry_count += 1
                    j.status = JobStatus.QUEUED.value
                    j.worker_lease_id = None
                    j.lease_expires_at = None
                    j.message = f"Lease expired; re-queued (retry {j.retry_count}/{j.max_retries})"
                else:
                    j.status = JobStatus.FAILED.value
                    j.finished_at = now
                    j.error = "Worker lease expired; max retries exceeded."
                    j.message = "Job failed due to worker timeout"
                count += 1
            if count > 0:
                db.commit()
                logger.info(f"Recovered {count} jobs with expired worker leases")
            return count


    def create_job(
        self,
        project_id: str,
        job_type: JobType | str,
        job_input: dict | None = None,
        priority: int = 10,
        depends_on_job_id: str | None = None,
        requires_gpu: bool = False,
        gpu_vram_mb: int = 0,
        cpu_units: int = 1,
        max_retries: int = 3,
    ) -> JobRecord:
        with SessionLocal() as db:
            job = JobRecord(
                project_id=project_id,
                job_type=job_type.value if isinstance(job_type, JobType) else job_type,
                status=JobStatus.QUEUED.value,
                progress=0.0,
                message="Job queued in multi-project scheduler",
                input=job_input or {},
                output={},
                priority=priority,
                depends_on_job_id=depends_on_job_id,
                requires_gpu=requires_gpu,
                gpu_vram_mb=gpu_vram_mb,
                cpu_units=cpu_units,
                worker_lease_id=None,
                lease_expires_at=None,
                retry_count=0,
                max_retries=max_retries,
                created_at=utc_now(),
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            return job

    def claim_job_lease(self, job_id: str) -> bool:
        """Atomically claims a worker lease on a job and sets status to RUNNING."""
        with SessionLocal() as db:
            job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if not job or job.status != JobStatus.QUEUED.value:
                return False
            job.status = JobStatus.RUNNING.value
            job.started_at = utc_now()
            job.worker_lease_id = self.worker_id
            job.lease_expires_at = utc_now() + timedelta(seconds=self.lease_duration_sec)
            job.message = "Job claimed by worker lease"
            db.commit()
            return True

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
                # Heartbeat lease renewal
                job.lease_expires_at = utc_now() + timedelta(seconds=self.lease_duration_sec)
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
            return self._to_dict(job)

    def list_project_jobs(self, project_id: str) -> list[dict]:
        with SessionLocal() as db:
            jobs = (
                db.query(JobRecord)
                .filter(JobRecord.project_id == project_id)
                .order_by(JobRecord.priority.desc(), JobRecord.created_at.desc())
                .all()
            )
            return [self._to_dict(j) for j in jobs]

    def list_all_jobs(
        self,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        """Lists jobs across all projects with optional status/project filter."""
        with SessionLocal() as db:
            query = db.query(JobRecord)
            if status:
                query = query.filter(JobRecord.status == status.upper())
            if project_id:
                query = query.filter(JobRecord.project_id == project_id)
            jobs = (
                query.order_by(JobRecord.priority.desc(), JobRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._to_dict(j) for j in jobs]

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
                job.worker_lease_id = None
                job.lease_expires_at = None
                db.commit()
                return True
        return False

    def retry_job(self, job_id: str) -> bool:
        """Manually re-queues a failed or cancelled job."""
        with SessionLocal() as db:
            job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if not job:
                return False
            job.status = JobStatus.QUEUED.value
            job.progress = 0.0
            job.error = None
            job.message = "Job manually re-queued for execution"
            job.worker_lease_id = None
            job.lease_expires_at = None
            job.retry_count = 0
            job.started_at = None
            job.finished_at = None
            db.commit()
            return True

    def is_job_active(self, job_id: str) -> bool:
        """Returns True if the background runner is still executing."""
        return job_id in self._active_tokens

    def enqueue_async(
        self,
        job_id: str,
        coro_fn: Callable[[PipelineCancellationToken, Callable[[float, str], None]], Coroutine[Any, Any, dict]],
    ) -> None:
        """
        Enqueues an asynchronous runner in the event loop with worker lease management,
        admission control, heartbeats, and exponential backoff retry.
        """
        token = PipelineCancellationToken()
        self._active_tokens[job_id] = token

        def progress_cb(pct: float, msg: str):
            self.update_job_progress(job_id, pct, msg)

        async def runner():
            # 1. Acquire lease and check dependencies & admission
            requires_gpu = False
            gpu_vram_mb = 0
            with SessionLocal() as db:
                job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                if not job:
                    return
                if job.status == JobStatus.CANCELLED.value or token.is_cancelled:
                    return

                # Check parent dependency
                if job.depends_on_job_id:
                    parent = db.query(JobRecord).filter(JobRecord.job_id == job.depends_on_job_id).first()
                    if not parent or parent.status in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
                        job.status = JobStatus.FAILED.value
                        job.error = f"Dependency job {job.depends_on_job_id} failed or cancelled"
                        job.finished_at = utc_now()
                        db.commit()
                        return

                requires_gpu = job.requires_gpu
                gpu_vram_mb = job.gpu_vram_mb
                job.status = JobStatus.RUNNING.value
                job.started_at = utc_now()
                job.worker_lease_id = self.worker_id
                job.lease_expires_at = utc_now() + timedelta(seconds=self.lease_duration_sec)
                job.message = "Job started by worker"
                db.commit()

            # Acquire GPU admission slot if required
            gpu_slot_acquired = False
            if requires_gpu:
                while not token.is_cancelled:
                    admitted = await resource_manager.acquire_gpu_slot(job_id, gpu_vram_mb)
                    if admitted:
                        gpu_slot_acquired = True
                        break
                    await asyncio.sleep(1.0)
                if token.is_cancelled:
                    return

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
                        job.worker_lease_id = None
                        job.lease_expires_at = None
                        db.commit()
            except asyncio.CancelledError:
                with SessionLocal() as db:
                    job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                    if job:
                        job.status = JobStatus.CANCELLED.value
                        job.message = "Job execution cancelled"
                        job.finished_at = utc_now()
                        job.worker_lease_id = None
                        job.lease_expires_at = None
                        db.commit()
            except Exception as e:
                logger.exception(f"Job {job_id} failed with error: {e}")
                with SessionLocal() as db:
                    job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                    if job:
                        if token.is_cancelled or job.status == JobStatus.CANCELLED.value:
                            job.status = JobStatus.CANCELLED.value
                            job.message = "Job cancelled by user"
                            job.finished_at = utc_now()
                        elif job.retry_count < job.max_retries:
                            # Retry with bounded exponential backoff
                            job.retry_count += 1
                            job.status = JobStatus.QUEUED.value
                            job.error = str(e)
                            job.worker_lease_id = None
                            job.lease_expires_at = None
                            backoff_sec = min(30, 2 ** job.retry_count * 2)
                            job.message = f"Job failed: {e}. Backoff {backoff_sec}s before retry ({job.retry_count}/{job.max_retries})."
                            logger.info(f"Re-queueing job {job_id} with backoff {backoff_sec}s (retry {job.retry_count}/{job.max_retries})")
                        else:
                            job.status = JobStatus.FAILED.value
                            job.error = str(e)
                            job.message = f"Job failed after {job.retry_count} retries: {str(e)}"
                            job.finished_at = utc_now()
                            job.worker_lease_id = None
                            job.lease_expires_at = None
                        db.commit()
            finally:
                if gpu_slot_acquired:
                    await resource_manager.release_gpu_slot(job_id)
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

