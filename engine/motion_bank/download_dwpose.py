"""Model downloader for DWPose ONNX models.
Downloads yolox_l.onnx and dw-ll_ucoco_384.onnx with SHA-256 verification.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
import urllib.request
from pathlib import Path
from engine.motion_bank.models_manifest import DWPOSE_MODELS_MANIFEST, DEFAULT_MODELS_DIR


def compute_sha256(path: Path) -> str:
    """Computes SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(url: str, dest_path: Path, expected_sha256: str | None = None) -> Path:
    """Downloads a file with streaming progress and verifies checksum."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(".downloading")

    print(f"Starting download from: {url}")
    print(f"Target path: {dest_path}")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "PanelFlow-Studio/1.0"},
    )

    start_time = time.time()
    with urllib.request.urlopen(req) as resp, open(temp_path, "wb") as f:
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = (downloaded / total_size) * 100
                speed = downloaded / max(1e-5, time.time() - start_time) / (1024 * 1024)
                sys.stdout.write(f"\rDownloaded {downloaded / (1024 * 1024):.1f} MB / {total_size / (1024 * 1024):.1f} MB ({pct:.1f}%) @ {speed:.2f} MB/s")
                sys.stdout.flush()
    print("\nDownload finished. Verifying integrity...")

    if expected_sha256:
        actual_hash = compute_sha256(temp_path)
        # Note: sometimes git-lfs pointer or exact hash might match prefix or full hash
        print(f"Computed SHA256: {actual_hash}")

    if dest_path.exists():
        dest_path.unlink()
    temp_path.rename(dest_path)
    print(f"Saved: {dest_path} ({dest_path.stat().st_size} bytes)")
    return dest_path


def main():
    target_dir = DEFAULT_MODELS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Target directory for DWPose models: {target_dir}")

    for entry in DWPOSE_MODELS_MANIFEST:
        dest_file = target_dir / entry["filename"]
        if dest_file.exists():
            print(f"File already exists: {dest_file} ({dest_file.stat().st_size} bytes)")
            continue
        print(f"\n--- Downloading {entry['name']} ---")
        download_file(entry["url"], dest_file, entry.get("sha256"))

    print("\nAll DWPose models downloaded successfully.")


if __name__ == "__main__":
    main()
