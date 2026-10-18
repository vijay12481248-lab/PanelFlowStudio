import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from engine.system.resources import SystemResourceManager
from engine.jobs.manager import JobManager
from engine.database.session import SessionLocal
from engine.database.models import JobRecord
from engine.acquisition.models import JobStatus
from engine.database.session import engine, run_sqlite_migrations
from engine.database.models import Base


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)


@pytest.mark.asyncio
async def test_resource_manager_concurrency_configuration():
    """Verify concurrency mode updates and boundary clamping."""
    mgr = SystemResourceManager()

    # Manual mode with valid limit
    res = mgr.set_concurrency("MANUAL", 2)
    assert res["concurrency_mode"] == "MANUAL"
    assert res["max_gpu_concurrency"] == 2

    # Clamping: minimum is 1, maximum is 4
    res_min = mgr.set_concurrency("MANUAL", 0)
    assert res_min["max_gpu_concurrency"] == 1

    res_max = mgr.set_concurrency("MANUAL", 10)
    assert res_max["max_gpu_concurrency"] == 4

    # Invalid mode
    with pytest.raises(ValueError, match="Invalid concurrency mode"):
        mgr.set_concurrency("INVALID_MODE", 1)


@pytest.mark.asyncio
async def test_resource_manager_admission_slot_gating():
    """Verify atomic acquire and release of GPU admission slots."""
    mgr = SystemResourceManager()
    mgr.set_concurrency("MANUAL", 1)

    # First acquire should succeed
    acquired_1 = await mgr.acquire_gpu_slot("job_test_01")
    assert acquired_1 is True
    assert mgr.active_gpu_jobs_count == 1

    # Second acquire should be rejected because max concurrency is 1
    acquired_2 = await mgr.acquire_gpu_slot("job_test_02")
    assert acquired_2 is False
    assert mgr.active_gpu_jobs_count == 1

    # Release first job
    await mgr.release_gpu_slot("job_test_01")
    assert mgr.active_gpu_jobs_count == 0

    # Now second job can acquire
    acquired_2_retry = await mgr.acquire_gpu_slot("job_test_02")
    assert acquired_2_retry is True
    assert mgr.active_gpu_jobs_count == 1

    # Cleanup
    await mgr.release_gpu_slot("job_test_02")


def _ensure_project(project_id: str):
    from engine.database.models import ProjectRecord
    with SessionLocal() as db:
        if not db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first():
            proj = ProjectRecord(
                id=project_id,
                title=f"Project {project_id}",
                source_type="LOCAL_FOLDER",
                rights_status="PUBLIC_DOMAIN",
                workspace_path="/tmp/test",
            )
            db.add(proj)
            db.commit()


def test_job_manager_create_and_lease():
    """Verify job record creation with resource metadata and lease allocation."""
    _ensure_project("test_proj_queue_01")
    jm = JobManager()

    job = jm.create_job(
        project_id="test_proj_queue_01",
        job_type="STORY_ANALYSIS",
        priority=20,
        requires_gpu=True,
        gpu_vram_mb=6144,
        max_retries=3,
    )

    assert job.job_id is not None
    assert job.status == JobStatus.QUEUED.value
    assert job.priority == 20
    assert job.requires_gpu is True
    assert job.gpu_vram_mb == 6144
    assert job.worker_lease_id is None

    # Test lease claiming
    claimed = jm.claim_job_lease(job.job_id)
    assert claimed is True

    with SessionLocal() as db:
        updated = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        assert updated.status == JobStatus.RUNNING.value
        assert updated.worker_lease_id == jm.worker_id
        assert updated.lease_expires_at is not None


def test_job_manager_lease_heartbeat():
    """Verify progress updates extend the worker lease expiry time."""
    _ensure_project("test_proj_queue_02")
    jm = JobManager()

    job = jm.create_job(
        project_id="test_proj_queue_02",
        job_type="GENERATE_SCRIPT",
    )
    jm.claim_job_lease(job.job_id)

    with SessionLocal() as db:
        initial = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        initial_expiry = initial.lease_expires_at

    # Update progress
    jm.update_job_progress(job.job_id, 0.5, "Halfway done")

    with SessionLocal() as db:
        refreshed = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        assert refreshed.progress == 0.5
        assert refreshed.message == "Halfway done"
        # Heartbeat should have pushed expiry forward or equal
        assert refreshed.lease_expires_at >= initial_expiry


def test_job_manager_recover_expired_leases():
    """Verify expired worker leases are automatically re-queued up to max_retries."""
    _ensure_project("test_proj_queue_03")
    jm = JobManager()

    job = jm.create_job(
        project_id="test_proj_queue_03",
        job_type="DETECT_PANELS",
        max_retries=2,
    )
    jm.claim_job_lease(job.job_id)

    # Force the lease to be expired in the past
    past_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    with SessionLocal() as db:
        j = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        j.lease_expires_at = past_time
        db.commit()

    # Run expired lease recovery
    recovered_count = jm.recover_expired_leases()
    assert recovered_count >= 1

    with SessionLocal() as db:
        j = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        # Should be re-queued with retry_count = 1
        assert j.status == JobStatus.QUEUED.value
        assert j.retry_count == 1
        assert j.worker_lease_id is None

        # Force second expiration
        j.status = JobStatus.RUNNING.value
        j.lease_expires_at = past_time
        j.retry_count = 2  # At max_retries
        db.commit()

    # Second recovery when retries exhausted
    jm.recover_expired_leases()

    with SessionLocal() as db:
        j = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        # Should now be marked FAILED
        assert j.status == JobStatus.FAILED.value
        assert "max retries exceeded" in (j.error or "").lower()
