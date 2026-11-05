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

    supervisor.register_new_job(job_id, job_data)
    retrieved = supervisor.get_job(job_id)
    assert retrieved is not None
    assert retrieved["prompt"] == "Test cinematic prompt"

    supervisor.update_job(job_id, status="completed", status_msg="Done")
    assert supervisor.get_job(job_id)["status"] == "completed"

    # Test cancel
    supervisor.cancel_job(job_id)
    assert supervisor.get_job(job_id)["status"] == "cancelled"


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


def test_reviewer_nonexistent_file():
    critique = analyze_video_chunk("nonexistent.mp4", "Dark apocalyptic streets")
    assert critique["score"] == 80
    assert critique["grade"] == "B"
    assert critique["verdict"] == "PENDING INSPECTION"


@patch("subprocess.run")
def test_reviewer_valid_probe(mock_run, tmp_path):
    chunk_file = tmp_path / "valid_chunk.mp4"
    chunk_file.write_bytes(b"content")

    probe_json = {
        "streams": [
            {"codec_type": "video", "width": 1344, "height": 768},
            {"codec_type": "audio"},
        ],
        "format": {"duration": "5.17"},
    }

    mock_res = MagicMock()
    mock_res.stdout = str(probe_json).replace("'", '"')
    mock_run.return_value = mock_res

    critique = analyze_video_chunk(str(chunk_file), "Cyberpunk neon alley with heavy rain", shot_index=1, total_shots=3)

    assert critique["overall_score"] >= 90
    assert critique["grade"] in ("A", "A+")
    assert critique["verdict"] == "APPROVED FOR MASTER CUT"
    assert "neon" in " ".join(critique["observations"]).lower() or "lighting" in " ".join(critique["observations"]).lower()
