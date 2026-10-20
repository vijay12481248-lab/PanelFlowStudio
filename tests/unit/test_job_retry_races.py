import time

from engine.acquisition.models import JobStatus
from engine.database.models import Base, JobRecord, ProjectRecord
from engine.database.session import SessionLocal, engine, run_sqlite_migrations
from engine.jobs.manager import JobManager
from engine.jobs.workflow import _OPERATION_FACTORIES, register_operation_factory


def _ensure_project(project_id: str) -> None:
    with SessionLocal() as db:
        if not db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first():
            db.add(
                ProjectRecord(
                    id=project_id,
                    title="Retry test project",
                    source_type="LOCAL_FOLDER",
                    rights_status="PUBLIC_DOMAIN",
                    workspace_path="/tmp/test",
                )
            )
            db.commit()


def test_sync_enqueue_retries_after_temporary_loop_closes():
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    project_id = "test_retry_sync_loop"
    _ensure_project(project_id)
    manager = JobManager()
    job = manager.create_job(project_id=project_id, job_type="STORY_ANALYSIS", max_retries=1)
    attempts = []

    async def flaky_job(token, progress_cb):
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            raise RuntimeError("temporary failure")
        return {"attempt": len(attempts)}

    # No running event loop here: this exercises the synchronous fallback thread.
    manager.enqueue_async(job.job_id, flaky_job)
    deadline = time.time() + 8.0
    while time.time() < deadline:
        current = manager.get_job(job.job_id)
        if current and current["status"] in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
            break
        time.sleep(0.1)

    current = manager.get_job(job.job_id)
    assert current["status"] == JobStatus.SUCCEEDED.value
    assert attempts == [1, 2]
    assert not manager.is_job_active(job.job_id)

def test_manual_retry_rehydrates_registered_operation_from_persisted_input():
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    project_id = "test_retry_rehydration"
    _ensure_project(project_id)
    manager = JobManager()
    job = manager.create_job(
        project_id=project_id,
        job_type="TEST_REHYDRATED_OPERATION",
        job_input={"value": 42},
        max_retries=0,
    )
    with SessionLocal() as db:
        record = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        record.status = JobStatus.FAILED.value
        record.error = "initial failure"
        db.commit()

    observed = []

    def factory(factory_project_id, payload):
        assert factory_project_id == project_id
        assert payload == {"value": 42}

        def operation(db, progress, is_cancelled):
            observed.append(payload["value"])
            return {"value": payload["value"]}

        return operation

    register_operation_factory("TEST_REHYDRATED_OPERATION", factory)
    assert manager.retry_job(job.job_id) is True

    deadline = time.time() + 8.0
    while time.time() < deadline:
        current = manager.get_job(job.job_id)
        if current and current["status"] in {JobStatus.SUCCEEDED.value, JobStatus.FAILED.value}:
            break
        time.sleep(0.1)

    current = manager.get_job(job.job_id)
    assert current["status"] == JobStatus.SUCCEEDED.value
    assert current["output"] == {"value": 42}
    assert observed == [42]


def test_builtin_operation_factories_are_available_without_api_router_import():
    expected = {
        "ACQUISITION", "RETRY_PAGES", "NORMALIZATION", "PANEL_DETECTION",
        "OCR_EXTRACTION", "STORY_ANALYSIS", "SCRIPT_GENERATION",
        "AUDIO_GENERATION", "COMFYUI_IMAGE_GENERATION",
    }
    assert expected <= set(_OPERATION_FACTORIES)


def test_stale_worker_cannot_update_reclaimed_job_lease():
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    project_id = "test_lease_fencing"
    _ensure_project(project_id)
    manager = JobManager()
    job = manager.create_job(project_id=project_id, job_type="LEASE_FENCE", max_retries=0)
    with SessionLocal() as db:
        record = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        record.status = JobStatus.RUNNING.value
        record.progress = 0.1
        record.worker_lease_id = "new-worker"
        db.commit()

    manager.update_job_progress(job.job_id, 0.9, "stale worker update")

    current = manager.get_job(job.job_id)
    assert current["progress"] == 0.1
    assert current["message"] != "stale worker update"
