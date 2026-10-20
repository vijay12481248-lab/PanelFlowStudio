import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from engine.acquisition.models import JobStatus
from engine.database.models import Base, JobRecord, ProjectRecord
from engine.database.session import SessionLocal, engine, run_sqlite_migrations
from engine.jobs.manager import JobManager
from engine.jobs.workflow import _runner


@pytest.fixture
def manager():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    run_sqlite_migrations(engine)
    with SessionLocal() as db:
        if not db.get(ProjectRecord, 'recovery-boundaries'):
            db.add(ProjectRecord(id='recovery-boundaries', title='Recovery boundaries', source_type='LOCAL_FOLDER', rights_status='PUBLIC_DOMAIN', workspace_path='/dummy'))
            db.commit()
    return JobManager()


def set_running(job_id, lease, expiry):
    with SessionLocal() as db:
        job = db.query(JobRecord).filter_by(job_id=job_id).one()
        job.status = JobStatus.RUNNING.value
        job.worker_lease_id = lease
        job.lease_expires_at = expiry
        db.commit()


def test_startup_does_not_reclaim_live_foreign_lease(manager, monkeypatch):
    job = manager.create_job('recovery-boundaries', 'UNKNOWN_LIVE')
    set_running(job.job_id, 'other-worker:live', datetime.now(timezone.utc) + timedelta(minutes=5))
    monkeypatch.setattr(manager, 'enqueue_async', lambda *a: pytest.fail('live lease requeued'))
    assert manager.recover_interrupted_jobs() == 0
    assert manager.get_job(job.job_id)['status'] == JobStatus.RUNNING.value
    assert manager.get_job(job.job_id)['worker_lease_id'] == 'other-worker:live'


def test_expired_unrecoverable_transition_is_conditional_and_counted_only_if_changed(manager, monkeypatch):
    job = manager.create_job('recovery-boundaries', 'UNKNOWN_EXPIRED')
    set_running(job.job_id, 'expired:old', datetime.now(timezone.utc) - timedelta(minutes=5))
    original = manager._resolve_operation_handler
    def race(record):
        with SessionLocal() as db:
            current = db.query(JobRecord).filter_by(job_id=record.job_id).one()
            current.worker_lease_id = 'replacement:new'
            current.lease_expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
            db.commit()
        return None
    monkeypatch.setattr(manager, '_resolve_operation_handler', race)
    assert manager.recover_expired_leases() == 0
    assert manager.get_job(job.job_id)['status'] == JobStatus.RUNNING.value
    assert manager.get_job(job.job_id)['worker_lease_id'] == 'replacement:new'


@pytest.mark.asyncio
async def test_lost_lease_before_gpu_admission_skips_operation_and_releases_slot(manager, monkeypatch):
    job = manager.create_job('recovery-boundaries', 'GPU_FENCE', requires_gpu=True)
    executed = []
    released = []
    async def acquire(lease, amount):
        set_running(job.job_id, 'replacement:new', datetime.now(timezone.utc) + timedelta(minutes=5))
        return True
    async def release(lease):
        released.append(lease)
    monkeypatch.setattr('engine.jobs.manager.resource_manager.acquire_gpu_slot', acquire)
    monkeypatch.setattr('engine.jobs.manager.resource_manager.release_gpu_slot', release)
    async def operation(token, progress):
        executed.append(True)
        return {}
    manager.enqueue_async(job.job_id, operation)
    task = manager._active_tasks[job.job_id]
    await task
    assert executed == []
    assert len(released) == 1
    assert manager.get_job(job.job_id)['worker_lease_id'] == 'replacement:new'


@pytest.mark.asyncio
async def test_rehydrated_operation_does_not_enter_when_lease_lost(manager):
    job = manager.create_job('recovery-boundaries', 'SIDE_EFFECT_FENCE')
    set_running(job.job_id, 'replacement:new', datetime.now(timezone.utc) + timedelta(minutes=5))
    calls = []
    def operation(db, progress, is_cancelled):
        calls.append('side effect')
        return {}
    class Token:
        is_cancelled = False
        lease_id = 'expired:old'
        job_id = job.job_id
    with pytest.raises(RuntimeError, match='lease'):
        await _runner(job.project_id, operation)(Token(), lambda *args: None)
    assert calls == []


