"""PanelFlow Studio - Preflight System Health & Production Capability Auditor.

Comprehensive diagnostics covering local models, ComfyUI workflows, InsightFace ArcFace,
audio synthesizers, FFmpeg toolchains, GPU VRAM headroom, and working disk space.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import urllib.request
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger("panelflow.system.health")


@dataclass
class CapabilityCheck:
    name: str
    category: Literal["model", "vision", "audio", "hardware", "tool"]
    status: Literal["ok", "warning", "error"]
    available: bool
    details: str
    recommendation: str | None = None


@dataclass
class ProductionReadinessReport:
    ready: bool
    all_ok: bool
    checks: dict[str, CapabilityCheck] = field(default_factory=dict)
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ready": self.ready,
            "all_ok": self.all_ok,
            "summary": self.summary,
            "recommendations": self.recommendations,
            "checks": {
                k: {
                    "name": v.name,
                    "category": v.category,
                    "status": v.status,
                    "available": v.available,
                    "details": v.details,
                    "recommendation": v.recommendation,
                }
                for k, v in self.checks.items()
            },
        }


def check_ollama(endpoint: str = "http://127.0.0.1:11434") -> CapabilityCheck:
    """Check Ollama service status and loaded model tags."""
    try:
        req = urllib.request.Request(f"{endpoint}/api/tags", headers={"User-Agent": "PanelFlow-Health"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name") for m in data.get("models", [])]
            qwen_found = any("qwen" in m.lower() for m in models)
            if qwen_found:
                return CapabilityCheck(
                    name="Ollama LLM & Vision",
                    category="model",
                    status="ok",
                    available=True,
                    details=f"Ollama online with {len(models)} model(s) (including Qwen)",
                )
            return CapabilityCheck(
                name="Ollama LLM & Vision",
                category="model",
                status="warning",
                available=True,
                details=f"Ollama running but no Qwen model found among: {models[:4]}",
                recommendation="Run: ollama pull qwen3.5:9b",
            )
    except Exception as exc:
        return CapabilityCheck(
            name="Ollama LLM & Vision",
            category="model",
            status="error",
            available=False,
            details=f"Ollama unreachable on {endpoint}: {exc}",
            recommendation="Start Ollama locally: ollama serve",
        )


def check_comfyui(endpoint: str = "http://127.0.0.1:8188") -> CapabilityCheck:
    """Check ComfyUI local daemon connectivity."""
    try:
        req = urllib.request.Request(f"{endpoint}/system_stats", headers={"User-Agent": "PanelFlow-Health"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            devs = data.get("devices", [])
            vram_info = f"{devs[0].get('name', 'GPU')} (VRAM {devs[0].get('vram_total', 0) // (1024**2)} MB)" if devs else "Active"
            return CapabilityCheck(
                name="ComfyUI Server",
                category="tool",
                status="ok",
                available=True,
                details=f"ComfyUI online on {endpoint} ({vram_info})",
            )
    except Exception as exc:
        return CapabilityCheck(
            name="ComfyUI Server",
            category="tool",
            status="warning",
            available=False,
            details=f"ComfyUI daemon not running on {endpoint}: {exc}",
            recommendation="Start ComfyUI: cd 'E:\\VIJAY SEKAR\\ComfyUI' && venv\\Scripts\\python.exe main.py --listen 127.0.0.1 --port 8188",
        )


def check_comfyui_workflows() -> CapabilityCheck:
    """Verify authorized FLUX.2 Klein 4B workflow files in the registry."""
    try:
        from engine.comfyui.art import ArtEngine
        from engine.comfyui.client import ComfyUIClient
        from engine.comfyui.registry import ComfyWorkflowRegistry

        client = ComfyUIClient()
        reg = ComfyWorkflowRegistry(client)
        workflows = reg.list_workflows() if hasattr(reg, "list_workflows") else []

        has_klein = "flux2_klein_4b" in workflows or Path("engine/comfyui/workflows/flux2_klein_4b.json").exists()
        has_klein_ref = "flux2_klein_4b_ref" in workflows or Path("engine/comfyui/workflows/flux2_klein_4b_ref.json").exists()

        if has_klein and has_klein_ref:
            return CapabilityCheck(
                name="FLUX.2 Klein 4B Workflows",
                category="model",
                status="ok",
                available=True,
                details="flux2_klein_4b & flux2_klein_4b_ref verified",
            )
        elif has_klein:
            return CapabilityCheck(
                name="FLUX.2 Klein 4B Workflows",
                category="model",
                status="warning",
                available=True,
                details="flux2_klein_4b found, but flux2_klein_4b_ref missing",
                recommendation="Ensure flux2_klein_4b_ref.json is installed in engine/comfyui/workflows/",
            )
        return CapabilityCheck(
            name="FLUX.2 Klein 4B Workflows",
            category="model",
            status="error",
            available=False,
            details="Authorized flux2_klein_4b workflow not found",
            recommendation="Install authorized FLUX.2 Klein 4B workflow JSONs",
        )
    except Exception as exc:
        return CapabilityCheck(
            name="FLUX.2 Klein 4B Workflows",
            category="model",
            status="warning",
            available=False,
            details=f"Workflow check error: {exc}",
        )


def check_insightface_models() -> CapabilityCheck:
    """Verify local AntelopeV2 ONNX ArcFace and SCRFD models."""
    try:
        from engine.characters.face_verify import (
            GLINTR100_ONNX_NAME,
            SCRFD_ONNX_NAME,
            _resolve_model_path,
        )

        glintr = _resolve_model_path(GLINTR100_ONNX_NAME)
        scrfd = _resolve_model_path(SCRFD_ONNX_NAME)

        if glintr and scrfd:
            return CapabilityCheck(
                name="InsightFace ArcFace 512-D",
                category="vision",
                status="ok",
                available=True,
                details=f"SCRFD detector + GlintR100 ArcFace verified ({glintr.parent})",
            )
        elif glintr:
            return CapabilityCheck(
                name="InsightFace ArcFace 512-D",
                category="vision",
                status="warning",
                available=True,
                details="GlintR100 available, SCRFD missing (using portrait crop fallback)",
            )
        return CapabilityCheck(
            name="InsightFace ArcFace 512-D",
            category="vision",
            status="warning",
            available=False,
            details="ONNX AntelopeV2 face models not located (using offline color histogram fallback)",
            recommendation="Place glintr100.onnx and scrfd_10g_bnkps.onnx in ComfyUI models/insightface/",
        )
    except Exception as exc:
        return CapabilityCheck(
            name="InsightFace ArcFace 512-D",
            category="vision",
            status="error",
            available=False,
            details=f"Face verification check failed: {exc}",
        )


def check_ffmpeg() -> CapabilityCheck:
    """Verify FFmpeg installation and required encoders/filters."""
    try:
        res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True)
        out = res.stdout.lower()
        has_libass = "--enable-libass" in out
        has_x264 = "--enable-libx264" in out

        if has_libass and has_x264:
            return CapabilityCheck(
                name="FFmpeg Media Toolchain",
                category="tool",
                status="ok",
                available=True,
                details="FFmpeg available with libx264 and libass (subtitles)",
            )
        return CapabilityCheck(
            name="FFmpeg Media Toolchain",
            category="tool",
            status="warning",
            available=True,
            details="FFmpeg found, but missing libass or libx264 compilation flags",
            recommendation="Install standard Gyan.dev essentials FFmpeg build",
        )
    except Exception as exc:
        return CapabilityCheck(
            name="FFmpeg Media Toolchain",
            category="tool",
            status="error",
            available=False,
            details=f"FFmpeg not executable in PATH: {exc}",
            recommendation="Install FFmpeg and add it to system PATH",
        )


def check_audio_studio_engines() -> CapabilityCheck:
    """Verify Audio Studio procedural sound generators and providers."""
    try:
        from engine.api.routers.audio_studio import get_engine

        engine = get_engine()
        names = [p.name for p in engine.providers]
        required = {"foley", "ambient", "synth"}
        missing = required - set(names)

        if not missing:
            return CapabilityCheck(
                name="Audio Studio Sound Engines",
                category="audio",
                status="ok",
                available=True,
                details=f"Active providers: {', '.join(names)}",
            )
        return CapabilityCheck(
            name="Audio Studio Sound Engines",
            category="audio",
            status="warning",
            available=True,
            details=f"Missing sound providers: {missing}",
        )
    except Exception as exc:
        return CapabilityCheck(
            name="Audio Studio Sound Engines",
            category="audio",
            status="error",
            available=False,
            details=f"AudioEngine initialization failed: {exc}",
        )


def check_reels_autocut_pipeline() -> CapabilityCheck:
    """Verify 9:16 Shorts/Reels reframing and karaoke subtitle engine."""
    try:
        from engine.reels.reframer import compute_reframing_plan
        from engine.reels.subtitles import build_karaoke_ass
        from engine.reels.publisher import autocut_horizontal_to_reel

        # Dry test of ASS generation
        ass = build_karaoke_ass([], hook="TEST")
        if "PlayResY: 1920" in ass:
            return CapabilityCheck(
                name="Shorts & Reels 9:16 Auto-Cut",
                category="tool",
                status="ok",
                available=True,
                details="Focal reframer, ASS karaoke compiler, and mastering pipeline operational",
            )
        return CapabilityCheck(
            name="Shorts & Reels 9:16 Auto-Cut",
            category="tool",
            status="warning",
            available=False,
            details="ASS karaoke formatting returned unexpected output",
        )
    except Exception as exc:
        return CapabilityCheck(
            name="Shorts & Reels 9:16 Auto-Cut",
            category="tool",
            status="error",
            available=False,
            details=f"Reels auto-cut modules failed import: {exc}",
        )


def check_system_resources() -> CapabilityCheck:
    """Check host RAM and working drive disk space."""
    try:
        cwd = Path.cwd()
        total, used, free = shutil.disk_usage(cwd)
        free_gb = round(free / (1024**3), 1)

        import psutil
        ram = psutil.virtual_memory()
        ram_free_gb = round(ram.available / (1024**3), 1)

        details = f"Disk: {free_gb} GB free on {cwd.drive or '/'}; RAM: {ram_free_gb} GB available"
        if free_gb < 15.0:
            return CapabilityCheck(
                name="Host System Resources",
                category="hardware",
                status="warning",
                available=True,
                details=details,
                recommendation="Low disk space on working volume (< 15 GB). Clear cache.",
            )
        return CapabilityCheck(
            name="Host System Resources",
            category="hardware",
            status="ok",
            available=True,
            details=details,
        )
    except Exception as exc:
        return CapabilityCheck(
            name="Host System Resources",
            category="hardware",
            status="warning",
            available=True,
            details=f"Could not read disk/RAM stats: {exc}",
        )


def check_production_readiness() -> ProductionReadinessReport:
    """Run all preflight health and capability checks."""
    checks: dict[str, CapabilityCheck] = {}

    checks["ollama"] = check_ollama()
    checks["comfyui"] = check_comfyui()
    checks["workflows"] = check_comfyui_workflows()
    checks["insightface"] = check_insightface_models()
    checks["ffmpeg"] = check_ffmpeg()
    checks["audio_studio"] = check_audio_studio_engines()
    checks["reels"] = check_reels_autocut_pipeline()
    checks["resources"] = check_system_resources()

    errors = [c for c in checks.values() if c.status == "error"]
    warnings = [c for c in checks.values() if c.status == "warning"]

    # Ready means core tools (FFmpeg, Audio Studio, Reels, Workflows) are operable
    is_ready = len(errors) == 0
    all_ok = is_ready and len(warnings) == 0

    recs = [c.recommendation for c in checks.values() if c.recommendation]

    if all_ok:
        summary = "All systems and production pipelines are fully operational and ready."
    elif is_ready:
        summary = f"Core production pipelines are operational with {len(warnings)} non-critical advisory warning(s)."
    else:
        summary = f"System has {len(errors)} critical blocker(s) requiring attention."

    return ProductionReadinessReport(
        ready=is_ready,
        all_ok=all_ok,
        checks=checks,
        summary=summary,
        recommendations=recs,
    )
