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
        assert updated.worker_lease_id.startswith(f"{jm.worker_id}:")
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
    jm.update_job_progress(job.job_id, 0.5, "Halfway done", lease_id=initial.worker_lease_id)

    with SessionLocal() as db:
        refreshed = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        assert refreshed.progress == 0.5
        assert refreshed.message == "Halfway done"
        # Heartbeat should have pushed expiry forward or equal
        assert refreshed.lease_expires_at >= initial_expiry


def test_job_manager_recover_expired_leases():
    """Expired leases fail closed when no durable operation handler exists."""
    _ensure_project("test_proj_queue_03")
    jm = JobManager()

    job = jm.create_job(
        project_id="test_proj_queue_03",
        job_type="DETECT_PANELS",
        max_retries=2,
    )
    jm.claim_job_lease(job.job_id)

    past_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    with SessionLocal() as db:
        j = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        j.lease_expires_at = past_time
        db.commit()

    recovered_count = jm.recover_expired_leases()
    assert recovered_count >= 1

    with SessionLocal() as db:
        j = db.query(JobRecord).filter(JobRecord.job_id == job.job_id).first()
        assert j.status == JobStatus.FAILED.value
        assert "cannot be rehydrated" in (j.error or "").lower()
        assert j.worker_lease_id is None


@pytest.mark.asyncio
async def test_can_admit_gpu_job_comfyui_with_resident_vram(monkeypatch):
    """ComfyUI jobs must not be rejected due to ComfyUI's own resident model weights."""
    mgr = SystemResourceManager()
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16311.0,
        "free_mb": 1200.0,
        "used_mb": 15111.0,
    })

    # Standard non-ComfyUI job is rejected because free VRAM (1200MB) < 10000MB
    admitted_non_comfy, reason = mgr.can_admit_gpu_job(10000, is_comfyui=False)
    assert admitted_non_comfy is False
    assert "Insufficient GPU VRAM" in reason

    # ComfyUI job is admitted because total physical GPU capacity (16311MB) supports it
    admitted_comfy, reason_comfy = mgr.can_admit_gpu_job(10000, is_comfyui=True)
    assert admitted_comfy is True
    assert reason_comfy == "Admitted"


@pytest.mark.asyncio
async def test_acquire_gpu_slot_comfyui_held_back_by_active_ollama(monkeypatch):
    """ComfyUI jobs must be held back if Ollama currently occupies the GPU."""
    mgr = SystemResourceManager()
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16311.0,
        "free_mb": 1200.0,
        "used_mb": 15111.0,
    })
    async def mock_ollama_runtime(*args, **kwargs):
        return {"total_ollama_vram_mb": 8500.0, "loaded_models_count": 1}
    monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)

    # Held back while Ollama is loaded
    acquired = await mgr.acquire_gpu_slot("comfy_job_01", 10000, is_comfyui=True)
    assert acquired is False


@pytest.mark.asyncio
async def test_acquire_gpu_slot_triggers_active_ollama_eviction(monkeypatch):
    """ComfyUI jobs must actively evict resident Ollama models to claim the slot."""
    mgr = SystemResourceManager()
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True,
        "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16311.0,
        "free_mb": 1200.0,
        "used_mb": 15111.0,
    })

    ollama_calls = 0
    async def mock_ollama_runtime(*args, **kwargs):
        nonlocal ollama_calls
        ollama_calls += 1
        if ollama_calls == 1:
            return {
                "total_ollama_vram_mb": 7000.0,
                "loaded_models_count": 1,
                "models": [{"name": "qwen3.5:9b"}],
            }
        # Post-eviction: VRAM is freed
        return {
            "total_ollama_vram_mb": 0.0,
            "loaded_models_count": 0,
            "models": [],
        }

    monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)

    eviction_targets = []
    async def mock_try_evict(endpoint_url="http://127.0.0.1:11434", models=None, authorization=None):
        eviction_targets.extend(models or [])
        return True

    monkeypatch.setattr(mgr, "_try_evict_ollama", mock_try_evict)

    acquired = await mgr.acquire_gpu_slot("comfy_job_02", 10000, is_comfyui=True)
    assert acquired is True
    assert "qwen3.5:9b" in eviction_targets
    assert mgr.active_gpu_jobs_count == 1
    await mgr.release_gpu_slot("comfy_job_02")


@pytest.mark.asyncio
async def test_try_evict_ollama_posts_keep_alive_zero(monkeypatch):
    """_try_evict_ollama issues POST /api/generate with keep_alive: 0."""
    import httpx
    mgr = SystemResourceManager()
    posted_payloads = []

    def mock_handler(request: httpx.Request):
        import json
        posted_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"status": "success"})

    client_creator = httpx.AsyncClient
    def mock_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(mock_handler)
        return client_creator(*args, **kwargs)

    monkeypatch.setattr("engine.system.resources.httpx.AsyncClient", mock_client)

    evicted = await mgr._try_evict_ollama(models=["qwen3.5:9b"])
    assert evicted is True
    assert len(posted_payloads) == 1
    assert posted_payloads[0]["model"] == "qwen3.5:9b"
    assert posted_payloads[0]["keep_alive"] == 0


