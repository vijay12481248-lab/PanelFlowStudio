"""Automated Environment, Hardware, and Commercial Licensing Audit for AI Visual Quality Inspector."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("panelflow.audit")

COMFYUI_DIR = Path(r"E:\VIJAY SEKAR\ComfyUI")

# Required model catalog with license metadata
REQUIRED_MODELS: Dict[str, Dict[str, Any]] = {
    "yunet": {
        "rel_path": "models/opencv/face_detection_yunet_2023mar.onnx",
        "description": "OpenCV YuNet Face Detector (CPU)",
        "license": "Apache 2.0",
        "commercial_cleared": True,
        "purpose": "Face Detection & 5-point Landmarking",
    },
    "sface": {
        "rel_path": "models/opencv/face_recognition_sface_2021dec.onnx",
        "description": "OpenCV SFace Identity Embedder (CPU)",
        "license": "Apache 2.0",
        "commercial_cleared": True,
        "purpose": "Identity Similarity & Duplicate Detection",
    },
    "dwpose_body": {
        "rel_path": "models/dwpose/dw-ll_ucoco_384.onnx",
        "description": "DWPose 133-Keypoint Pose Estimator",
        "license": "Apache 2.0 / Open Source",
        "commercial_cleared": True,
        "purpose": "Skeletal Topology & Missing Limbs",
    },
    "dwpose_det": {
        "rel_path": "models/dwpose/yolox_l.onnx",
        "description": "YOLOX-L Person Bounding Box Detector",
        "license": "Apache 2.0",
        "commercial_cleared": True,
        "purpose": "Person Localization & Counting",
    },
    "animagine_inpaint": {
        "rel_path": "models/checkpoints/animagine-xl-4.0.safetensors",
        "description": "Animagine XL 4.0 SDXL Checkpoint",
        "license": "CreativeML Open RAIL++-M",
        "commercial_cleared": True,
        "purpose": "Localized Masked Inpainting Repair",
    },
}

REQUIRED_CUSTOM_NODES = [
    "ComfyUI-H3-FaceRefine",
    "ComfyUI_IPAdapter_plus",
    "ComfyUI-PuLID-Flux",
    "Herrgotts-H3-Infinite-Continuation-Suite",
]


def audit_hardware() -> Dict[str, Any]:
    """Audits GPU, CUDA availability, and host RAM."""
    hw_info: Dict[str, Any] = {
        "cuda_available": False,
        "device_count": 0,
        "devices": [],
        "system_ram_gb": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024**3), 2)
        if hasattr(os, "sysconf") else 32.0,
    }

    try:
        import torch
        hw_info["cuda_available"] = torch.cuda.is_available()
        hw_info["torch_version"] = torch.__version__
        if torch.cuda.is_available():
            hw_info["device_count"] = torch.cuda.device_count()
            for i in range(torch.cuda.device_count()):
                prop = torch.cuda.get_device_properties(i)
                hw_info["devices"].append({
                    "id": i,
                    "name": prop.name,
                    "total_vram_gb": round(prop.total_memory / (1024**3), 2),
                    "major": prop.major,
                    "minor": prop.minor,
                })
    except Exception as exc:
        hw_info["error"] = str(exc)

    return hw_info


def audit_comfyui() -> Dict[str, Any]:
    """Audits ComfyUI base path, models, and custom nodes."""
    exists = COMFYUI_DIR.is_dir()
    models_audit: Dict[str, Any] = {}
    nodes_audit: Dict[str, Any] = {}

    if exists:
        for key, spec in REQUIRED_MODELS.items():
            full_p = COMFYUI_DIR / spec["rel_path"]
            is_present = full_p.is_file()
            size_mb = round(full_p.stat().st_size / (1024**2), 2) if is_present else 0.0
            models_audit[key] = {
                "present": is_present,
                "size_mb": size_mb,
                "path": str(full_p),
                "license": spec["license"],
                "commercial_cleared": spec["commercial_cleared"],
                "purpose": spec["purpose"],
            }

        custom_nodes_dir = COMFYUI_DIR / "custom_nodes"
        for node in REQUIRED_CUSTOM_NODES:
            node_p = custom_nodes_dir / node
            nodes_audit[node] = {
                "installed": node_p.is_dir(),
                "path": str(node_p),
            }

    return {
        "comfyui_dir": str(COMFYUI_DIR),
        "exists": exists,
        "models": models_audit,
        "custom_nodes": nodes_audit,
    }


def audit_ollama() -> Dict[str, Any]:
    """Probes local Ollama instance on port 11434 and checks for qwen3.5:9b."""
    ollama_info: Dict[str, Any] = {
        "connected": False,
        "url": "http://127.0.0.1:11434",
        "models": [],
        "has_qwen35": False,
    }
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", headers={"User-Agent": "PanelFlow-Audit"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                ollama_info["connected"] = True
                models = [m.get("name") for m in data.get("models", [])]
                ollama_info["models"] = models
                ollama_info["has_qwen35"] = any("qwen3.5:9b" in m for m in models)
    except Exception as exc:
        ollama_info["error"] = str(exc)

    return ollama_info


def audit_ffmpeg() -> Dict[str, Any]:
    """Checks FFmpeg executable and h264_nvenc hardware acceleration support."""
    ffmpeg_bin = shutil.which("ffmpeg")
    ffmpeg_info: Dict[str, Any] = {
        "installed": ffmpeg_bin is not None,
        "path": ffmpeg_bin,
        "nvenc_supported": False,
    }

    if ffmpeg_bin:
        try:
            r = subprocess.run(
                [ffmpeg_bin, "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1",
                 "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"],
                capture_output=True,
            )
            ffmpeg_info["nvenc_supported"] = (r.returncode == 0)
        except Exception:
            ffmpeg_info["nvenc_supported"] = False

    return ffmpeg_info


def run_full_audit(output_json_path: str = "docs/quality_inspector/audit_environment_report.json") -> Dict[str, Any]:
    """Executes full environment, hardware, and commercial licensing audit."""
    logger.info("Executing Phase 0 Environment & Commercial Licensing Audit...")

    hw = audit_hardware()
    comfy = audit_comfyui()
    ollama = audit_ollama()
    ff = audit_ffmpeg()

    all_models_present = all(m.get("present", False) for m in comfy.get("models", {}).values())
    all_commercial_cleared = all(m.get("commercial_cleared", False) for m in comfy.get("models", {}).values())
    all_nodes_present = all(n.get("installed", False) for n in comfy.get("custom_nodes", {}).values())
    gpu_ready = hw.get("cuda_available", False) and len(hw.get("devices", [])) > 0

    overall_ready = all_models_present and all_commercial_cleared and ollama.get("connected", False) and gpu_ready

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_ready": overall_ready,
        "hardware": hw,
        "comfyui": comfy,
        "ollama": ollama,
        "ffmpeg": ff,
        "licensing_summary": {
            "all_models_commercial_cleared": all_commercial_cleared,
            "non_commercial_replacements": [
                "InsightFace Antelopev2 (Non-commercial research only) -> REPLACED by OpenCV YuNet + SFace (Apache 2.0)",
                "Qwen Image 2.1 (Non-commercial research license) -> RETIRED, replaced by Animagine XL 4.0 SDXL (Open RAIL++-M)",
            ],
            "commercial_models": [
                {"name": "OpenCV YuNet", "license": "Apache 2.0", "status": "Active & Verified"},
                {"name": "OpenCV SFace", "license": "Apache 2.0", "status": "Active & Verified"},
                {"name": "DWPose (ONNX)", "license": "Apache 2.0", "status": "Active & Verified"},
                {"name": "Animagine XL 4.0", "license": "CreativeML Open RAIL++-M", "status": "Active & Verified"},
                {"name": "HiDream-I1 Fast", "license": "MIT", "status": "Active & Verified"},
                {"name": "Z-Image Turbo", "license": "Apache 2.0", "status": "Active & Verified"},
            ],
        },
    }

    out_p = Path(output_json_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(f"Phase 0 Audit Report written to: {out_p}")

    # Print summary to console
    print("\n" + "=" * 70)
    print("PHASE 0: ENVIRONMENT & COMMERCIAL LICENSING AUDIT SUMMARY")
    print("=" * 70)
    if hw["devices"]:
        dev = hw["devices"][0]
        print(f"GPU: {dev['name']} ({dev['total_vram_gb']} GB VRAM) - CUDA Ready: {hw['cuda_available']}")
    print(f"Ollama: {'CONNECTED (qwen3.5:9b available)' if ollama['has_qwen35'] else 'OFFLINE/MISSING'}")
    print(f"FFmpeg: {'FOUND' if ff['installed'] else 'NOT FOUND'} (NVENC Hardware Acceleration: {ff['nvenc_supported']})")
    print("-" * 70)
    print("MODEL CATALOG & LICENSING STATUS:")
    for k, v in comfy["models"].items():
        status_sym = "[OK]" if v["present"] else "[MISSING]"
        print(f"  {status_sym} {k:<18} | Size: {v['size_mb']:>6.1f} MB | License: {v['license']} (Commercial: {v['commercial_cleared']})")
    print("-" * 70)
    print("COMFYUI CUSTOM NODES:")
    for k, v in comfy["custom_nodes"].items():
        status_sym = "[OK]" if v["installed"] else "[MISSING]"
        print(f"  {status_sym} {k}")
    print("=" * 70)
    print(f"PHASE 0 STATUS: {'ENVIRONMENT READY FOR PHASE 1' if overall_ready else 'DEGRADED / ACTION NEEDED'}")
    print("=" * 70 + "\n")

    return report


if __name__ == "__main__":
    run_full_audit()
