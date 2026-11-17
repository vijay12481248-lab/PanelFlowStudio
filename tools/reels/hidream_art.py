"""Pictures for a reel from HiDream-I1 Fast (MIT transformer) on a throwaway ComfyUI on :8189 - NOT an ArtEngine workflow (see AGENTS.md: klein is the art workflow;
this is the owner's explicit choice for the ghost reel, 2026-11-16). Reads the spec's own `style`, writes panels/sN.png like make_reel.stage_art, skips existing files.

  ComfyUI for HiDream must run WITHOUT --disable-dynamic-vram, alone on the GPU (memory: hidream-works-dynamic-vram):
      cd E:\\VIJAY SEKAR\\ComfyUI && venv\\Scripts\\python.exe main.py --listen 127.0.0.1 --port 8189 --disable-auto-launch
  python tools/reels/hidream_art.py r13 [--seed-bump N] [--only 3,5]        (REEL_OUT_DIR as for make_reel.py)
"""
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_reel as mr  # noqa: E402

BASE = "http://127.0.0.1:8189"


def call(path, data=None):
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=30).read()


def graph(prompt, w, h, seed):
    return {
        "81": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "82": {"class_type": "QuadrupleCLIPLoader", "inputs": {"clip_name1": "clip_l_hidream.safetensors", "clip_name2": "clip_g_hidream.safetensors",
               "clip_name3": "t5xxl_fp8_e4m3fn_scaled.safetensors", "clip_name4": "llama_3.1_8b_instruct_fp8_scaled.safetensors"}},
        "93": {"class_type": "UNETLoader", "inputs": {"unet_name": "hidream_i1_fast_fp8.safetensors", "weight_dtype": "default"}},
        "91": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["93", 0], "shift": 3.0}},
        "85": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["82", 0], "text": prompt}},
        "90": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["82", 0], "text": ""}},
        "84": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "94": {"class_type": "KSampler", "inputs": {"model": ["91", 0], "positive": ["85", 0], "negative": ["90", 0], "latent_image": ["84", 0],
               "seed": seed, "steps": 16, "cfg": 1.0, "sampler_name": "lcm", "scheduler": "normal", "denoise": 1.0}},
        "86": {"class_type": "VAEDecode", "inputs": {"samples": ["94", 0], "vae": ["81", 0]}},
        "88": {"class_type": "SaveImage", "inputs": {"images": ["86", 0], "filename_prefix": "reel_hidream"}},
    }


def draw(prompt, w, h, seed, limit=900):
    t0 = time.time()
    pid = json.loads(call("/prompt", {"prompt": graph(prompt, w, h, seed), "client_id": str(uuid.uuid4())}))["prompt_id"]
    while True:
        time.sleep(3)
        hist = json.loads(call(f"/history/{pid}"))
        if pid in hist:
            break
        if time.time() - t0 > limit:
            call("/interrupt", {})
            sys.exit(f"HiDream took over {limit}s; interrupted")
    e = hist[pid]
    if e["status"]["status_str"] != "success":
        sys.exit("HiDream failed: " + json.dumps(e["status"])[:600])
    img = e["outputs"]["88"]["images"][0]
    return call(f"/view?filename={img['filename']}&subfolder={img['subfolder']}&type={img['type']}")


def main():
    args = sys.argv[1:]
    bump = int(args[args.index("--seed-bump") + 1]) if "--seed-bump" in args else 0
    only = {int(x) for x in args[args.index("--only") + 1].split(",")} if "--only" in args else None
    slugs = [a for a in args if not a.startswith("-") and not a.replace(",", "").isdigit()]
    for r in mr.pick(slugs):
        style = r.get("style")
        if not style:
            sys.exit(f"{r['slug']} has no `style` key: this tool is for reels with their own picture style")
        for i, s in enumerate(r["scenes"], 1):
            out = mr.rdir(r, "panels", f"s{i}.png")
            if mr.have(out) or s.get("reuse") or (only and i not in only):
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.monotonic()
            out.write_bytes(draw(f"{s['img']}. {r['palette']}. {style}", 768, 1344, 1000 + 10 * mr.ridx(r) + i + bump))
            print(f"hidream {r['slug']} s{i}: {time.monotonic() - t0:.0f}s", flush=True)


main()
