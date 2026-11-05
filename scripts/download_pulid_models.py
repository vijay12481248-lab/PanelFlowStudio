"""Download and setup PuLID-Flux models in ComfyUI."""
import os
import sys
import time
import zipfile
import urllib.request
from pathlib import Path

COMFY_ROOT = Path(r"E:\VIJAY SEKAR\ComfyUI")
PULID_DIR = COMFY_ROOT / "models" / "pulid"
INSIGHT_DIR = COMFY_ROOT / "models" / "insightface" / "models" / "antelopev2"
CLIP_DIR = COMFY_ROOT / "models" / "clip"
PULID_DIR.mkdir(parents=True, exist_ok=True)
INSIGHT_DIR.mkdir(parents=True, exist_ok=True)
CLIP_DIR.mkdir(parents=True, exist_ok=True)

def download_file(url: str, dest_path: Path, desc: str):
    if dest_path.exists() and dest_path.stat().st_size > 1000000:
        print(f"[EXISTS] {desc}: {dest_path.name} ({dest_path.stat().st_size / (1024*1024):.1f} MB)", flush=True)
        return
    print(f"\n[DOWNLOADING] {desc}...", flush=True)
    print(f"  URL: {url}", flush=True)
    print(f"  Dest: {dest_path}", flush=True)
    t0 = time.time()
    
    # Custom opener with User-Agent
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')]
    urllib.request.install_opener(opener)
    
    last_print = 0
    def reporthook(count, block_size, total_size):
        nonlocal last_print
        if total_size > 0:
            mb = (count * block_size) / (1024 * 1024)
            tot_mb = total_size / (1024 * 1024)
            pct = count * block_size / total_size * 100
            now = time.time()
            if now - last_print > 3 or mb >= tot_mb:
                last_print = now
                speed = mb / max(0.1, now - t0)
                print(f"  {pct:.1f}% ({mb:.1f}/{tot_mb:.1f} MB) @ {speed:.2f} MB/s", flush=True)

    tmp_path = dest_path.with_suffix(".downloading")
    urllib.request.urlretrieve(url, tmp_path, reporthook=reporthook)
    tmp_path.rename(dest_path)
    dur = time.time() - t0
    size_mb = dest_path.stat().st_size / (1024 * 1024)
    print(f"  [COMPLETED] {dest_path.name} in {dur:.1f}s ({size_mb:.1f} MB, {size_mb/dur:.2f} MB/s)", flush=True)

def main():
    print("=== PuLID-Flux Model Downloader ===", flush=True)
    
    # 1. PuLID FLUX model
    pulid_url = "https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.0.safetensors"
    pulid_file = PULID_DIR / "pulid_flux_v0.9.0.safetensors"
    download_file(pulid_url, pulid_file, "PuLID-FLUX Checkpoint (v0.9.0)")
    
    # 2. AntelopeV2 models
    antelope_zip = INSIGHT_DIR.parent / "antelopev2.zip"
    antelope_url = "https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip"
    download_file(antelope_url, antelope_zip, "InsightFace AntelopeV2 Zip")
    
    # Extract antelopev2
    print("\n[EXTRACTING] AntelopeV2 models...", flush=True)
    with zipfile.ZipFile(antelope_zip, 'r') as zip_ref:
        zip_ref.extractall(INSIGHT_DIR)
    print(f"  Extracted to {INSIGHT_DIR}:", [f.name for f in INSIGHT_DIR.glob("*.onnx")], flush=True)
    antelope_zip.unlink(missing_ok=True)
    
    # 3. EVA02-CLIP model
    eva_url = "https://huggingface.co/QuanSun/EVA-CLIP/resolve/main/EVA02_CLIP_L_336_psz14_s6B.pt"
    eva_file = CLIP_DIR / "EVA02_CLIP_L_336_psz14_s6B.pt"
    download_file(eva_url, eva_file, "EVA02-CLIP PyTorch Weight")
    
    # Also link/copy to Hugging Face cache so timm/open_clip finds it seamlessly
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub" / "models--QuanSun--EVA-CLIP" / "snapshots" / "main"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "EVA02_CLIP_L_336_psz14_s6B.pt"
    if not cache_file.exists() and eva_file.exists():
        import shutil
        shutil.copy2(eva_file, cache_file)
        print(f"  Linked to HF cache: {cache_file}", flush=True)

    print("\n=== All PuLID-Flux Models Downloaded and Ready! ===", flush=True)

if __name__ == "__main__":
    main()
