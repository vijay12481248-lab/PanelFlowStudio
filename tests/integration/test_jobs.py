import asyncio
from pathlib import Path
import pytest
from engine.config.settings import settings
from engine.jobs.manager import job_manager
from engine.acquisition.models import JobType, JobStatus
from engine.database.session import init_db, SessionLocal
from engine.database.models import ProjectRecord, JobRecord

@pytest.fixture(autouse=True)
def setup_database():
    from engine.database.models import Base
    from engine.database.session import engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

@pytest.mark.asyncio
async def test_job_lifecycle_and_cancellation():
    with SessionLocal() as db:
        proj = ProjectRecord(
            id="test-proj-jobs-1",
            title="Job Test Project 1",
            source_type="LOCAL_FOLDER",
            rights_status="PUBLIC_DOMAIN",
            workspace_path="/dummy1",
        )
        db.add(proj)
        db.commit()

    # Part A: Test cancellation while QUEUED
    queued_job = job_manager.create_job(
        project_id="test-proj-jobs-1",
        job_type=JobType.ACQUISITION,
        job_input={"test": True},
    )
    assert queued_job.status == JobStatus.QUEUED.value

    job_manager.cancel_job(queued_job.job_id)
    retrieved = job_manager.get_job(queued_job.job_id)
    assert retrieved["status"] == JobStatus.CANCELLED.value

    # Part B: Deterministic long-running job: QUEUED -> RUNNING -> cancellation requested -> CANCELLED
    running_job = job_manager.create_job(
        project_id="test-proj-jobs-1",
        job_type=JobType.ACQUISITION,
        job_input={"test_long_running": True},
    )
    assert running_job.status == JobStatus.QUEUED.value

    completed_steps = []
    unfinished_steps = []

    async def long_running_coro(token, progress_cb):
        # 10 discrete steps with delay allowing deterministic cancellation during RUNNING
        for step in range(1, 11):
            if token.is_cancelled:
                unfinished_steps.append(step)
                return {"completed": completed_steps, "cancelled_at_step": step}
            await asyncio.sleep(0.08)
            completed_steps.append(step)
            progress_cb(step / 10.0, f"Processing step {step}/10")
        return {"completed": completed_steps}

    job_manager.enqueue_async(running_job.job_id, long_running_coro)

    # Poll until job enters RUNNING state
    is_running = False
    for _ in range(20):
        current_status = job_manager.get_job(running_job.job_id)
        if current_status["status"] == JobStatus.RUNNING.value:
            is_running = True
            break
        await asyncio.sleep(0.02)
    assert is_running is True, "Job failed to transition to RUNNING state"

    # Wait until at least step 1 has completed
    for _ in range(20):
        if len(completed_steps) >= 1:
            break
        await asyncio.sleep(0.02)
    assert len(completed_steps) >= 1, "Job did not complete initial work step before cancellation"

    # Issue cancellation request while RUNNING
    cancelled_ok = job_manager.cancel_job(running_job.job_id)
    assert cancelled_ok is True

    # Wait for background runner to complete
    for _ in range(30):
        current = job_manager.get_job(running_job.job_id)
        if current["status"] in (JobStatus.CANCELLED.value, JobStatus.SUCCEEDED.value, JobStatus.FAILED.value):
            break
        await asyncio.sleep(0.05)

    final_job = job_manager.get_job(running_job.job_id)

    # 1. Assert final status == CANCELLED (Never SUCCEEDED)
    assert final_job["status"] == JobStatus.CANCELLED.value, f"Expected CANCELLED but got {final_job['status']}"

    # 2. Verify completed work before cancellation remains valid
    assert len(completed_steps) >= 1
    assert len(completed_steps) < 10, "Job ran all steps despite cancellation"

    # 3. Verify unfinished work was not marked successful
    assert 10 not in completed_steps

    # 4. Verify simulated application restart does not incorrectly resume or mutate the cancelled job
    recovered_count = job_manager.recover_interrupted_jobs()
    post_restart_job = job_manager.get_job(running_job.job_id)
    assert post_restart_job["status"] == JobStatus.CANCELLED.value

def test_crash_recovery():
    with SessionLocal() as db:
        proj = ProjectRecord(
            id="test-proj-jobs-2",
            title="Job Test Project 2",
            source_type="LOCAL_FOLDER",
            rights_status="PUBLIC_DOMAIN",
            workspace_path="/dummy2",
        )
        db.add(proj)
        # Simulate a job left in RUNNING state prior to a sudden crash
        crashed_job = JobRecord(
            job_id="crashed-job-123",
            project_id="test-proj-jobs-2",
            job_type="ACQUISITION",
            status=JobStatus.RUNNING.value,
            progress=0.45,
            message="Downloading page 10",
        )
        db.add(crashed_job)
        db.commit()

    # Trigger crash recovery
    recovered_count = job_manager.recover_interrupted_jobs()
    assert recovered_count >= 1

    with SessionLocal() as db:
        job = db.query(JobRecord).filter(JobRecord.job_id == "crashed-job-123").first()
        assert job.status == JobStatus.FAILED.value
        assert "interrupted" in job.message.lower() or "terminated" in (job.error or "").lower()
        assert job.finished_at is not None
