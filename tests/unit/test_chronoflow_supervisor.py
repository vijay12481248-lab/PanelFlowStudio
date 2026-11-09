import pytest
import asyncio
from unittest.mock import patch, MagicMock
from pathlib import Path
from engine.chronoflow.supervisor import JobSupervisor
from engine.chronoflow.reviewer import analyze_video_chunk


def test_supervisor_singleton_and_job_registration():
    supervisor = JobSupervisor()
    assert supervisor is JobSupervisor()

    job_id = "test_job_123"
    job_data = {
        "id": job_id,
        "prompt": "Test cinematic prompt",
        "status": "starting",
        "created_at": 1000.0,
    }

    with patch.object(supervisor, "_save_jobs_to_disk"):
        supervisor.register_new_job(job_id, job_data)
        try:
            retrieved = supervisor.get_job(job_id)
            assert retrieved is not None
            assert retrieved["prompt"] == "Test cinematic prompt"

            supervisor.update_job(job_id, status="completed", status_msg="Done")
            assert supervisor.get_job(job_id)["status"] == "completed"

            # Test cancel
            supervisor.cancel_job(job_id)
            assert supervisor.get_job(job_id)["status"] == "cancelled"
        finally:
            supervisor.active_jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_supervisor_unified_sync_state():
    mock_pipeline = MagicMock()
    async def fake_status():
        return {
            "connected": True,
            "gpu": "RTX 5060 Ti",
            "vram_free_gb": 12.5,
            "vram_total_gb": 16.0,
            "queue": {"busy": False, "pending_count": 0},
        }
    mock_pipeline.check_comfy_status = fake_status

    supervisor = JobSupervisor(pipeline=mock_pipeline)
    sync_state = await supervisor.get_unified_sync_state(client_version=0)

    assert "version" in sync_state
    assert sync_state["comfy"]["connected"] is True
    assert "5060" in sync_state["comfy"]["gpu"] or sync_state["comfy"]["gpu"] == "RTX 5060 Ti"
    assert "jobs_summary" in sync_state


async def _watchdog_verdict(comfy_status, idle_for=0.0):
    """Run one watchdog pass over a job that has been rendering for 2 minutes with no update, while ComfyUI has been idle for `idle_for`
    seconds; return (status, was_task_cancelled)."""
    import time

    sup = JobSupervisor()
    sup._save_jobs_to_disk = lambda: None
    sup._idle_since = time.time() - idle_for if idle_for else None
    jid = "watchdog_test_job"

    async def fake_status():
        return comfy_status

    sup.pipeline = MagicMock(check_comfy_status=fake_status)
    sup.register_new_job(jid, {"id": jid, "status": "starting", "chunks": [], "created_at": time.time() - 120, "last_updated_at": time.time() - 120})
    task = asyncio.create_task(asyncio.sleep(60))
    sup._tasks[jid] = task
    try:
        await sup.reconcile_state()
        await asyncio.sleep(0)
        return sup.get_job(jid)["status"], task.cancelled() or task.cancelling() > 0
    finally:
        task.cancel()
        sup._tasks.pop(jid, None)
        sup.active_jobs.pop(jid, None)


@pytest.mark.asyncio
async def test_watchdog_does_not_kill_a_job_when_comfyui_simply_did_not_answer():
    # a heavy render starves ComfyUI's web server: the queue request times out. That is "unknown", not "idle".
    unanswered = {"connected": True, "queue": {"busy": False, "reachable": False, "pending_count": 0}}
    assert await _watchdog_verdict(unanswered) == ("starting", False)
    assert await _watchdog_verdict({"connected": False, "queue": {"busy": False}}) == ("starting", False)


@pytest.mark.asyncio
async def test_watchdog_still_stops_a_job_when_comfyui_really_says_it_is_idle():
    idle = {"connected": True, "queue": {"busy": False, "reachable": True, "pending_count": 0}}
    status, cancelled = await _watchdog_verdict(idle, idle_for=60.0)  # idle for a minute while the job waits for output: hung
    assert status == "failed" and cancelled


