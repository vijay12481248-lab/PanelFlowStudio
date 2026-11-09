"""PanelFlow Studio - Wan2.1 14B I2V Model Downloader and Verification Tool.

Comports with AGENTS.md constraint:
"Downloads of models/files need the owner's approval with the exact file, size and source first."

Provides:
  --inspect : Pre-download manifest reporting (file names, sizes, sources, hashes).
  --verify  : Local file presence and SHA-256 integrity verification.
  --download: Download missing files (requires --approve or interactive confirmation).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_COMFY_ROOT = Path(os.environ.get("PANELFLOW_COMFYUI_DIR", r"E:\VIJAY SEKAR\ComfyUI"))
HF_BASE_URL = "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main"

# Authoritative model manifest for Wan2.1 14B Image-to-Video
WAN_MODELS_MANIFEST: List[Dict[str, Any]] = [
    {
        "id": "wan2.1_diffusion_480p",
        "name": "Wan2.1 I2V 14B 480P DiT (FP8 Scaled)",
        "subfolder": "diffusion_models",
        "filename": "wan2.1_i2v_480p_14B_fp8_scaled.safetensors",
        "repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged",
        "rel_path": "split_files/diffusion_models/wan2.1_i2v_480p_14B_fp8_scaled.safetensors",
        "url": f"{HF_BASE_URL}/split_files/diffusion_models/wan2.1_i2v_480p_14B_fp8_scaled.safetensors",
        "size_bytes": 16401356938,
        "sha256": "b2de21b99b2e72cb0ff15253b07e926f26e7cf1b7e229efc32f94ad1f1ed9395",
        "required": True,
        "resolution": "480p",
        "description": "Primary 14B DiT video diffusion weights with embedded FP8 scaling factors (native 832x480).",
    },
    {
        "id": "wan2.1_text_encoder",
        "name": "UMT5-XXL Text Encoder (FP8 Scaled)",
        "subfolder": "text_encoders",
        "filename": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged",
        "rel_path": "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "url": f"{HF_BASE_URL}/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "size_bytes": 6735906897,
        "sha256": "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68",
        "required": True,
        "resolution": "all",
        "description": "Multilingual UMT5-XXL text encoder in FP8 scaled format, loaded by CLIPLoader(type='wan').",
    },
    {
        "id": "wan2.1_vae",
        "name": "Wan2.1 3D Video VAE",
        "subfolder": "vae",
        "filename": "wan_2.1_vae.safetensors",
        "repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged",
        "rel_path": "split_files/vae/wan_2.1_vae.safetensors",
        "url": f"{HF_BASE_URL}/split_files/vae/wan_2.1_vae.safetensors",
        "size_bytes": 253815318,
        "sha256": "2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b",
        "required": True,
        "resolution": "all",
        "description": "Native Wan2.1 3D spatio-temporal VAE for frame encoding and latent decoding.",
    },
    {
        "id": "wan2.1_clip_vision_optional",
        "name": "CLIP-ViT-H-14 Vision Encoder (FP16 Optional)",
        "subfolder": "clip_vision",
        "filename": "clip_vision_h.safetensors",
        "repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged",
        "rel_path": "split_files/clip_vision/clip_vision_h.safetensors",
        "url": f"{HF_BASE_URL}/split_files/clip_vision/clip_vision_h.safetensors",
        "size_bytes": 1264219396,
        "sha256": "64a7ef761bfccbadbaa3da77366aac4185a6c58fa5de5f589b42a65bcc21f161",
        "required": False,
        "resolution": "all",
        "description": "Optional image encoder. Note: ComfyUI already possesses CLIP-ViT-H-14 in models/clip_vision.",
    },
    {
        "id": "wan2.1_diffusion_720p_optional",
        "name": "Wan2.1 I2V 14B 720P DiT (FP8 Scaled Optional)",
        "subfolder": "diffusion_models",
        "filename": "wan2.1_i2v_720p_14B_fp8_scaled.safetensors",
        "repo": "Comfy-Org/Wan_2.1_ComfyUI_repackaged",
        "rel_path": "split_files/diffusion_models/wan2.1_i2v_720p_14B_fp8_scaled.safetensors",
        "url": f"{HF_BASE_URL}/split_files/diffusion_models/wan2.1_i2v_720p_14B_fp8_scaled.safetensors",
        "size_bytes": 16401356938,
        "sha256": "6d7a34b63b70eb608324e546d979167a5e787ac6bca3528e63f54a11572d66aa",
        "required": False,
        "resolution": "720p",
        "description": "Optional 720P DiT model. Note: May encounter memory pressure on 16GB VRAM GPUs.",
    },
]


def compute_sha256(path: Path, block_size: int = 8 * 1024 * 1024, progress_cb=None) -> str:
    """Calculate SHA256 hash of a file with streaming chunks."""
    h = hashlib.sha256()
    total_bytes = path.stat().st_size
    bytes_read = 0
    with open(path, "rb") as f:
        while chunk := f.read(block_size):
            h.update(chunk)
            bytes_read += len(chunk)
            if progress_cb:
                progress_cb(bytes_read, total_bytes)
    return h.hexdigest()


def inspect_manifest(comfy_root: Path, variant: str = "480p") -> Dict[str, Any]:
    """Inspect model manifest and return detailed summary for owner approval."""
    models_dir = comfy_root / "models"
    selected = [
        m for m in WAN_MODELS_MANIFEST
        if (m["required"] and (m["resolution"] in ("all", variant)))
        or (variant == "720p" and m["id"] == "wan2.1_diffusion_720p_optional")
    ]

    total_bytes = sum(m["size_bytes"] for m in selected)
    total_gb = total_bytes / (1024 ** 3)

    items = []
    for m in selected:
        target_path = models_dir / m["subfolder"] / m["filename"]
        items.append({
            "name": m["name"],
            "filename": m["filename"],
            "subfolder": m["subfolder"],
            "target_path": str(target_path),
            "size_bytes": m["size_bytes"],
            "size_gb": round(m["size_bytes"] / (1024 ** 3), 2),
            "expected_sha256": m["sha256"],
            "source_repo": m["repo"],
            "url": m["url"],
            "description": m["description"],
            "exists": target_path.exists(),
        })

    return {
        "variant": variant,
        "comfy_root": str(comfy_root),
        "total_files": len(items),
        "total_bytes": total_bytes,
        "total_gb": round(total_gb, 2),
        "items": items,
    }


def verify_models(comfy_root: Path, variant: str = "480p", quick: bool = False) -> Dict[str, Any]:
    """Verify presence, file size, and optionally SHA256 checksums of local models."""
    models_dir = comfy_root / "models"
    manifest = inspect_manifest(comfy_root, variant)
    results = []
    all_ok = True

    for item in manifest["items"]:
        path = Path(item["target_path"])
        entry = {
            "name": item["name"],
            "filename": item["filename"],
            "path": str(path),
            "expected_bytes": item["size_bytes"],
            "expected_sha256": item["expected_sha256"],
            "status": "UNKNOWN",
        }
        if not path.exists():
            entry["status"] = "MISSING"
            all_ok = False
        else:
            actual_size = path.stat().st_size
            entry["actual_bytes"] = actual_size
            if actual_size != item["size_bytes"]:
                entry["status"] = f"SIZE_MISMATCH (got {actual_size}, expected {item['size_bytes']})"
                all_ok = False
            elif quick:
                entry["status"] = "OK (size matched)"
            else:
                print(f"  Verifying SHA256 for {item['filename']}...")
                actual_hash = compute_sha256(path)
                entry["actual_sha256"] = actual_hash
                if actual_hash.lower() == item["expected_sha256"].lower():
                    entry["status"] = "VERIFIED_OK"
                else:
                    entry["status"] = f"HASH_MISMATCH (got {actual_hash})"
                    all_ok = False
        results.append(entry)

    return {"ready": all_ok, "variant": variant, "results": results}


def download_model(item: Dict[str, Any], dest_path: Path) -> bool:
    """Download single model file with resumption and verification."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = dest_path.with_suffix(dest_path.suffix + ".part")

    existing_bytes = 0
    if dest_path.exists():
        if dest_path.stat().st_size == item["size_bytes"]:
            print(f"  Verifying SHA256 for existing {dest_path.name}...")
            if compute_sha256(dest_path).lower() == item["expected_sha256"].lower():
                print(f"[OK] File already exists and verified: {dest_path.name}")
                return True
            print(f"[WARN] Existing file {dest_path.name} is corrupt (hash mismatch). Removing for fresh download.")
            dest_path.unlink(missing_ok=True)
        else:
            if not part_path.exists():
                dest_path.rename(part_path)
            else:
                dest_path.unlink(missing_ok=True)

    if part_path.exists():
        existing_bytes = part_path.stat().st_size
        if existing_bytes >= item["size_bytes"]:
            if existing_bytes == item["size_bytes"] and compute_sha256(part_path).lower() == item["expected_sha256"].lower():
                dest_path.unlink(missing_ok=True)
                part_path.replace(dest_path)
                print(f"[COMPLETE] {item['name']} verified and installed: {dest_path.name}\n")
                return True
            print(f"[WARN] Stale/corrupt part file {part_path.name} detected. Removing to start fresh.")
            part_path.unlink(missing_ok=True)
            existing_bytes = 0

    headers = {"User-Agent": "PanelFlow-Studio/1.0"}
    if existing_bytes > 0:
        headers["Range"] = f"bytes={existing_bytes}-"
        print(f"\n[RESUME] {item['name']} from {existing_bytes / (1024*1024):.1f} MB...")
    else:
        print(f"\n[START] Downloading {item['name']} ({item['size_gb']} GB)...")
        print(f"  Source URL: {item['url']}")
        print(f"  Target:     {dest_path}")

    req = urllib.request.Request(item["url"], headers=headers)
    t0 = time.time()
    last_print = 0

    mode = "ab" if existing_bytes > 0 else "wb"
    with urllib.request.urlopen(req, timeout=60) as resp, open(part_path, mode) as out_f:
        downloaded = existing_bytes
        total = item["size_bytes"]
        chunk_size = 2 * 1024 * 1024  # 2 MB chunks

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
                gb_done = downloaded / (1024 ** 3)
                gb_tot = total / (1024 ** 3)
                sys.stdout.write(f"\r  [{pct:5.1f}%] {gb_done:.2f} / {gb_tot:.2f} GB @ {speed_mb:.2f} MB/s ")
                sys.stdout.flush()

    sys.stdout.write("\n")
    print(f"  Verifying downloaded checksum for {dest_path.name}...")
    calc_hash = compute_sha256(part_path)
    if calc_hash.lower() != item["expected_sha256"].lower():
        print(f"[ERROR] SHA256 mismatch for {dest_path.name}!")
        print(f"  Expected: {item['expected_sha256']}")
        print(f"  Actual:   {calc_hash}")
        part_path.unlink(missing_ok=True)
        return False

    dest_path.unlink(missing_ok=True)
    part_path.replace(dest_path)
    print(f"[COMPLETE] {item['name']} verified and installed: {dest_path.name}\n")
    return True


