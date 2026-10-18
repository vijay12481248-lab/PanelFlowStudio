import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
import soundfile as sf
import numpy as np

BASE_URL = "http://127.0.0.1:8001"

payload = {
    "prompt": "Instrumental cinematic dark-fantasy underscore with low strings and subtle crystal resonance, mysterious and atmospheric, no vocals",
    "lyrics": "[Instrumental]",
    "audio_duration": 10.0,
    "bpm": 85,
    "key_scale": "D Minor",
    "time_signature": "4/4",
    "audio_format": "wav",
    "batch_size": 1,
    "thinking": False,
    "inference_steps": 8,
    "guidance_scale": 7.0,
    "seed": 42100,
    "use_random_seed": False,
}

print("[1] Submitting task to /release_task...")
req_data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    f"{BASE_URL}/release_task",
    data=req_data,
    headers={"Content-Type": "application/json"}
)

with urllib.request.urlopen(req, timeout=15) as resp:
    res = json.loads(resp.read().decode("utf-8"))

print("Response:", res)
task_id = res.get("data", {}).get("task_id")
print("Task ID:", task_id)

print("[2] Polling /query_result...")
for i in range(60):
    time.sleep(2.0)
    query_body = json.dumps({"task_id_list": [task_id]}).encode("utf-8")
    q_req = urllib.request.Request(
        f"{BASE_URL}/query_result",
        data=query_body,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(q_req, timeout=10) as q_resp:
        q_data = json.loads(q_resp.read().decode("utf-8"))
    
    rows = q_data.get("data", [])
    if not rows:
        print(f"Poll {i}: no rows")
        continue
    row = rows[0]
    status = row.get("status")
    print(f"Poll {i}: status={status}, progress={row.get('progress_text', '')}")
    if status == 1:
        result_raw = row.get("result")
        if isinstance(result_raw, str):
            result_raw = json.loads(result_raw)
        track_info = result_raw[0] if isinstance(result_raw, list) else result_raw
        audio_subpath = track_info.get("file", "")
        dl_url = f"{BASE_URL}{audio_subpath}" if audio_subpath.startswith("/") else f"{BASE_URL}/{audio_subpath}"
        print("Success! Download URL:", dl_url)
        out_path = Path("scratch/test_ace_output.wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(dl_url, timeout=30) as dl_resp:
            out_path.write_bytes(dl_resp.read())
        
        info = sf.info(str(out_path))
        data, sr = sf.read(str(out_path))
        peak = np.max(np.abs(data))
        print(f"Downloaded WAV: {out_path.stat().st_size} bytes, duration={info.duration:.2f}s, sr={info.samplerate}, peak={peak:.4f}")
        break
    elif status == 2:
        print("Failed! Status 2")
        break
