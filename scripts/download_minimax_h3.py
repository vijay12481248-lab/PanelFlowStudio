"""Download MiniMax Fast H3 models into ComfyUI with resumption and progress tracking.

Exact model files approved by owner:
- diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors (19.53 GB)
- text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors (14.61 GB)
- loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors (1.82 GB)
- vae/minimax_h3_video_vae_int8_convrot.safetensors (2.62 GB)
- vae/minimax_h3_audio_vae_fp32.safetensors (0.56 GB)

Total download size: ~39.14 GB
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

DEFAULT_COMFY_ROOT = Path(r"E:\VIJAY SEKAR\ComfyUI")
HF_BASE_URL = "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main"

MODELS = [
    {
        "subfolder": "loras",
        "filename": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        "size_bytes": 1956193000,
        "description": "Fast H3 Turbo LoRA (8-step)",
    },
    {
        "subfolder": "vae",
        "filename": "minimax_h3_audio_vae_fp32.safetensors",
        "size_bytes": 605254808,
        "description": "MiniMax H3 Audio VAE",
    },
    {
        "subfolder": "vae",
        "filename": "minimax_h3_video_vae_int8_convrot.safetensors",
        "size_bytes": 2811065184,
        "description": "MiniMax H3 Video VAE (INT8 ConvRot)",
    },
    {
        "subfolder": "text_encoders",
        "filename": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "size_bytes": 15687142551,
        "description": "Qwen3-VL 32B Text/Vision Encoder (NVFP4 AWQ)",
    },
    {
        "subfolder": "diffusion_models",
        "filename": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "size_bytes": 20970379616,
        "description": "MiniMax H3 FL2VA DiT Diffusion Model (Pruned INT8 ConvRot)",
    },
]


def download_file(url: str, dest_path: Path, expected_bytes: int, desc: str) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    existing_bytes = 0
    if dest_path.exists():
        size = dest_path.stat().st_size
        if expected_bytes and size >= expected_bytes - 1024:
            print(f"[OK] {desc} already exists: {dest_path.name} ({size / (1024*1024*1024):.2f} GB)")
            return
        if not part_path.exists():
            dest_path.rename(part_path)
            existing_bytes = part_path.stat().st_size

    if part_path.exists():
        existing_bytes = part_path.stat().st_size

    headers = {"User-Agent": "PanelFlow-Studio/1.0"}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"
        print(f"\n[RESUME] {desc} from {existing_bytes / (1024*1024):.1f} MB...")
    else:
        print(f"\n[START] Downloading {desc} ({expected_bytes / (1024*1024*1024):.2f} GB)...")
        print(f"  URL:  {url}")
        print(f"  Dest: {dest_path}")

    req = urllib.request.Request(url, headers=headers)
    t0 = time.time()
    last_print = 0

    mode = "ab" if existing_bytes > 0 else "wb"
    with urllib.request.urlopen(req, timeout=30) as resp, open(part_path, mode) as out_f:
        downloaded = existing_bytes
        total = expected_bytes or int(resp.headers.get("Content-Length", 0)) + existing_bytes
        chunk_size = 1024 * 1024  # 1 MB chunks

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_f.write(chunk)
            downloaded += len(chunk)
            now = time.time()
            if now - last_print >= 2.0 or downloaded >= total:
                last_print = now
                elapsed = max(0.1, now - t0)
                speed_mb = (downloaded - existing_bytes) / (1024 * 1024) / elapsed
                pct = (downloaded / total * 100) if total else 0.0
                gb_done = downloaded / (1024 * 1024 * 1024)
                gb_tot = total / (1024 * 1024 * 1024)
                sys.stdout.write(f"\r  [{pct:5.1f}%] {gb_done:.2f} / {gb_tot:.2f} GB @ {speed_mb:.2f} MB/s ")
                sys.stdout.flush()

    sys.stdout.write("\n")
    part_path.rename(dest_path)
    final_size = dest_path.stat().st_size
    print(f"[COMPLETE] {desc}: {dest_path.name} ({final_size / (1024*1024*1024):.2f} GB)")


def main():
    parser = argparse.ArgumentParser(description="Download MiniMax Fast H3 models for ComfyUI")
    parser.add_argument("--comfy-dir", type=Path, default=DEFAULT_COMFY_ROOT, help="ComfyUI installation root")
    parser.add_argument("--file", type=str, default="all", help="Specific model subfolder/filename or 'all'")
    args = parser.parse_args()

    comfy_dir = args.comfy_dir
    models_dir = comfy_dir / "models"
    print("==================================================================")
    print(" PanelFlow Studio - MiniMax Fast H3 Model Downloader")
    print(f" Target ComfyUI: {comfy_dir}")
    print(f" Models Dir:     {models_dir}")
    print("==================================================================")

    for item in MODELS:
        sub = item["subfolder"]
        fn = item["filename"]
        if args.file != "all" and args.file not in fn:
            continue
        url = f"{HF_BASE_URL}/{sub}/{fn}"
        dest = models_dir / sub / fn
        try:
            download_file(url, dest, item["size_bytes"], item["description"])
        except Exception as exc:
            print(f"[ERROR] Failed downloading {fn}: {exc}")
            print("  You can re-run this script anytime to resume!")


if __name__ == "__main__":
    main()