@pytest.mark.asyncio
async def test_stale_worker_cannot_publish_success_after_replacement(manager):
    job = manager.create_job('recovery-boundaries', 'TERMINAL_FENCE')
    entered = asyncio.Event()
    release = asyncio.Event()

    async def operation(token, progress):
        entered.set()
        await release.wait()
        return {'stale': True}

    manager.enqueue_async(job.job_id, operation)
    task = manager._active_tasks[job.job_id]
    await entered.wait()
    set_running(job.job_id, 'replacement:new', datetime.now(timezone.utc) + timedelta(minutes=5))
    release.set()
    await task
    state = manager.get_job(job.job_id)
    assert state['status'] == JobStatus.RUNNING.value
    assert state['output'] == {}
    assert state['worker_lease_id'] == 'replacement:new'


@pytest.mark.asyncio
async def test_cancelled_token_cannot_publish_success(manager):
    job = manager.create_job('recovery-boundaries', 'CANCEL_FENCE')

    async def operation(token, progress):
        token.cancel()
        return {'must_not_publish': True}

    manager.enqueue_async(job.job_id, operation)
    await manager._active_tasks[job.job_id]
    state = manager.get_job(job.job_id)
    assert state['status'] == JobStatus.CANCELLED.value
    assert state['output'] == {}


def test_startup_reclaims_expired_lease_and_orphan_queue(manager, monkeypatch):
    expired = manager.create_job('recovery-boundaries', 'RECOVERY_A', max_retries=2)
    queued = manager.create_job('recovery-boundaries', 'RECOVERY_B')
    set_running(expired.job_id, 'dead:worker', datetime.now(timezone.utc) - timedelta(minutes=5))
    seen = []
    monkeypatch.setattr(manager, '_resolve_operation_handler', lambda job: lambda *args: None)
    monkeypatch.setattr(manager, 'enqueue_async', lambda job_id, handler: seen.append(job_id))
    assert manager.recover_interrupted_jobs() == 2
    assert set(seen) == {expired.job_id, queued.job_id}
    assert manager.get_job(expired.job_id)['retry_count'] == 1
    assert manager.get_job(expired.job_id)['status'] == JobStatus.QUEUED.value


def test_startup_reclaims_expired_local_active_worker(manager, monkeypatch):
    job = manager.create_job('recovery-boundaries', 'EXPIRED_LOCAL_STARTUP', max_retries=2)
    token = type('Token', (), {'cancel': lambda self: setattr(self, 'cancelled', True)})()
    manager._active_tokens[job.job_id] = token
    set_running(job.job_id, manager.worker_id + ':old', datetime.now(timezone.utc) - timedelta(minutes=1))
    seen = []
    monkeypatch.setattr(manager, '_resolve_operation_handler', lambda _: lambda *args: None)
    monkeypatch.setattr(manager, 'enqueue_async', lambda job_id, handler: seen.append(job_id))
    assert manager.recover_interrupted_jobs() == 1
    assert vars(token).get('cancelled') is True
    assert seen == [job.job_id]


def test_periodic_recovery_reclaims_expired_local_active_worker(manager, monkeypatch):
    job = manager.create_job('recovery-boundaries', 'EXPIRED_LOCAL', max_retries=2)
    old_token = type('Token', (), {'cancel': lambda self: setattr(self, 'cancelled', True)})()
    manager._active_tokens[job.job_id] = old_token
    set_running(job.job_id, manager.worker_id + ':old', datetime.now(timezone.utc) - timedelta(minutes=1))
    seen = []
    monkeypatch.setattr(manager, '_resolve_operation_handler', lambda _: lambda *args: None)
    monkeypatch.setattr(manager, 'enqueue_async', lambda job_id, handler: seen.append(job_id))
    assert manager.recover_expired_leases() == 1
    assert old_token.cancelled
    assert manager.get_job(job.job_id)['status'] == JobStatus.QUEUED.value
    assert seen == [job.job_id]


def test_expired_worker_cannot_renew_lease_from_progress(manager):
    job = manager.create_job('recovery-boundaries', 'EXPIRED_PROGRESS')
    expired_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    set_running(job.job_id, 'worker:old', expired_at)
    manager.update_job_progress(job.job_id, 0.9, 'stale progress', lease_id='worker:old')
    state = manager.get_job(job.job_id)
    assert state['progress'] == 0.0
    assert state['message'] != 'stale progress'