def print_approval_report(manifest: Dict[str, Any]) -> None:
    """Print structured table for owner approval as mandated by AGENTS.md."""
    print("=" * 80)
    print(" PANELFLOW STUDIO - MODEL DOWNLOAD SPECIFICATION & APPROVAL REPORT")
    print(" (Per AGENTS.md: Downloads of models/files need owner approval with exact")
    print("  file, size, and source first)")
    print("=" * 80)
    print(f"Variant:           {manifest['variant']}")
    print(f"ComfyUI Root:      {manifest['comfy_root']}")
    print(f"Total Model Files: {manifest['total_files']}")
    print(f"Total Download:    {manifest['total_gb']} GB ({manifest['total_bytes']:,} bytes)")
    print("-" * 80)

    for i, item in enumerate(manifest["items"], 1):
        status = "[INSTALLED]" if item["exists"] else "[NOT DOWNLOADED]"
        print(f"{i}. {item['name']} {status}")
        print(f"   Target Subfolder: models/{item['subfolder']}/")
        print(f"   Filename:         {item['filename']}")
        print(f"   Exact Size:       {item['size_bytes']:,} bytes ({item['size_gb']} GB)")
        print(f"   Expected SHA256:  {item['expected_sha256']}")
        print(f"   HuggingFace Repo: {item['source_repo']}")
        print(f"   Direct URL:       {item['url']}")
        print(f"   Description:      {item['description']}")
        print("-" * 80)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wan2.1 14B Model Downloader and Verifier")
    parser.add_argument("--comfy-dir", type=Path, default=DEFAULT_COMFY_ROOT, help="ComfyUI installation path")
    parser.add_argument("--variant", choices=["480p", "720p"], default="480p", help="Target resolution variant")
    parser.add_argument("--inspect", action="store_true", help="Print exact file, size, source specification for approval")
    parser.add_argument("--verify", action="store_true", help="Verify presence and checksums of local model files")
    parser.add_argument("--quick", action="store_true", help="Quick verification (size only, skip full SHA256 hash)")
    parser.add_argument("--download", action="store_true", help="Download missing models")
    parser.add_argument("--approve", action="store_true", help="Explicit owner approval flag required for non-interactive download")
    args = parser.parse_args(argv)

    comfy_dir = args.comfy_dir
    manifest = inspect_manifest(comfy_dir, args.variant)

    if args.inspect or (not args.verify and not args.download):
        print_approval_report(manifest)
        return 0

    if args.verify:
        print(f"Verifying Wan2.1 models in {comfy_dir / 'models'}...")
        res = verify_models(comfy_dir, args.variant, quick=args.quick)
        print("\nVerification Results:")
        for r in res["results"]:
            print(f" - {r['filename']}: {r['status']}")
        if res["ready"]:
            print("\n[ALL MODELS READY] ComfyUI has all required Wan2.1 weights.")
            return 0
        else:
            print("\n[MODELS MISSING OR INCOMPLETE] Run with --inspect to view required downloads.")
            return 1

    if args.download:
        print_approval_report(manifest)
        if not args.approve:
            if not sys.stdin.isatty():
                print("\n[ERROR] Non-interactive download requires explicit --approve flag complying with AGENTS.md.")
                return 2
            try:
                confirm = input("\nDo you approve downloading these exact files? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nDownload cancelled: input stream closed.")
                return 2
            if confirm not in ("y", "yes"):
                print("Download cancelled: owner approval was not granted.")
                return 0

        print("\nProceeding with approved model download...")
        for item in manifest["items"]:
            dest = comfy_dir / "models" / item["subfolder"] / item["filename"]
            success = download_model(item, dest)
            if not success:
                print(f"[FAILED] Failed to verify or download {item['filename']}.")
                return 1
        print("\n[SUCCESS] All approved Wan2.1 models downloaded and verified.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
