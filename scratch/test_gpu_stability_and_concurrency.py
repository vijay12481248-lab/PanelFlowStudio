import os
import sys
import json
import time
import subprocess
from pathlib import Path
import urllib.request
import urllib.error

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

PROJECT_ID = "68711176-90f5-4a68-8520-78d6e183bf65"
API_URL = "http://127.0.0.1:8765"

def get_vram_usage():
    try:
        out = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits"
        ]).decode("utf-8").strip()
        parts = [float(p.strip()) for p in out.split(",")]
        return {
            "total_mb": parts[0],
            "used_mb": parts[1],
            "free_mb": parts[2],
            "util_pct": parts[3],
        }
    except Exception as e:
        return {"error": str(e)}

def test_gpu_stability():
    print("=================================================================")
    print(" CHAPTER 9.1: GPU RESOURCE STABILITY & CONCURRENCY BENCHMARK")
    print("=================================================================")

    # 1. Baseline GPU VRAM
    vram_before = get_vram_usage()
    print(f"Baseline VRAM: Used: {vram_before['used_mb']} MB / {vram_before['total_mb']} MB ({vram_before['used_mb']/vram_before['total_mb']*100:.1f}%) | Free: {vram_before['free_mb']} MB")

    # 2. Check Music Health endpoint
    req = urllib.request.urlopen(f"{API_URL}/api/music/health", timeout=5)
    health = json.loads(req.read().decode("utf-8"))
    print(f"Engine Music Health: {health['service']} | Model: {health['health']['loaded_model']}")

    # 3. Test Short Synthesis to Measure Generation Latency & VRAM Stability
    print("\nExecuting live 5.0s synthesis test to measure latency and VRAM footprint...")
    payload = {
        "cue_id": "cue_01_opening_mystery",
        "prompt": "Soft crystal resonance ambient drone, dark fantasy D Minor, gentle strings.",
        "audio_duration": 5.0,
        "bpm": 78,
        "key_scale": "D Minor",
        "time_signature": "4/4",
        "use_random_seed": True,
        "inference_steps": 8,
        "guidance_scale": 7.0,
    }

    t0 = time.time()
    req_post = urllib.request.Request(
        f"{API_URL}/api/projects/{PROJECT_ID}/music/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    resp = urllib.request.urlopen(req_post, timeout=60)
    take_data = json.loads(resp.read().decode("utf-8"))
    gen_time = time.time() - t0

    vram_after_gen = get_vram_usage()
    print(f"Synthesis Complete in {gen_time:.2f}s!")
    print(f"Generated Take ID: {take_data.get('take_id')}")
    print(f"Take Duration: {take_data.get('duration_sec')}s | Peak: {take_data.get('measured_peak_dbfs')} dBFS | RMS: {take_data.get('measured_rms_dbfs')} dBFS")
    print(f"Post-Gen VRAM: Used: {vram_after_gen['used_mb']} MB | Free: {vram_after_gen['free_mb']} MB")

    # 4. Test Concurrency Protection (GPU Slot Lock)
    # When resource_manager has locked the slot, concurrent requests should be safely serialized
    print("\nTesting GPU slot admission lock...")
    from engine.system.resources import SystemResourceManager
    import asyncio
    resource_manager = SystemResourceManager()

    async def test_slot_lock():
        job_1 = "test_slot_job_1"
        job_2 = "test_slot_job_2"
        # Acquire slot 1
        acq_1 = await resource_manager.acquire_gpu_slot(job_1, required_vram_mb=0.0)
        print(f"  Job 1 Slot Acquired: {acq_1}")
        # Try to acquire slot 2 while job 1 is running
        acq_2 = await resource_manager.acquire_gpu_slot(job_2, required_vram_mb=0.0)
        print(f"  Job 2 Slot Acquired (Should be False): {acq_2}")
        # Release job 1
        await resource_manager.release_gpu_slot(job_1)
        print("  Job 1 Slot Released")
        # Try job 2 again
        acq_2_retry = await resource_manager.acquire_gpu_slot(job_2, required_vram_mb=0.0)
        print(f"  Job 2 Slot Acquired after Job 1 Release: {acq_2_retry}")
        await resource_manager.release_gpu_slot(job_2)

        assert acq_1 is True, "Job 1 should acquire lock"
        assert acq_2 is False, "Job 2 must be blocked to prevent concurrent OOM"
        assert acq_2_retry is True, "Job 2 should succeed once Job 1 releases lock"

    asyncio.run(test_slot_lock())

    # 5. Final VRAM Recovery Check
    vram_final = get_vram_usage()
    vram_diff_mb = abs(vram_final['used_mb'] - vram_before['used_mb'])
    print(f"\nFinal VRAM: Used: {vram_final['used_mb']} MB | VRAM Delta from Baseline: {vram_diff_mb:.1f} MB")
    assert vram_diff_mb < 200.0, "VRAM memory leak detected!"

    print("\n=================================================================")
    print(" GPU STABILITY, LATENCY & CONCURRENCY LOCK TESTS PASSED!")
    print("=================================================================")

if __name__ == "__main__":
    test_gpu_stability()
