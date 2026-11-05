#!/usr/bin/env python3
"""
PanelFlow Studio - Automated Model Downloader for ComfyUI
Downloads open-source, commercially usable models:
  1) Qwen 2.5-VL + LongCat-Image (Apache 2.0)
  2) FLUX.1 [schnell] + T5-XXL + CLIP-L (Apache 2.0) + PuLID
Supports auto-resuming, progress display, and direct placement into ComfyUI models folder.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Default ComfyUI root directory on this system
DEFAULT_COMFYUI_DIR = Path(r"E:\VIJAY SEKAR\ComfyUI")

# Model definitions with HuggingFace direct download URLs
MODELS = {
    "qwen": [
        {
            "name": "Qwen 2.5-VL 7B FP8 Text Encoder",
            "filename": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "subfolder": "text_encoders",
            "url": "https://huggingface.co/Comfy-Org/Qwen-Image/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
            "size_gb": "~7.6 GB",
        },
        {
            "name": "LongCat-Image Diffusion Model (BF16)",
            "filename": "longcat_image_bf16_3.safetensors",
            "subfolder": "diffusion_models",
            # Standard Comfy-Org longcat diffusion model
            "url": "https://huggingface.co/Comfy-Org/LongCat-Image/resolve/main/split_files/diffusion_models/longcat_image_bf16.safetensors",
            "size_gb": "~12.5 GB",
        },
        {
            "name": "AE VAE (AutoEncoder)",
            "filename": "ae.safetensors",
            "subfolder": "vae",
            "url": "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors",
            "size_gb": "~335 MB",
        },
    ],
    "flux": [
        {
            "name": "FLUX.1 [schnell] FP8 (Apache 2.0)",
            "filename": "flux1-schnell-fp8.safetensors",
            "subfolder": "diffusion_models",
            "url": "https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors",
            "size_gb": "~11.9 GB",
        },
        {
            "name": "T5-XXL Text Encoder (FP8)",
            "filename": "t5xxl_fp8_e4m3fn.safetensors",
            "subfolder": "text_encoders",
            "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors",
            "size_gb": "~4.9 GB",
        },
        {
            "name": "CLIP-L Text Encoder",
            "filename": "clip_l.safetensors",
            "subfolder": "text_encoders",
            "url": "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors",
            "size_gb": "~246 MB",
        },
        {
            "name": "AE VAE (AutoEncoder)",
            "filename": "ae.safetensors",
            "subfolder": "vae",
            "url": "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors",
            "size_gb": "~335 MB",
        },
        {
            "name": "PuLID for FLUX (Character Consistency)",
            "filename": "pulid_flux_v0.9.1.safetensors",
            "subfolder": "pulid",
            "url": "https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors",
            "size_gb": "~300 MB",
        },
    ],
}


def format_bytes(num_bytes: int) -> str:
    """Format bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def download_file_with_resume(url: str, dest_path: Path, item_name: str) -> bool:
    """Download a file with HTTP Range resume support and progress indication."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    initial_size = temp_path.stat().st_size if temp_path.exists() else 0

    headers = {
        "User-Agent": "PanelFlowStudio/1.0 (Downloader)",
    }
    if initial_size > 0:
        headers["Range"] = f"bytes={initial_size}-"

    req = Request(url, headers=headers)

    try:
        with urlopen(req, timeout=30) as response:
            content_range = response.headers.get("Content-Range")
            total_size = None
            if content_range:
                # Format: bytes start-end/total
                try:
                    total_size = int(content_range.split("/")[-1])
                except (ValueError, IndexError):
                    pass
            elif "Content-Length" in response.headers:
                total_size = int(response.headers["Content-Length"]) + initial_size

            # If server ignores Range request and returns 200 instead of 206
            mode = "ab" if response.status == 206 or (initial_size > 0 and content_range) else "wb"
            if mode == "wb":
                initial_size = 0

            downloaded = initial_size
            start_time = time.time()
            last_print = 0.0

            print(f"\n[+] Downloading: {item_name}")
            print(f"    Target: {dest_path}")
            if total_size:
                print(f"    Total Size: {format_bytes(total_size)} (Resuming from {format_bytes(initial_size)})")

            chunk_size = 1024 * 1024  # 1MB chunks
            with open(temp_path, mode) as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_print > 0.5:
                        elapsed = now - start_time
                        speed = (downloaded - initial_size) / elapsed if elapsed > 0 else 0
                        speed_str = f"{format_bytes(int(speed))}/s"

                        if total_size and total_size > 0:
                            percent = (downloaded / total_size) * 100
                            eta_sec = (total_size - downloaded) / speed if speed > 0 else 0
                            eta_str = f"{int(eta_sec // 60):02d}:{int(eta_sec % 60):02d}"
                            progress_bar = ("=" * int(percent // 4)).ljust(25)
                            sys.stdout.write(
                                f"\r    [{progress_bar}] {percent:5.1f}% | {format_bytes(downloaded)}/{format_bytes(total_size)} | {speed_str} | ETA: {eta_str} "
                            )
                        else:
                            sys.stdout.write(f"\r    Downloaded: {format_bytes(downloaded)} | Speed: {speed_str} ")
                        sys.stdout.flush()
                        last_print = now

            print(f"\n[✓] Completed: {dest_path.name} ({format_bytes(downloaded)})")

        # Atomic rename after successful download
        if temp_path.exists():
            if dest_path.exists():
                dest_path.unlink()
            temp_path.rename(dest_path)
        return True

    except HTTPError as e:
        if e.code == 416:  # Requested Range Not Satisfiable (likely fully downloaded)
            if temp_path.exists() and temp_path.stat().st_size > 0:
                temp_path.rename(dest_path)
                print(f"[✓] File already completely downloaded: {dest_path.name}")
                return True
        print(f"\n[!] HTTP Error downloading {item_name}: {e.code} {e.reason}")
        return False
    except (URLError, TimeoutError) as e:
        print(f"\n[!] Network Error downloading {item_name}: {e}")
        print("    You can re-run this script anytime to resume!")
        return False
    except Exception as e:
        print(f"\n[!] Unexpected Error downloading {item_name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="PanelFlow Studio - ComfyUI Model Downloader")
    parser.add_argument(
        "--comfy-dir",
        type=str,
        default=str(DEFAULT_COMFYUI_DIR),
        help=f"Path to ComfyUI directory (default: {DEFAULT_COMFYUI_DIR})",
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--qwen",
        action="store_true",
        help="Download Qwen 2.5-VL 7B (FP8) + LongCat-Image model set (matches existing registry)",
    )
    group.add_argument(
        "--flux",
        action="store_true",
        help="Download FLUX.1 [schnell] (Apache 2.0) + T5-XXL + PuLID model set",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Download both Qwen and FLUX model sets",
    )
    args = parser.parse_args()

    comfy_dir = Path(args.comfy_dir)
    models_dir = comfy_dir / "models"

    print("=" * 70)
    print(" PanelFlow Studio - Model Downloader")
    print("=" * 70)
    print(f"Target ComfyUI Directory: {comfy_dir}")
    print(f"Target Models Directory: {models_dir}")

    if not comfy_dir.exists():
        print(f"[!] Warning: ComfyUI directory does not exist at '{comfy_dir}'")
        choice = input("Create it and continue? [y/N]: ").strip().lower()
        if choice != "y":
            print("Aborted.")
            sys.exit(1)

    # Determine which sets to download
    selected_sets = []
    if args.all:
        selected_sets = ["qwen", "flux"]
    elif args.qwen:
        selected_sets = ["qwen"]
    elif args.flux:
        selected_sets = ["flux"]
    else:
        # Interactive prompt
        print("\nPlease choose which model suite to download:")
        print("  1) Qwen 2.5-VL + LongCat-Image (Matches PanelFlow's manga_image_generation registry)")
        print("  2) FLUX.1 [schnell] + T5-XXL + PuLID (Fastest, Apache 2.0, top narrative prompt adherence)")
        print("  3) Both suites")
        print("  4) Exit")
        choice = input("\nEnter choice [1-4]: ").strip()
        if choice == "1":
            selected_sets = ["qwen"]
        elif choice == "2":
            selected_sets = ["flux"]
        elif choice == "3":
            selected_sets = ["qwen", "flux"]
        else:
            print("Exiting.")
            sys.exit(0)

    # Execute downloads
    for model_set in selected_sets:
        items = MODELS[model_set]
        print(f"\n>>> Starting Download: {model_set.upper()} Model Suite ({len(items)} files)")
        for item in items:
            target_file = models_dir / item["subfolder"] / item["filename"]
            if target_file.exists() and target_file.stat().st_size > 1024 * 1024:
                print(f"\n[=] Already exists: {target_file.name} ({format_bytes(target_file.stat().st_size)}) - Skipping.")
                continue

            success = download_file_with_resume(item["url"], target_file, f"{item['name']} ({item['size_gb']})")
            if not success:
                print(f"[!] Warning: Failed downloading {item['name']}. You can re-run to resume.")

    print("\n" + "=" * 70)
    print(" Download process finished!")
    print("=" * 70)
    print("You can restart ComfyUI to detect the new models.")


if __name__ == "__main__":
    main()
