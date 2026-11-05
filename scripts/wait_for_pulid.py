"""Wait for prompt and save output image."""
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from engine.comfyui import ComfyUIClient

client = ComfyUIClient()
pid = "6b5873a7-7147-4d72-959e-1f73be391d82"
if len(sys.argv) > 1:
    pid = sys.argv[1]

print(f"Waiting for prompt {pid}...")
t0 = time.time()
while time.time() - t0 < 300:
    hist = client.history(pid)
    if hist and pid in hist:
        imgs = hist[pid]["outputs"].get("7", {}).get("images", [])
        if imgs:
            i = imgs[0]
            data = client.download_output(i["filename"], i["subfolder"], i["type"])
            out_file = Path("output/Original_Stories/mahabharata_kurukshetra/panels/arjuna_pulid_test.png")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_bytes(data)
            print(f"[SUCCESS] PuLID-FLUX image saved: {out_file} ({len(data)/(1024*1024):.2f} MB)")
            break
        else:
            print("Prompt finished but no output images found in node 7:", hist[pid])
            break
    time.sleep(3)
