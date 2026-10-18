import urllib.request
import json
import time

project_id = "741a1c5c-cb8f-44ef-bc2e-f3503fda4da2"
url = f"http://127.0.0.1:8765/api/projects/{project_id}/render/jobs"
payload = json.dumps({
    "profile_name": "standard_1080p",
    "subtitle_enabled": True,
    "bgm_volume_db": -10.0,
    "dialogue_gain_db": 0.0,
    "is_draft": False
}).encode("utf-8")

req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

print("Starting 1080p Production Render with fixed RGB encoder & semantic QA...")
with urllib.request.urlopen(req) as resp:
    job = json.loads(resp.read().decode("utf-8"))

render_id = job["render_id"]
print(f"Render Job ID: {render_id}")

while True:
    time.sleep(2)
    poll_url = f"http://127.0.0.1:8765/api/projects/{project_id}/render/jobs/{render_id}"
    with urllib.request.urlopen(poll_url) as resp:
        status_data = json.loads(resp.read().decode("utf-8"))
    
    st = status_data["status"]
    done = status_data.get("frames_done", 0)
    total = status_data.get("frames_total", 0)
    pct = round((done / max(1, total)) * 100, 1)
    print(f"[{st}] {done}/{total} frames ({pct}%) | Stage: {status_data.get('current_stage')}")
    
    if st in ("COMPLETE", "FAILED", "CANCELLED"):
        print("\nFinal Result:")
        print(f"Status: {st}")
        print(f"Validation: {status_data.get('validation_status')}")
        print(f"Output: {status_data.get('output_path')}")
        if status_data.get("validation_report"):
            print("Validation Report:", json.dumps(status_data["validation_report"], indent=2))
        break