@pytest.mark.asyncio
async def test_watchdog_ignores_the_few_idle_seconds_between_two_shots():
    # ComfyUI finished shot 1 and the task has not yet registered it / submitted shot 2. The job record is stale (nothing updates it during a
    # render), but ComfyUI has only just become idle: this killed a healthy two-shot job at the end of its first shot.
    idle = {"connected": True, "queue": {"busy": False, "reachable": True, "pending_count": 0}}
    assert await _watchdog_verdict(idle, idle_for=0.0) == ("starting", False)
    assert await _watchdog_verdict(idle, idle_for=8.0) == ("starting", False)


@pytest.mark.asyncio
async def test_watchdog_leaves_a_job_alone_while_comfyui_reports_it_is_busy():
    busy = {"connected": True, "queue": {"busy": True, "reachable": True, "pending_count": 0}}
    assert await _watchdog_verdict(busy) == ("starting", False)


@pytest.mark.asyncio
async def test_watchdog_sees_a_shot_regeneration_task_registered_under_a_regen_name():
    # /regenerate_chunk registers its task as "<job>_regen_<n>", not "<job>": the watchdog used to conclude "no task running" and flip the
    # regenerating job to completed seconds after it started, while ComfyUI was still rendering.
    import time

    sup = JobSupervisor()

    async def fake_status():
        return {"connected": True, "queue": {"busy": True, "reachable": True, "pending_count": 0}}

    sup.pipeline = MagicMock(check_comfy_status=fake_status)
    sup._save_jobs_to_disk = lambda: None    # register_new_job would otherwise write this fake job into the real vault/jobs.json
    jid = "regen_job"
    sup.register_new_job(jid, {"id": jid, "status": "regenerating", "chunks": ["a.mp4"], "created_at": time.time(), "last_updated_at": time.time()})
    task = asyncio.create_task(asyncio.sleep(60))
    sup._tasks[f"{jid}_regen_3"] = task
    try:
        await sup.reconcile_state()
        assert sup.get_job(jid)["status"] == "regenerating"
        task.cancel()
        await asyncio.sleep(0)
        sup._tasks.pop(f"{jid}_regen_3", None)
        await sup.reconcile_state()              # the task is gone: now it really is finished
        assert sup.get_job(jid)["status"] == "completed"
    finally:
        task.cancel()
        sup._tasks.pop(f"{jid}_regen_3", None)
        sup.active_jobs.pop(jid, None)


def test_reviewer_nonexistent_file():
    critique = analyze_video_chunk("nonexistent.mp4", "Dark apocalyptic streets")
    assert critique["verdict"] == "NOT INSPECTED" and critique["measured"] is False
    assert critique["overall_score"] is None and critique["grade"] is None  # no invented score for a clip that was not looked at


def test_reviewer_measures_real_frames_and_invents_nothing(tmp_path):
    import cv2
    import numpy as np

    rng = np.random.default_rng(1)
    base = cv2.GaussianBlur(rng.integers(0, 255, (432, 768, 3), dtype=np.uint8), (0, 0), 2)
    vw = cv2.VideoWriter(str(tmp_path / "still.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 24, (384, 216))
    for _ in range(40):
        vw.write(base[108:324, 192:576])
    vw.release()
    critique = analyze_video_chunk(str(tmp_path / "still.mp4"), "Cyberpunk neon alley with heavy rain", shot_index=1, total_shots=3)
    assert critique["measured"] is True and critique["overall_score"] is None and critique["grade"] is None
    assert "APPROVED" not in critique["verdict"]  # a still picture with no audio stream cannot be approved
    assert any(f["axis"] == "audio" for f in critique["flags"]) and "neon" not in " ".join(critique["observations"]).lower()  # the prompt no longer picks the praise
    assert critique["metrics"]["has_audio"] is False and "identity" in critique["not_checked"]