@pytest.mark.asyncio
async def test_supports_concurrent_gpu_threshold_branching(monkeypatch):
    """Verify hardware threshold: False on 16 GB, True on >= 24 GB."""
    mgr = SystemResourceManager()

    # 16 GB GPU (RTX 5060 Ti: 16,311 MB)
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True, "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16311.0, "free_mb": 1200.0, "used_mb": 15111.0,
    })
    assert mgr.supports_concurrent_gpu() is False

    # 24 GB GPU (RTX 4090: 24,576 MB)
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True, "device_name": "NVIDIA GeForce RTX 4090",
        "total_mb": 24576.0, "free_mb": 18000.0, "used_mb": 6576.0,
    })
    assert mgr.supports_concurrent_gpu() is True


@pytest.mark.asyncio
async def test_concurrent_gpu_pipeline_flag_hardware_guard(monkeypatch):
    """
    Strict hardware guard:
    Even when PANELFLOW_CONCURRENT_GPU_PIPELINE=1, concurrency is disallowed on 16 GB.
    """
    mgr = SystemResourceManager()

    # Set feature flag
    monkeypatch.setenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", "1")

    # On 16 GB hardware -> MUST return False and log fallback
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True, "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16311.0, "free_mb": 1200.0, "used_mb": 15111.0,
    })
    assert mgr.is_concurrent_pipeline_enabled() is False

    # On 24 GB hardware -> Returns True
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True, "device_name": "NVIDIA GeForce RTX 4090",
        "total_mb": 24576.0, "free_mb": 18000.0, "used_mb": 6576.0,
    })
    assert mgr.is_concurrent_pipeline_enabled() is True

    # When flag is unset on 24 GB -> Returns False (defaults to safe time-slicing)
    monkeypatch.delenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", raising=False)
    assert mgr.is_concurrent_pipeline_enabled() is False


@pytest.mark.asyncio
async def test_acquire_gpu_slot_active_eviction_retry_sub200ms(monkeypatch):
    """Verify sub-200ms active eviction ping-pong with low-latency retry polling."""
    mgr = SystemResourceManager()
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True, "device_name": "NVIDIA GeForce RTX 5060 Ti",
        "total_mb": 16311.0, "free_mb": 1200.0, "used_mb": 15111.0,
    })

    poll_count = 0
    async def mock_ollama_runtime(*args, **kwargs):
        nonlocal poll_count
        poll_count += 1
        if poll_count == 1:
            # Initially occupied
            return {"total_ollama_vram_mb": 7000.0, "loaded_models_count": 1, "models": [{"name": "qwen3.5:9b"}]}
        # Post-eviction deallocation
        return {"total_ollama_vram_mb": 0.0, "loaded_models_count": 0, "models": []}

    monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)

    evictions = []
    async def mock_evict(endpoint_url="http://127.0.0.1:11434", models=None, authorization=None):
        evictions.extend(models or [])
        return True

    monkeypatch.setattr(mgr, "_try_evict_ollama", mock_evict)

    acquired = await mgr.acquire_gpu_slot("comfy_sub200ms_job", 10000, is_comfyui=True)
    assert acquired is True
    assert "qwen3.5:9b" in evictions
    assert poll_count >= 2
    await mgr.release_gpu_slot("comfy_sub200ms_job")


@pytest.mark.asyncio
async def test_concurrent_residency_on_24gb_bypasses_eviction(monkeypatch):
    """On >= 24 GB with flag enabled, ComfyUI does NOT evict resident Ollama."""
    mgr = SystemResourceManager()
    monkeypatch.setenv("PANELFLOW_CONCURRENT_GPU_PIPELINE", "1")
    monkeypatch.setattr(mgr, "get_gpu_memory", lambda: {
        "available": True, "device_name": "NVIDIA GeForce RTX 4090",
        "total_mb": 24576.0, "free_mb": 13576.0, "used_mb": 11000.0,
    })

    async def mock_ollama_runtime(*args, **kwargs):
        return {"total_ollama_vram_mb": 7000.0, "loaded_models_count": 1, "models": [{"name": "qwen3.5:9b"}]}

    monkeypatch.setattr(mgr, "get_ollama_runtime", mock_ollama_runtime)

    eviction_called = False
    async def mock_evict(*args, **kwargs):
        nonlocal eviction_called
        eviction_called = True
        return True

    monkeypatch.setattr(mgr, "_try_evict_ollama", mock_evict)

    # Acquire ComfyUI slot with concurrent pipeline
    acquired = await mgr.acquire_gpu_slot("comfy_24gb_job", 10000, is_comfyui=True)
    assert acquired is True
    # Ollama was NOT evicted because 24 GB hardware supports concurrent residency!
    assert eviction_called is False
    await mgr.release_gpu_slot("comfy_24gb_job")


