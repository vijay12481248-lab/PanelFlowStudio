import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from uuid import uuid4
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.config.settings import settings
from engine.database.session import get_db
from engine.projects.service import project_service

router = APIRouter(prefix="/api/system", tags=["system"])
engine_instance_id = uuid4().hex

class BrowseRequest(BaseModel):
    path: str | None = None
    show_files: bool = True
    extensions: list[str] | None = None

@router.get("/health")
def health_check():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.version,
        "instance_id": engine_instance_id,
        "workspace_root": str(settings.workspace_root),
    }


@router.post("/restart", status_code=202)
def restart_engine(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from engine.database.models import JobRecord, RenderJobRecord
    if not request.client or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Engine restart is available only from this computer.")
    if request.headers.get("x-panelflow-control") != "restart":
        raise HTTPException(403, "Missing engine control header.")
    restart = getattr(request.app.state, "request_restart", None)
    if restart is None:
        raise HTTPException(409, "Restart support requires launching the engine with the updated run_engine.py or launcher first.")
    if getattr(request.app.state, "restarting", False):
        raise HTTPException(409, "Engine restart is already in progress.")
    busy = db.query(JobRecord).filter(JobRecord.status.in_(["QUEUED", "RUNNING"])).first()
    render_busy = db.query(RenderJobRecord).filter(RenderJobRecord.status.in_([
        "QUEUED", "RUNNING", "PREPARING", "COMPOSING", "ENCODING", "MUXING", "VALIDATING",
    ])).first()
    if busy or render_busy:
        raise HTTPException(409, "Finish or cancel queued and running jobs before restarting the engine.")
    request.app.state.restarting = True
    background_tasks.add_task(restart)
    return {"status": "restarting", "instance_id": engine_instance_id}

@router.post("/browse")
def browse_filesystem(req: BrowseRequest):
    target_path = Path(req.path).resolve() if req.path else Path.home()
    if not target_path.exists() or not target_path.is_dir():
        target_path = Path.home()

    entries = []
    try:
        for item in sorted(target_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name.startswith((".", "$")):
                continue
            is_dir = item.is_dir()
            if not is_dir and not req.show_files:
                continue
            if not is_dir and req.extensions:
                if item.suffix.lower() not in [e.lower() for e in req.extensions]:
                    continue
            entries.append({
                "name": item.name,
                "path": str(item.resolve()),
                "is_dir": is_dir,
                "size": item.stat().st_size if not is_dir else 0,
            })
    except PermissionError:
        pass

    parent_path = str(target_path.parent.resolve()) if target_path.parent != target_path else None
    return {
        "current_path": str(target_path),
        "parent_path": parent_path,
        "entries": entries,
    }

@router.post("/projects/{project_id}/open-folder")
def open_project_folder(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    folder_path = Path(proj.workspace_path)
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Workspace directory does not exist on disk")

    try:
        if sys.platform == "win32":
            os.startfile(str(folder_path))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder_path)], check=True)
        else:
            subprocess.run(["xdg-open", str(folder_path)], check=True)
        return {"opened": True, "path": str(folder_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {e}")


class OpenPathRequest(BaseModel):
    path: str
    select_file: bool = False


@router.post("/open-path")
def open_system_path(req: OpenPathRequest):
    p = Path(req.path).resolve()
    if not p.exists():
        raise HTTPException(status_code=404, detail="Target path does not exist on disk")

    try:
        if sys.platform == "win32":
            if req.select_file and p.is_file():
                subprocess.run(["explorer.exe", f"/select,{str(p)}"], check=False)
            else:
                target = str(p if p.is_dir() else p.parent)
                os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R" if (req.select_file and p.is_file()) else "", str(p)], check=True)
        else:
            subprocess.run(["xdg-open", str(p if p.is_dir() else p.parent)], check=True)
        return {"opened": True, "path": str(p)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to open path: {e}")


@router.get("/providers")
def get_providers_status():
    """
    Probes all local engine dependencies and returns structured health details.
    """
    import shutil
    import urllib.request
    import json
    from engine.system.setup import locate_and_configure_ffmpeg, get_voice_reference_dir

    # Automatically locate FFmpeg if missing from PATH
    ffmpeg_info = locate_and_configure_ffmpeg()

    results = []

    # 1. FFmpeg
    ffmpeg_bin = ffmpeg_info.get("ffmpeg_path") or shutil.which("ffmpeg")
    ffmpeg_version = ffmpeg_info.get("version") or "Unknown"
    if ffmpeg_bin and ffmpeg_version == "Unknown":
        try:
            out = subprocess.check_output([ffmpeg_bin, "-version"], stderr=subprocess.STDOUT, text=True, timeout=2.0)
            ffmpeg_version = out.splitlines()[0] if out else "Found"
        except Exception:
            ffmpeg_version = "Available"

    results.append({
        "id": "ffmpeg",
        "name": "FFmpeg Video Encoder",
        "category": "video_engine",
        "status": "HEALTHY" if ffmpeg_bin else "MISSING",
        "version": ffmpeg_version,
        "path": ffmpeg_bin or "",
        "required": True,
        "details": "Hardware-accelerated and software libx264/aac video rendering pipeline.",
    })

    # 2. FFprobe
    ffprobe_bin = shutil.which("ffprobe")
    ffprobe_version = "Unknown"
    if ffprobe_bin:
        try:
            out = subprocess.check_output([ffprobe_bin, "-version"], stderr=subprocess.STDOUT, text=True, timeout=2.0)
            ffprobe_version = out.splitlines()[0] if out else "Found"
        except Exception:
            ffprobe_version = "Available"

    results.append({
        "id": "ffprobe",
        "name": "FFprobe Media Inspector",
        "category": "video_engine",
        "status": "HEALTHY" if ffprobe_bin else "MISSING",
        "version": ffprobe_version,
        "path": ffprobe_bin or "",
        "required": True,
        "details": "Audio/video stream validation, metadata inspection, and timing verification.",
    })

    # 3. Ollama LLM
    ollama_status = "NOT_RUNNING"
    ollama_models = []
    try:
        req = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1.0)
        models_data = json.loads(req.read().decode())
        ollama_models = [m.get("name", "") for m in models_data.get("models", [])]
        ollama_status = "HEALTHY" if ollama_models else "DEGRADED"
    except Exception:
        ollama_status = "OFFLINE"

    results.append({
        "id": "ollama",
        "name": "Ollama Local LLM",
        "category": "story_intelligence",
        "status": ollama_status,
        "version": f"{len(ollama_models)} models loaded" if ollama_models else "Unavailable",
        "path": "http://127.0.0.1:11434",
        "required": False,
        "details": f"Local story comprehension, speaker attribution, and scriptwriting ({', '.join(ollama_models[:3]) if ollama_models else 'no models'}).",
    })

    # 3b. Cloud / Free LLM API Gateway (OpenRouter, Groq, Custom)
    from engine.llm.registry import llm_registry
    cloud_cfg = llm_registry.get_cloud_config()
    has_cloud_key = bool(cloud_cfg.get("api_key", "").strip())
    cloud_ptype = cloud_cfg.get("provider_type", "openrouter").capitalize()
    cloud_model = cloud_cfg.get("model_name", "meta-llama/llama-3.3-70b-instruct:free")
    results.append({
        "id": "cloud_llm",
        "name": f"Cloud & Free LLMs ({cloud_ptype})",
        "category": "story_intelligence",
        "status": "HEALTHY" if has_cloud_key else "READY",
        "version": cloud_model,
        "path": cloud_cfg.get("endpoint_url", "https://openrouter.ai/api/v1"),
        "required": False,
        "details": f"Cloud narrative intelligence & vision via {cloud_ptype} ({'API Key configured' if has_cloud_key else 'Configurable in Cloud LLM tab'}).",
    })

    # 4. Chatterbox Turbo Neural Voice (MIT Permissive Commercial)
    chatterbox_venv = Path(r"C:\Tools\Chatterbox\.venv\Scripts\python.exe")
    chatterbox_hf = Path.home() / ".cache" / "huggingface" / "hub" / "models--ResembleAI--chatterbox-turbo"
    voice_refs = get_voice_reference_dir()
    has_voices = voice_refs.exists() and len(list(voice_refs.glob("*.*"))) > 0

    if chatterbox_venv.exists() and chatterbox_hf.exists():
        cb_status = "HEALTHY"
        cb_version = "Chatterbox Turbo (MIT Commercial, Resemble AI on CUDA)"
        cb_path = str(chatterbox_venv)
        cb_details = f"Commercial-ready zero-shot neural voice cloning with {len(list(voice_refs.glob('*.*')))} voice profiles."
    elif chatterbox_venv.exists():
        cb_status = "READY"
        cb_version = "Chatterbox Turbo Runtime"
        cb_path = str(chatterbox_venv)
        cb_details = "Local PyTorch inference runtime ready for commercial voice synthesis."
    else:
        cb_status = "READY" if has_voices else "DEGRADED"
        cb_version = "Procedural Synthesizer Active"
        cb_path = str(voice_refs)
        cb_details = f"Procedural voice synthesizer active with {len(list(voice_refs.glob('*.*')))} voice reference profiles."

    results.append({
        "id": "chatterbox_turbo",
        "name": "Chatterbox Turbo Neural Voice (MIT)",
        "category": "audio_engine",
        "status": cb_status,
        "version": cb_version,
        "path": cb_path,
        "required": False,
        "details": cb_details,
    })

    # 4b. F5-TTS Neural Voice
    f5_pool = Path(r"C:\Tools\generated_audio\marcus_male_deep")
    f5_files = list(f5_pool.glob("*.wav")) if f5_pool.exists() else []
    f5_status = "HEALTHY" if (f5_pool.exists() and len(f5_files) > 0) else "DEGRADED"

    results.append({
        "id": "f5_tts",
        "name": "F5-TTS Neural Voice",
        "category": "audio_engine",
        "status": f5_status,
        "version": f"{len(f5_files)} cached takes" if f5_files else "Procedural fallback",
        "path": str(f5_pool),
        "required": False,
        "details": "High-fidelity neural dialogue synthesis with zero-shot emotion and natural breathiness.",
    })

    # 5. ACE-Step
    ace_api_url = "http://127.0.0.1:8001"
    ace_status = "STOPPED"
    ace_version = "Offline"
    ace_path = ""
    ace_details = "Adaptive crystal score generator rooted in D Dorian cinematic soundscape."
    try:
        req = urllib.request.urlopen(f"{ace_api_url}/health", timeout=1.0)
        ace_data = json.loads(req.read().decode())
        if ace_data.get("code") == 200 or ace_data.get("data", {}).get("status") == "ok":
            ace_status = "READY"
            loaded = ace_data.get("data", {}).get("loaded_model", "acestep-v15-turbo")
            ace_version = f"ACE-Step 1.5 REST API ({loaded} on CUDA)"
            ace_path = ace_api_url
            ace_details = "Real-time neural music generation server active on port 8001."
    except Exception:
        ace_dir = Path(r"C:\Tools\ACE-Step-1.5")
        if ace_dir.exists():
            ace_status = "STOPPED"
            ace_version = "Installed (Service Offline, Procedural Synthesizer active)"
            ace_path = str(ace_dir)
            ace_details = "ACE-Step API service is stopped. Procedural synthesizer active; start via start_api_server.bat."
        else:
            ace_status = "DEGRADED"
            ace_version = "Procedural Synthesizer Fallback (D-Minor Master 48kHz)"
            ace_details = "Procedural crystal score synthesizer active in D Dorian."

    results.append({
        "id": "ace_step",
        "name": "ACE-Step Music Director",
        "category": "audio_engine",
        "status": ace_status,
        "version": ace_version,
        "path": ace_path,
        "required": False,
        "details": ace_details,
    })

    # 6. Playwright
    pw_status = "MISSING"
    pw_version = "None"
    try:
        import playwright
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True)
            pw_version = b.version
            b.close()
            pw_status = "HEALTHY"
    except Exception as e:
        pw_status = "BROWSER_RUNTIME_MISSING"
        pw_version = "CLI Available, Browser Binaries Required"

    results.append({
        "id": "playwright",
        "name": "Playwright Reader Engine",
        "category": "acquisition_engine",
        "status": pw_status,
        "version": pw_version,
        "path": "playwright/chromium",
        "required": False,
        "details": "Dynamic single-page application reader crawler and DOM visual extraction.",
    })

    return {
        "providers": results,
        "system_ready": ffmpeg_bin is not None and ffprobe_bin is not None,
    }


@router.get("/hardware")
def get_hardware_diagnostics():
    """
    Returns user-readable hardware diagnostics and neural audio performance tier.
    """
    import platform
    import shutil
    import psutil
    from datetime import datetime, timezone

    total_ram_gb = round(psutil.virtual_memory().total / (1024**3), 1)
    available_ram_gb = round(psutil.virtual_memory().available / (1024**3), 1)

    target_disk = settings.app_data_dir if settings.app_data_dir.exists() else Path.home()
    usage = shutil.disk_usage(target_disk)
    total_disk_gb = round(usage.total / (1024**3), 1)
    free_disk_gb = round(usage.free / (1024**3), 1)

    gpu_name = "CPU Only"
    vram_mb = 0
    cuda_available = False

    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.check_output(
                [smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                text=True,
                timeout=2.0,
            )
            parts = [p.strip() for p in out.strip().split(",")]
            if parts:
                gpu_name = parts[0]
                if len(parts) > 1 and "MiB" in parts[1]:
                    vram_mb = int(parts[1].replace("MiB", "").strip())
                cuda_available = True
        except Exception:
            pass

    # Check FFmpeg hardware acceleration support
    ffmpeg_bin = shutil.which("ffmpeg")
    ffmpeg_hwaccels = []
    if ffmpeg_bin:
        try:
            hw_out = subprocess.check_output([ffmpeg_bin, "-hwaccels"], text=True, timeout=2.0)
            ffmpeg_hwaccels = [line.strip() for line in hw_out.splitlines()[1:] if line.strip()]
        except Exception:
            pass

    # Determine neural audio performance tier
    if (cuda_available and vram_mb >= 6000 and total_ram_gb >= 16) or (total_ram_gb >= 32):
        tier = "GOOD"
        rec = "Excellent specifications for real-time F5-TTS neural voice synthesis and 1080p video composition."
    elif total_ram_gb >= 12 or (cuda_available and vram_mb >= 4000):
        tier = "SUPPORTED"
        rec = "Supported configuration. Neural dialogue generation and video encoding will execute smoothly."
    elif total_ram_gb >= 8:
        tier = "LIMITED"
        rec = "Limited specifications. CPU synthesis fallback will be utilized; render times may be slower."
    else:
        tier = "UNSUPPORTED"
        rec = "Below minimum recommended requirements (<8 GB RAM). Video rendering or neural models may exhaust memory."

    return {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count() or 1,
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": available_ram_gb,
        "total_disk_gb": total_disk_gb,
        "free_disk_gb": free_disk_gb,
        "gpu_name": gpu_name,
        "vram_mb": vram_mb,
        "cuda_available": cuda_available,
        "ffmpeg_available": ffmpeg_bin is not None,
        "ffmpeg_hwaccels": ffmpeg_hwaccels[:4],
        "neural_performance_tier": tier,
        "recommendations": rec,
    }


@router.get("/diagnostics")
def export_sanitized_diagnostics(db: Session = Depends(get_db)):
    """
    Generates a privacy-preserving sanitized diagnostic bundle for beta issue reporting.
    Excludes all user files, full comic images, tokens, and passwords.
    """
    from datetime import datetime, timezone
    from engine.database.models import ProjectRecord, RenderJobRecord

    hw = get_hardware_diagnostics()
    providers = get_providers_status()

    total_projects = db.query(ProjectRecord).count()
    total_renders = db.query(RenderJobRecord).count()
    failed_renders = db.query(RenderJobRecord).filter(RenderJobRecord.status == "FAILED").count()

    recent_failures = (
        db.query(RenderJobRecord)
        .filter(RenderJobRecord.status == "FAILED")
        .order_by(RenderJobRecord.created_at.desc())
        .limit(5)
        .all()
    )

    sanitized_issues = []
    for r in recent_failures:
        sanitized_issues.append({
            "job_id": r.id,
            "error_code": r.error_code,
            "error_message": r.error_message,
            "stage": r.current_stage,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "panelflow_version": settings.version,
        "diagnostic_schema": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hardware": {
            "os": f"{hw['os_name']} {hw['os_release']} ({hw['architecture']})",
            "cpu_cores": hw["cpu_count"],
            "total_ram_gb": hw["total_ram_gb"],
            "free_disk_gb": hw["free_disk_gb"],
            "gpu": hw["gpu_name"],
            "vram_mb": hw["vram_mb"],
            "tier": hw["neural_performance_tier"],
        },
        "providers": [
            {
                "id": p["id"],
                "name": p["name"],
                "status": p["status"],
                "version": p["version"],
                "required": p["required"],
            }
            for p in providers.get("providers", [])
        ],
        "system_metrics": {
            "total_projects": total_projects,
            "total_renders": total_renders,
            "failed_renders": failed_renders,
        },
        "recent_job_failures": sanitized_issues,
        "privacy_notice": "This diagnostic export contains only hardware specifications and error codes. No personal files, images, or source content are included.",
    }


# ---------------------------------------------------------------------------
# Ollama Multi-Role Configuration & Official REST API Endpoints
# ---------------------------------------------------------------------------

class OllamaConfigRequest(BaseModel):
    endpoint_url: str = "http://127.0.0.1:11434"
    is_remote: bool = False
    auth_token: str | None = None
    vision_model: str = "qwen3.5:9b"
    reasoning_model: str = "qwen3.5:9b"
    narration_model: str = "qwen3.5:9b"
    num_ctx: int = 32768
    concurrency_mode: str = "MANUAL"
    max_gpu_concurrency: int = 1
    approved_remote_ips: list[str] | None = None


class OllamaTestRequest(BaseModel):
    endpoint_url: str | None = None
    is_remote: bool = False
    auth_token: str | None = None


class ConcurrencyRequest(BaseModel):
    concurrency_mode: str = "MANUAL"
    max_gpu_concurrency: int = 1


class BenchmarkRequest(BaseModel):
    model: str | None = None


@router.get("/ollama/config")
def get_ollama_config():
    """
    Returns sanitized Ollama configuration.
    Tokens are never revealed in network responses or logs.
    """
    from engine.llm.registry import llm_registry
    prov = llm_registry.get_ollama_provider()
    return {
        "endpoint_url": prov.endpoint_url,
        "is_remote": prov.is_remote,
        "has_auth_token": bool(prov.auth_token and prov.auth_token.strip()),
        "vision_model": prov.vision_model,
        "reasoning_model": prov.reasoning_model,
        "narration_model": prov.narration_model,
        "num_ctx": prov.num_ctx,
        "concurrency_mode": prov.concurrency_mode,
        "max_gpu_concurrency": prov.max_gpu_concurrency,
        "approved_remote_ips": sorted(prov.remote_authorization.approved_remote_ips),
        "authorization_identity": prov.remote_authorization.identity,
    }


@router.post("/ollama/config")
def save_ollama_config(req: OllamaConfigRequest):
    """
    Validates and updates Ollama configuration.
    Enforces SSRF prevention on endpoint URLs.
    """
    from engine.llm.registry import llm_registry
    from engine.llm.providers.ollama import (
        OllamaEndpointAuthorization,
        persist_ollama_endpoint_authorization,
        validate_ollama_endpoint,
    )
    from engine.system.resources import resource_manager

    current_prov = llm_registry.get_ollama_provider()
    try:
        authorization = (
            OllamaEndpointAuthorization.create(req.approved_remote_ips)
            if req.approved_remote_ips is not None
            else current_prov.remote_authorization
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    valid, err_msg = validate_ollama_endpoint(
        req.endpoint_url,
        req.is_remote,
        authorization=authorization,
    )
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid Ollama endpoint: {err_msg}")

    # If auth_token is not provided, preserve current token
    final_token = req.auth_token if req.auth_token is not None else current_prov.auth_token

    persist_ollama_endpoint_authorization(authorization)
    updated_prov = llm_registry.configure_ollama(
        endpoint_url=req.endpoint_url,
        is_remote=req.is_remote,
        auth_token=final_token,
        vision_model=req.vision_model,
        reasoning_model=req.reasoning_model,
        narration_model=req.narration_model,
        num_ctx=req.num_ctx,
        concurrency_mode=req.concurrency_mode,
        max_gpu_concurrency=req.max_gpu_concurrency,
    )

    resource_manager.set_concurrency(req.concurrency_mode, req.max_gpu_concurrency)

    return {
        "status": "SAVED",
        "endpoint_url": updated_prov.endpoint_url,
        "is_remote": updated_prov.is_remote,
        "has_auth_token": bool(updated_prov.auth_token and updated_prov.auth_token.strip()),
        "vision_model": updated_prov.vision_model,
        "reasoning_model": updated_prov.reasoning_model,
        "narration_model": updated_prov.narration_model,
        "num_ctx": updated_prov.num_ctx,
        "concurrency_mode": updated_prov.concurrency_mode,
        "max_gpu_concurrency": updated_prov.max_gpu_concurrency,
        "approved_remote_ips": sorted(updated_prov.remote_authorization.approved_remote_ips),
        "authorization_identity": updated_prov.remote_authorization.identity,
    }


@router.get("/ollama/models")
async def list_ollama_models_with_capabilities():
    """
    Discovers installed models via /api/tags and queries /api/show for
    actual architectural capabilities (vision, tools, thinking).
    """
    from engine.llm.registry import llm_registry
    prov = llm_registry.get_ollama_provider()
    models = await prov.discover_models_with_capabilities()
    recommendations = prov.recommend_models(models)
    return {
        "models": models,
        "recommendations": recommendations,
        "endpoint_url": prov.endpoint_url,
        "is_remote": prov.is_remote,
        "healthy": len(models) > 0,
    }


@router.post("/ollama/test")
async def test_ollama_connection(req: OllamaTestRequest):
    """
    Tests connection to target Ollama endpoint with timing,
    evaluating health and installed model inventory.
    """
    import time
    from engine.llm.registry import llm_registry
    from engine.llm.providers.ollama import OllamaProvider, validate_ollama_endpoint

    current_prov = llm_registry.get_ollama_provider()
    target_url = req.endpoint_url or current_prov.endpoint_url
    is_remote = req.is_remote if req.endpoint_url else current_prov.is_remote
    auth_token = req.auth_token if req.auth_token is not None else current_prov.auth_token

    valid, err_msg = validate_ollama_endpoint(
        target_url,
        is_remote,
        authorization=current_prov.remote_authorization,
    )
    if not valid:
        return {
            "status": "ERROR",
            "connected": False,
            "error": f"SSRF Check Rejected: {err_msg}",
            "latency_ms": 0.0,
            "models": [],
        }

    test_provider = OllamaProvider(
        endpoint_url=target_url,
        is_remote=is_remote,
        auth_token=auth_token,
        timeout=5.0,
    )

    t0 = time.perf_counter()
    healthy = await test_provider.health_check()
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    if not healthy:
        return {
            "status": "OFFLINE",
            "connected": False,
            "error": f"Could not reach Ollama server at {target_url}",
            "latency_ms": elapsed_ms,
            "models": [],
        }

    models = await test_provider.list_available_models()
    return {
        "status": "HEALTHY",
        "connected": True,
        "latency_ms": elapsed_ms,
        "models_count": len(models),
        "models": models,
    }


# ---------------------------------------------------------------------------
# Hardware Resource Telemetry & GPU Concurrency Endpoints
# ---------------------------------------------------------------------------

@router.get("/resources")
async def get_system_resources():
    """
    Returns real-time telemetry: host RAM, GPU VRAM (via nvidia-smi / PyTorch),
    active Ollama runtime memory (/api/ps), and admission queue status.
    """
    from engine.system.resources import resource_manager
    from engine.llm.registry import llm_registry

    prov = llm_registry.get_ollama_provider()
    telemetry = await resource_manager.get_full_telemetry(
        ollama_endpoint=prov.endpoint_url,
        auth_token=prov.auth_token,
        authorization=prov.remote_authorization,
    )
    return telemetry


@router.post("/concurrency")
def set_concurrency_settings(req: ConcurrencyRequest):
    """
    Configures GPU admission control mode (AUTO or MANUAL) and max concurrency.
    """
    from engine.system.resources import resource_manager
    from engine.llm.registry import llm_registry

    res = resource_manager.set_concurrency(req.concurrency_mode, req.max_gpu_concurrency)
    prov = llm_registry.get_ollama_provider()
    prov.concurrency_mode = res["concurrency_mode"]
    prov.max_gpu_concurrency = res["max_gpu_concurrency"]

    return {
        "status": "UPDATED",
        "concurrency_mode": prov.concurrency_mode,
        "max_gpu_concurrency": prov.max_gpu_concurrency,
    }


@router.post("/benchmark")
async def run_concurrency_benchmark(req: BenchmarkRequest):
    """
    Executes sequential vs 2-request concurrent performance benchmark under real workload.
    """
    from engine.system.resources import resource_manager
    from engine.llm.registry import llm_registry

    prov = llm_registry.get_ollama_provider()
    target_model = req.model or prov.narration_model or "qwen3.5:9b"

    results = await resource_manager.benchmark_concurrency(
        endpoint_url=prov.endpoint_url,
        model=target_model,
        auth_token=prov.auth_token,
        authorization=prov.remote_authorization,
    )
    return results


# ---------------------------------------------------------------------------
# Setup & Dependency Provisioning Endpoints
# ---------------------------------------------------------------------------

class OllamaPullRequest(BaseModel):
    model: str = "qwen2.5:7b"
    endpoint_url: Optional[str] = None


@router.post("/locate-ffmpeg")
def api_locate_ffmpeg():
    """
    Scans host filesystem for FFmpeg and FFprobe binaries and auto-configures PATH.
    """
    from engine.system.setup import locate_and_configure_ffmpeg
    return locate_and_configure_ffmpeg()


@router.post("/provision-voices")
def api_provision_voices():
    """
    Deploys bundled default voice reference profiles to AppData voice directory.
    """
    from engine.system.setup import provision_default_voices
    return provision_default_voices()


@router.post("/install-playwright")
def api_start_playwright_install():
    """
    Spawns background installation of Playwright Chromium browser binaries.
    """
    from engine.system.setup import playwright_installer
    return playwright_installer.start_install()


@router.get("/install-playwright/status")
def api_get_playwright_install_status():
    """
    Returns live progress and logs for Playwright browser installation.
    """
    from engine.system.setup import playwright_installer
    return playwright_installer.get_status()


@router.post("/ollama/pull")
async def api_start_ollama_pull(req: OllamaPullRequest):
    """
    Initiates asynchronous download of target LLM model in local or remote Ollama.
    """
    from engine.system.setup import ollama_pull_manager
    from engine.llm.registry import llm_registry
    from engine.llm.providers.ollama import validate_ollama_endpoint

    prov = llm_registry.get_ollama_provider()
    target_url = req.endpoint_url or prov.endpoint_url
    valid, err_msg = validate_ollama_endpoint(target_url, prov.is_remote)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid Ollama endpoint: {err_msg}")

    return await ollama_pull_manager.start_pull(req.model, target_url)


@router.get("/ollama/pull/status")
def api_get_ollama_pull_status():
    """
    Returns live progress, percentage, and bytes for active Ollama model download.
    """
    from engine.system.setup import ollama_pull_manager
    return ollama_pull_manager.get_status()


# =====================================================================
# Cloud & Free LLM API Gateway Endpoints (OpenRouter, Groq, Custom)
# =====================================================================

class CloudLLMConfigRequest(BaseModel):
    provider_type: str = "openrouter"  # openrouter, groq, custom_openai
    endpoint_url: str = "https://openrouter.ai/api/v1"
    api_key: Optional[str] = None
    model_name: str = "meta-llama/llama-3.3-70b-instruct:free"
    custom_models: Optional[list[str]] = None
    is_active: bool = True


class CloudLLMTestRequest(BaseModel):
    endpoint_url: str
    api_key: Optional[str] = None
    model_name: Optional[str] = None


class CloudLLMChatRequest(BaseModel):
    prompt: str
    model_name: Optional[str] = None
    system_prompt: Optional[str] = None


class FlowOverridePayload(BaseModel):
    provider_id: str = "global"
    model_name: Optional[str] = ""


class GlobalLLMSettingsRequest(BaseModel):
    global_default_provider: str = "ollama"
    global_default_model: str = "qwen3.5:9b"
    flow_overrides: Optional[Dict[str, FlowOverridePayload]] = None


@router.get("/llm/cloud-config")
def get_cloud_llm_config():
    """
    Returns sanitized Cloud / Free LLM configuration.
    Tokens are never revealed in network responses or logs.
    """
    from engine.llm.registry import llm_registry
    cfg = llm_registry.get_cloud_config()
    api_key = cfg.get("api_key", "")
    has_key = bool(api_key and api_key.strip())
    masked_key = (api_key[:4] + "••••" + api_key[-4:]) if len(api_key) >= 12 else ("••••" if has_key else "")
    return {
        "provider_type": cfg.get("provider_type", "openrouter"),
        "endpoint_url": cfg.get("endpoint_url", "https://openrouter.ai/api/v1"),
        "has_api_key": has_key,
        "masked_api_key": masked_key,
        "model_name": cfg.get("model_name", "meta-llama/llama-3.3-70b-instruct:free"),
        "custom_models": cfg.get("custom_models", []),
        "is_active": cfg.get("is_active", False),
    }


@router.post("/llm/cloud-config")
def save_cloud_llm_config(req: CloudLLMConfigRequest):
    """
    Validates and persists Cloud / Free LLM configuration.
    Enables instant switching to free cloud models (OpenRouter, Groq, etc.).
    """
    from engine.llm.registry import llm_registry
    current_cfg = llm_registry.get_cloud_config()

    key = req.api_key
    if key is None or "••••" in key:
        key = current_cfg.get("api_key", "")

    provider = llm_registry.configure_cloud_provider(
        endpoint_url=req.endpoint_url,
        api_key=key,
        model_name=req.model_name,
        provider_type=req.provider_type,
        custom_models=req.custom_models,
        is_active=req.is_active,
    )

    has_key = bool(key and key.strip())
    masked_key = (key[:4] + "••••" + key[-4:]) if len(key) >= 12 else ("••••" if has_key else "")
    return {
        "status": "SAVED",
        "provider_type": req.provider_type,
        "endpoint_url": req.endpoint_url,
        "has_api_key": has_key,
        "masked_api_key": masked_key,
        "model_name": req.model_name,
        "custom_models": req.custom_models or current_cfg.get("custom_models", []),
        "is_active": req.is_active,
    }


@router.post("/llm/cloud-test")
async def test_cloud_llm_connection(req: CloudLLMTestRequest):
    """
    Tests live latency and verifies model inventory for the Cloud / Free LLM API.
    """
    import time
    from engine.llm.registry import llm_registry
    from engine.llm.providers.openai_compatible import OpenAICompatibleProvider

    current_cfg = llm_registry.get_cloud_config()
    key = req.api_key
    if not key or "••••" in key:
        key = current_cfg.get("api_key", "")

    test_prov = OpenAICompatibleProvider(
        endpoint_url=req.endpoint_url,
        api_key=key,
        model_name=req.model_name or "default",
    )

    t0 = time.time()
    try:
        models = await test_prov.list_available_models()
        latency_ms = round((time.time() - t0) * 1000, 1)
        endpoint_healthy = len(models) > 0 or await test_prov.health_check()
        if not endpoint_healthy:
            return {
                "status": "DEGRADED",
                "connected": False,
                "latency_ms": latency_ms,
                "models_count": len(models),
                "models": models[:50],
                "model_verified": False,
                "response_preview": None,
                "error": "The endpoint did not return a usable /models response.",
            }

        selected_model = req.model_name or (models[0] if models else "default")
        response = await test_prov.generate_text(
            "Reply with exactly: PANELFLOW_OK",
            system_prompt="You are a connection test. Follow the requested output exactly.",
            max_tokens=12,
            model=selected_model,
        )
        latency_ms = round((time.time() - t0) * 1000, 1)
        model_verified = bool(response and response.strip())
        return {
            "status": "HEALTHY" if model_verified else "DEGRADED",
            "connected": model_verified,
            "latency_ms": latency_ms,
            "models_count": len(models),
            "models": models[:50],
            "model_verified": model_verified,
            "response_preview": response.strip()[:120] if response else None,
            "error": None if model_verified else f"The endpoint is reachable, but model '{selected_model}' returned no text.",
        }
    except Exception as e:
        latency_ms = round((time.time() - t0) * 1000, 1)
        return {
            "status": "ERROR",
            "connected": False,
            "latency_ms": latency_ms,
            "models_count": 0,
            "models": [],
            "model_verified": False,
            "response_preview": None,
            "error": str(e),
        }


@router.post("/llm/cloud-chat")
async def chat_with_cloud_llm(req: CloudLLMChatRequest):
    """Send a real prompt through the saved active cloud/gateway provider."""
    import time
    from engine.llm.registry import llm_registry

    prompt = req.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    cfg = llm_registry.get_cloud_config()
    if not cfg.get("is_active", False):
        raise HTTPException(status_code=409, detail="No active cloud or gateway provider is configured")

    provider = llm_registry.get_cloud_provider()
    if provider is None:
        llm_registry.load_persisted_cloud_provider()
        provider = llm_registry.get_cloud_provider()
    if provider is None:
        raise HTTPException(status_code=409, detail="The configured provider is not loaded; restart the engine")

    model_name = req.model_name or cfg.get("model_name") or provider.model_name
    started = time.time()
    try:
        response = await provider.generate_text(
            prompt,
            system_prompt=req.system_prompt or "You are a concise assistant testing PanelFlow's configured LLM provider.",
            max_tokens=1024,
            model=model_name,
        )
        return {
            "status": "OK",
            "provider_type": cfg.get("provider_type", "custom"),
            "model_name": model_name,
            "response": response,
            "latency_ms": round((time.time() - started) * 1000, 1),
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "provider_type": cfg.get("provider_type", "custom"),
            "model_name": model_name,
            "response": "",
            "latency_ms": round((time.time() - started) * 1000, 1),
            "error": str(exc),
        }
@router.get("/llm/providers/all")
async def get_all_available_llm_providers():
    """
    Returns all registered LLM providers (Local Ollama and Cloud / Free LLM)
    and their selectable models for UI dropdowns in Narration Studio.
    """
    from engine.llm.registry import llm_registry
    ollama_prov = llm_registry.get_ollama_provider()
    cloud_cfg = llm_registry.get_cloud_config()

    ollama_models = []
    try:
        ollama_models = await ollama_prov.list_available_models()
    except Exception:
        pass

    cloud_models = list(cloud_cfg.get("custom_models", []))
    if cloud_cfg.get("model_name") and cloud_cfg.get("model_name") not in cloud_models:
        cloud_models = [cloud_cfg["model_name"]] + cloud_models

    return {
        "providers": [
            {
                "id": "ollama",
                "name": "Local Ollama (Offline GPU/CPU)",
                "type": "local",
                "endpoint": ollama_prov.endpoint_url,
                "models": ollama_models if ollama_models else ["qwen3.5:9b"],
                "active_model": ollama_prov.narration_model or "qwen3.5:9b",
                "is_healthy": len(ollama_models) > 0,
            },
            {
                "id": "cloud_llm",
                "name": f"Cloud / Free LLM ({cloud_cfg.get('provider_type', 'openrouter').capitalize()})",
                "type": "cloud",
                "endpoint": cloud_cfg.get("endpoint_url", "https://openrouter.ai/api/v1"),
                "models": cloud_models,
                "active_model": cloud_cfg.get("model_name", "meta-llama/llama-3.3-70b-instruct:free"),
                "is_configured": bool(cloud_cfg.get("api_key")),
                "is_active": cloud_cfg.get("is_active", False),
            }
        ]
    }


@router.get("/llm/global-settings")
async def get_global_llm_settings():
    """
    Returns the centralized global LLM configuration, flow overrides,
    and a unified catalog of all configured and discoverable providers and models.
    """
    from engine.llm.registry import llm_registry
    settings_data = llm_registry.get_global_settings()
    cloud_cfg = llm_registry.get_cloud_config()
    ollama_prov = llm_registry.get_ollama_provider()

    ollama_models = []
    ollama_healthy = False
    try:
        ollama_models = await ollama_prov.list_available_models()
        ollama_healthy = len(ollama_models) > 0
    except Exception:
        pass

    cloud_models = list(cloud_cfg.get("custom_models", []))
    if cloud_cfg.get("model_name") and cloud_cfg.get("model_name") not in cloud_models:
        cloud_models = [cloud_cfg["model_name"]] + cloud_models

    has_cloud_key = bool(cloud_cfg.get("api_key") and cloud_cfg["api_key"].strip())
    ptype = cloud_cfg.get("provider_type", "openrouter")
    cloud_healthy = False
    if cloud_cfg.get("is_active", False):
        try:
            cloud_provider = llm_registry.get_cloud_provider()
            cloud_healthy = bool(cloud_provider and await cloud_provider.health_check())
        except Exception:
            cloud_healthy = False

    providers = [
        {
            "id": "ollama",
            "name": "Local Ollama (Offline GPU/CPU)",
            "type": "local",
            "is_configured": True,
            "is_healthy": ollama_healthy,
            "endpoint": ollama_prov.endpoint_url,
            "models": ollama_models if ollama_models else ["qwen3.5:9b", "qwen2.5:7b"],
            "default_model": ollama_prov.narration_model or "qwen2.5:7b",
        },
        {
            "id": "freellmapi",
            "name": "FreeLLMAPI Gateway (Local/Self-Hosted)",
            "type": "gateway",
            "is_configured": ptype == "freellmapi" and has_cloud_key,
            "is_healthy": ptype == "freellmapi" and cloud_healthy,
            "endpoint": cloud_cfg.get("endpoint_url") if ptype == "freellmapi" else "http://localhost:3001/v1",
            "models": (["auto"] + cloud_models) if ptype == "freellmapi" else ["auto"],
            "default_model": "auto",
        },
        {
            "id": "openrouter",
            "name": "OpenRouter Free Tier",
            "type": "cloud",
            "is_configured": (ptype == "openrouter" and has_cloud_key),
            "is_healthy": ptype == "openrouter" and cloud_healthy and has_cloud_key,
            "endpoint": "https://openrouter.ai/api/v1",
            "models": ["meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free", "deepseek/deepseek-r1:free", "qwen/qwen-2.5-vl-72b-instruct:free"],
            "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        },
        {
            "id": "groq",
            "name": "Groq Cloud Free Tier",
            "type": "cloud",
            "is_configured": (ptype == "groq" and has_cloud_key),
            "is_healthy": ptype == "groq" and cloud_healthy and has_cloud_key,
            "endpoint": "https://api.groq.com/openai/v1",
            "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
            "default_model": "llama-3.3-70b-versatile",
        },
        {
            "id": "custom",
            "name": "Custom OpenAI-Compatible Endpoint",
            "type": "custom",
            "is_configured": ptype == "custom" and has_cloud_key,
            "is_healthy": ptype == "custom" and cloud_cfg.get("is_active", False),
            "endpoint": cloud_cfg.get("endpoint_url") if ptype == "custom" else "http://127.0.0.1:1234/v1",
            "models": cloud_models if ptype == "custom" else ["default"],
            "default_model": cloud_cfg.get("model_name") if ptype == "custom" else "default",
        },
    ]

    return {
        "global_default_provider": settings_data.get("global_default_provider", "ollama"),
        "global_default_model": settings_data.get("global_default_model", "qwen3.5:9b"),
        "flow_overrides": settings_data.get("flow_overrides", {}),
        "providers": providers,
    }


@router.post("/llm/global-settings")
def update_global_llm_settings(req: GlobalLLMSettingsRequest):
    """
    Updates and persists the centralized global LLM defaults and flow-level routing.
    """
    from engine.llm.registry import llm_registry
    flows_dict = None
    if req.flow_overrides is not None:
        flows_dict = {
            k: v.model_dump() if hasattr(v, "model_dump") else dict(v)
            for k, v in req.flow_overrides.items()
        }

    saved = llm_registry.update_global_settings(
        global_default_provider=req.global_default_provider,
        global_default_model=req.global_default_model,
        flow_overrides=flows_dict,
    )
    return {
        "status": "SAVED",
        "global_default_provider": saved.get("global_default_provider"),
        "global_default_model": saved.get("global_default_model"),
        "flow_overrides": saved.get("flow_overrides"),
    }

