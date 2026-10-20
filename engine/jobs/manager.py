import asyncio
import logging
import threading
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


class _LeaseCancellationToken(PipelineCancellationToken):
    """Cooperative cancellation also fences a worker after lease loss."""

    def __init__(self, manager: "JobManager", job_id: str, lease_id: str):
        super().__init__()
        self.manager = manager
        self.job_id = job_id
        self.lease_id = lease_id
        self.claimed = False

    @property
    def is_cancelled(self) -> bool:
        return super().is_cancelled or (self.claimed and not self.manager._lease_is_current(self.job_id, self.lease_id))


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
        self._state_lock = threading.RLock()
        self._active_tokens: dict[str, PipelineCancellationToken] = {}
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._retry_handles: dict[str, threading.Timer] = {}
        self._operation_handlers: dict[str, Callable] = {}

    def _retire_expired_local_worker(self, job: JobRecord) -> bool:
        """Fence a local worker only after its persisted lease has expired."""
        with self._state_lock:
            token = self._active_tokens.get(job.job_id)
            if token is None:
                return True
            if (job.status != JobStatus.RUNNING.value or job.lease_expires_at is None
                    or job.lease_expires_at.replace(tzinfo=timezone.utc) >= utc_now()):
                return False
            token.cancel()
            self._active_tokens.pop(job.job_id, None)
            self._active_tasks.pop(job.job_id, None)
            return True

    def _resolve_operation_handler(self, job: JobRecord) -> Callable | None:
        with self._state_lock:
            handler = self._operation_handlers.get(job.job_id)
        if handler:
            return handler
        try:
            from engine.jobs.workflow import rehydrate_job_runner

            handler = rehydrate_job_runner(job)
        except Exception as exc:
            logger.warning("Could not rehydrate job %s: %s", job.job_id, exc)
            return None
        if handler:
            with self._state_lock:
                self._operation_handlers[job.job_id] = handler
        return handler

    def _mark_unrecoverable(self, job: JobRecord, message: str) -> None:
        job.status = JobStatus.FAILED.value
        job.error = message
        job.message = message
        job.finished_at = utc_now()
        job.worker_lease_id = None
        job.lease_expires_at = None

    def _lease_is_current(self, job_id: str, lease_id: str) -> bool:
        with SessionLocal() as db:
            return db.query(JobRecord).filter(
                JobRecord.job_id == job_id,
                JobRecord.status == JobStatus.RUNNING.value,
                JobRecord.worker_lease_id == lease_id,
                JobRecord.lease_expires_at > utc_now(),
            ).first() is not None

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
        """Requeue recoverable interrupted jobs; fail closed when no handler exists."""
        to_enqueue: list[tuple[str, Callable]] = []
        with SessionLocal() as db:
            interrupted_jobs = (
                db.query(JobRecord)
                .filter(JobRecord.status.in_((JobStatus.RUNNING.value, JobStatus.QUEUED.value)))
                .all()
            )
            count = 0
            now = utc_now()
            for job in interrupted_jobs:
                if not self._retire_expired_local_worker(job):
                    continue
                if job.status == JobStatus.RUNNING.value and job.lease_expires_at and job.lease_expires_at.replace(tzinfo=timezone.utc) >= now:
                    continue
                handler = self._resolve_operation_handler(job)
                recoverable = job.status == JobStatus.QUEUED.value or job.retry_count < job.max_retries
                old_status, old_lease = job.status, job.worker_lease_id
                conditions = [JobRecord.job_id == job.job_id, JobRecord.status == old_status]
                if old_status == JobStatus.RUNNING.value:
                    conditions.extend((JobRecord.worker_lease_id == old_lease,
                                       (JobRecord.lease_expires_at == None) | (JobRecord.lease_expires_at < now)))
                values = {JobRecord.worker_lease_id: None, JobRecord.lease_expires_at: None}
                if handler and recoverable:
                    values.update({JobRecord.status: JobStatus.QUEUED.value,
                                   JobRecord.retry_count: job.retry_count + (old_status == JobStatus.RUNNING.value),
                                   JobRecord.message: "Interrupted job re-queued for durable recovery"})
                else:
                    message = "Interrupted job has no rehydratable operation or retries remain; submit it again after restart."
                    values.update({JobRecord.status: JobStatus.FAILED.value, JobRecord.error: message,
                                   JobRecord.message: message, JobRecord.finished_at: now})
                updated = db.query(JobRecord).filter(*conditions).update(values, synchronize_session=False)
                if updated:
                    count += updated
                    if handler and recoverable:
                        to_enqueue.append((job.job_id, handler))
            if count:
                db.commit()
                logger.info("Recovered %s interrupted jobs", count)
        for job_id, handler in to_enqueue:
            self.enqueue_async(job_id, handler)
        return count

    def recover_expired_leases(self) -> int:
        """Requeue expired jobs only when their operation can be rehydrated."""
        to_enqueue: list[tuple[str, Callable]] = []
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
            for job in expired_jobs:
                if not self._retire_expired_local_worker(job):
                    continue
                handler = self._resolve_operation_handler(job)
                old_lease_id = job.worker_lease_id
                if handler and job.retry_count < job.max_retries:
                    next_retry = job.retry_count + 1
                    updated = db.query(JobRecord).filter(
                        JobRecord.job_id == job.job_id,
                        JobRecord.status == JobStatus.RUNNING.value,
                        JobRecord.worker_lease_id == old_lease_id,
                        JobRecord.lease_expires_at < now,
                    ).update(
                        {
                            JobRecord.retry_count: next_retry,
                            JobRecord.status: JobStatus.QUEUED.value,
                            JobRecord.worker_lease_id: None,
                            JobRecord.lease_expires_at: None,
                            JobRecord.message: f"Lease expired; re-queued ({next_retry}/{job.max_retries})",
                        },
                        synchronize_session=False,
                    )
                    if updated == 1:
                        to_enqueue.append((job.job_id, handler))
                else:
                    message = "Worker lease expired and the operation cannot be rehydrated or retried; submit it again."
                    updated = db.query(JobRecord).filter(
                        JobRecord.job_id == job.job_id,
                        JobRecord.status == JobStatus.RUNNING.value,
                        JobRecord.worker_lease_id == old_lease_id,
                        JobRecord.lease_expires_at < now,
                    ).update({JobRecord.status: JobStatus.FAILED.value, JobRecord.error: message,
                              JobRecord.message: message, JobRecord.finished_at: now,
                              JobRecord.worker_lease_id: None, JobRecord.lease_expires_at: None},
                             synchronize_session=False)
                count += updated
            if count:
                db.commit()
                logger.info("Recovered %s jobs with expired worker leases", count)
        for job_id, handler in to_enqueue:
            self.enqueue_async(job_id, handler)
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
            lease_id = f"{self.worker_id}:{uuid.uuid4().hex}"
            now = utc_now()
            claimed = db.query(JobRecord).filter(
                JobRecord.job_id == job_id,
                JobRecord.status == JobStatus.QUEUED.value,
            ).update(
                {
                    JobRecord.status: JobStatus.RUNNING.value,
                    JobRecord.started_at: now,
                    JobRecord.worker_lease_id: lease_id,
                    JobRecord.lease_expires_at: now + timedelta(seconds=self.lease_duration_sec),
                    JobRecord.message: "Job claimed by worker lease",
                },
                synchronize_session=False,
            )
            db.commit()
            return claimed == 1

    def update_job_progress(
        self,
        job_id: str,
        progress: float,
        message: str,
        output_patch: dict | None = None,
        lease_id: str | None = None,
    ) -> None:
        with SessionLocal() as db:
            job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if not job:
                return
            now = utc_now()
            values = {
                JobRecord.progress: max(0.0, min(1.0, progress)),
                JobRecord.message: message,
                JobRecord.lease_expires_at: now + timedelta(seconds=self.lease_duration_sec),
            }
            if output_patch:
                values[JobRecord.output] = {**(job.output or {}), **output_patch}
            db.query(JobRecord).filter(
                JobRecord.job_id == job_id,
                JobRecord.status == JobStatus.RUNNING.value,
                JobRecord.worker_lease_id == (lease_id or self.worker_id),
                JobRecord.lease_expires_at > now,
            ).update(values, synchronize_session=False)
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
        with self._state_lock:
            retry_handle = self._retry_handles.pop(job_id, None)
            token = self._active_tokens.get(job_id)
            task = self._active_tasks.get(job_id)
        if retry_handle:
            retry_handle.cancel()
        if token:
            token.cancel()
        if task and not task.done():
            loop = task.get_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(task.cancel)

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
        """Requeue a terminal job only when its operation can be rehydrated."""
        handler = None
        with SessionLocal() as db:
            job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
            if not job or job.status not in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
                return False
            handler = self._resolve_operation_handler(job)
            if not handler:
                self._mark_unrecoverable(
                    job,
                    "Job cannot be retried because its operation handler is unavailable; submit it again.",
                )
                db.commit()
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
        self.enqueue_async(job_id, handler)
        return True

    def is_job_active(self, job_id: str) -> bool:
        """Returns True if the background runner is still executing."""
        with self._state_lock:
            return job_id in self._active_tokens

    def _clear_active(self, job_id: str, token: PipelineCancellationToken | None = None) -> None:
        with self._state_lock:
            if token is not None and self._active_tokens.get(job_id) is not token:
                return
            self._active_tokens.pop(job_id, None)
            task = self._active_tasks.get(job_id)
            if task is None or task.done() or task is asyncio.current_task():
                self._active_tasks.pop(job_id, None)

    def _schedule_retry(
        self,
        job_id: str,
        coro_fn: Callable[[PipelineCancellationToken, Callable[[float, str], None]], Coroutine[Any, Any, dict]],
        delay_sec: float,
    ) -> None:
        with self._state_lock:
            existing = self._retry_handles.pop(job_id, None)
        if existing:
            existing.cancel()

        def enqueue_if_still_queued() -> None:
            with self._state_lock:
                self._retry_handles.pop(job_id, None)
                already_active = job_id in self._active_tokens
            with SessionLocal() as db:
                job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                if not job or job.status != JobStatus.QUEUED.value or already_active:
                    return
            self.enqueue_async(job_id, coro_fn)

        handle = threading.Timer(delay_sec, enqueue_if_still_queued)
        handle.daemon = True
        with self._state_lock:
            self._retry_handles[job_id] = handle
        handle.start()

    def enqueue_async(
        self,
        job_id: str,
        coro_fn: Callable[[PipelineCancellationToken, Callable[[float, str], None]], Coroutine[Any, Any, dict]],
    ) -> None:
        """Enqueue one runner with lease, admission, cancellation and bounded retry."""
        with self._state_lock:
            if job_id in self._active_tokens:
                logger.info("Ignoring duplicate enqueue for active job %s", job_id)
                return
            pending_retry = self._retry_handles.pop(job_id, None)
            lease_id = f"{self.worker_id}:{uuid.uuid4().hex}"
            token = _LeaseCancellationToken(self, job_id, lease_id)
            self._active_tokens[job_id] = token
            self._operation_handlers[job_id] = coro_fn
        if pending_retry:
            pending_retry.cancel()

        current_progress = [0.0, "Starting analysis"]

        def progress_cb(pct: float, msg: str):
            current_progress[:] = [pct, msg]
            self.update_job_progress(job_id, pct, msg, lease_id=lease_id)

        def model_activity(activity):
            self.update_job_progress(job_id, current_progress[0], current_progress[1],
                                     output_patch={"model_activity": {**activity, "updated_at": utc_now().isoformat()}},
                                     lease_id=lease_id)

        async def runner():
            gpu_slot_acquired = False
            heartbeat_task = None
            succeeded = False
            requires_gpu = False
            gpu_vram_mb = 0
            try:
                with SessionLocal() as db:
                    job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                    if job is None or job.status != JobStatus.QUEUED.value or token.is_cancelled:
                        return

                    if job.depends_on_job_id:
                        parent = db.query(JobRecord).filter(JobRecord.job_id == job.depends_on_job_id).first()
                        if not parent or parent.status in (JobStatus.FAILED.value, JobStatus.CANCELLED.value):
                            job.status = JobStatus.FAILED.value
                            job.error = f"Dependency job {job.depends_on_job_id} failed or cancelled"
                            job.finished_at = utc_now()
                            db.commit()
                            return

                    requires_gpu = bool(job.requires_gpu)
                    gpu_vram_mb = float(job.gpu_vram_mb or 0)
                    now = utc_now()
                    claimed = db.query(JobRecord).filter(
                        JobRecord.job_id == job_id,
                        JobRecord.status == JobStatus.QUEUED.value,
                    ).update(
                        {
                            JobRecord.status: JobStatus.RUNNING.value,
                            JobRecord.started_at: now,
                            JobRecord.worker_lease_id: lease_id,
                            JobRecord.lease_expires_at: now + timedelta(seconds=self.lease_duration_sec),
                            JobRecord.message: "Job started by worker",
                        },
                        synchronize_session=False,
                    )
                    db.commit()
                    if claimed != 1:
                        return
                token.claimed = True

                async def heartbeat():
                    while True:
                        await asyncio.sleep(self.lease_duration_sec / 3)
                        with SessionLocal() as heartbeat_db:
                            renewed = heartbeat_db.query(JobRecord).filter(
                                JobRecord.job_id == job_id,
                                JobRecord.status == JobStatus.RUNNING.value,
                                JobRecord.worker_lease_id == lease_id,
                                JobRecord.lease_expires_at > utc_now(),
                            ).update({JobRecord.lease_expires_at: utc_now() + timedelta(seconds=self.lease_duration_sec)},
                                     synchronize_session=False)
                            heartbeat_db.commit()
                        if not renewed:
                            token.cancel()
                            return

                heartbeat_task = asyncio.create_task(heartbeat())
                if requires_gpu:
                    while not token.is_cancelled:
                        if not self._lease_is_current(job_id, lease_id):
                            return
                        if await resource_manager.acquire_gpu_slot(lease_id, gpu_vram_mb):
                            gpu_slot_acquired = True
                            break
                        await asyncio.sleep(1.0)
                    if token.is_cancelled:
                        return

                if not self._lease_is_current(job_id, lease_id):
                    return
                from engine.llm.activity import activity_sink, generation_cancelled
                activity_context = activity_sink.set(model_activity)
                cancellation_context = generation_cancelled.set(lambda: token.is_cancelled)
                try:
                    output = await coro_fn(token, progress_cb)
                finally:
                    activity_sink.reset(activity_context)
                    generation_cancelled.reset(cancellation_context)
                with SessionLocal() as db:
                    now = utc_now()
                    cancelled = token.is_cancelled
                    terminal = {
                        JobRecord.status: JobStatus.CANCELLED.value if cancelled else JobStatus.SUCCEEDED.value,
                        JobRecord.message: "Job cancelled by user" if cancelled else "Job completed successfully",
                        JobRecord.finished_at: now,
                        JobRecord.worker_lease_id: None,
                        JobRecord.lease_expires_at: None,
                    }
                    if not cancelled:
                        terminal.update({JobRecord.progress: 1.0, JobRecord.output: output or {}})
                    succeeded = bool(db.query(JobRecord).filter(
                        JobRecord.job_id == job_id,
                        JobRecord.status == JobStatus.RUNNING.value,
                        JobRecord.worker_lease_id == lease_id,
                        JobRecord.lease_expires_at > now,
                    ).update(terminal, synchronize_session=False)) and not cancelled
                    db.commit()
                if succeeded:
                    with self._state_lock:
                        self._operation_handlers.pop(job_id, None)
            except asyncio.CancelledError:
                with SessionLocal() as db:
                    now = utc_now()
                    db.query(JobRecord).filter(
                        JobRecord.job_id == job_id, JobRecord.status == JobStatus.RUNNING.value,
                        JobRecord.worker_lease_id == lease_id,
                        JobRecord.lease_expires_at > now,
                    ).update({JobRecord.status: JobStatus.CANCELLED.value,
                              JobRecord.message: "Job execution cancelled", JobRecord.finished_at: now,
                              JobRecord.worker_lease_id: None, JobRecord.lease_expires_at: None},
                             synchronize_session=False)
                    db.commit()
            except Exception as exc:
                logger.exception("Job %s failed with error: %s", job_id, exc)
                retry_delay = None
                with SessionLocal() as db:
                    job = db.query(JobRecord).filter(JobRecord.job_id == job_id).first()
                    now = utc_now()
                    if job:
                        values = {JobRecord.worker_lease_id: None, JobRecord.lease_expires_at: None,
                                  JobRecord.error: str(exc)}
                        if token.is_cancelled:
                            values.update({JobRecord.status: JobStatus.CANCELLED.value,
                                           JobRecord.message: "Job cancelled by user", JobRecord.finished_at: now})
                        elif job.retry_count < job.max_retries and getattr(exc, "retryable", True):
                            next_retry = job.retry_count + 1
                            retry_delay = min(30, 2 ** next_retry * 2)
                            values.update({JobRecord.retry_count: next_retry, JobRecord.status: JobStatus.QUEUED.value,
                                           JobRecord.message: f"Job failed: {exc}. Backoff {retry_delay}s before retry ({next_retry}/{job.max_retries})."})
                        else:
                            values.update({JobRecord.status: JobStatus.FAILED.value,
                                           JobRecord.message: (f"Job stopped for review: {exc}" if not getattr(exc, "retryable", True)
                                                               else f"Job failed after {job.retry_count} retries: {exc}"),
                                           JobRecord.finished_at: now})
                        changed = db.query(JobRecord).filter(
                            JobRecord.job_id == job_id, JobRecord.status == JobStatus.RUNNING.value,
                            JobRecord.worker_lease_id == lease_id, JobRecord.lease_expires_at > now,
                        ).update(values, synchronize_session=False)
                        db.commit()
                        if changed and retry_delay is not None:
                            self._schedule_retry(job_id, coro_fn, retry_delay)
            finally:
                if heartbeat_task:
                    heartbeat_task.cancel()
                if gpu_slot_acquired:
                    await resource_manager.release_gpu_slot(lease_id)
                self._clear_active(job_id, token)

        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(runner())
            with self._state_lock:
                self._active_tasks[job_id] = task
        except RuntimeError:
            import threading
            def bg_thread():
                asyncio.run(runner())
            t = threading.Thread(target=bg_thread, daemon=True)
            t.start()


job_manager = JobManager()

