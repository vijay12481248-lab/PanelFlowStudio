import os
import subprocess
import sys
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from engine.config.settings import settings
from engine.database.session import get_db
from engine.projects.service import project_service

router = APIRouter(prefix="/api/system", tags=["system"])

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
        "workspace_root": str(settings.workspace_root),
    }

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

    results = []

    # 1. FFmpeg
    ffmpeg_bin = shutil.which("ffmpeg")
    ffmpeg_version = "Unknown"
    if ffmpeg_bin:
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

    # 4. F5-TTS
    f5_hf_base = Path.home() / ".cache" / "huggingface" / "hub" / "models--SWivid--F5-TTS"
    f5_weights = list(f5_hf_base.glob("**/model_*.safetensors")) if f5_hf_base.exists() else []
    f5_venv = Path(r"C:\Tools\F5-TTS\.venv\Scripts\python.exe")
    f5_pool = Path(r"C:\Tools\generated_audio\marcus_male_deep")
    f5_files = list(f5_pool.glob("*.wav")) if f5_pool.exists() else []

    if f5_weights and (f5_venv.exists() or len(f5_files) > 0):
        f5_status = "READY"
        f5_version = f"F5-TTS v1 Base (1.35GB Neural Weights on CUDA, {len(f5_files)} cached takes)"
        f5_path = str(f5_weights[0])
        f5_details = "Zero-shot neural dialogue synthesis with natural breathiness and emotional inflections."
    elif len(f5_files) > 0:
        f5_status = "DEGRADED"
        f5_version = f"Procedural Voice Fallback ({len(f5_files)} cached takes)"
        f5_path = str(f5_pool)
        f5_details = "Pre-generated reference assets active. Full neural inference requires model weights in C:\\Tools\\F5-TTS."
    else:
        f5_status = "MISSING"
        f5_version = "Model & Runtime Missing"
        f5_path = ""
        f5_details = "Voice synthesis engine not configured. Procedural synthesis fallback active."

    results.append({
        "id": "f5_tts",
        "name": "F5-TTS Neural Voice",
        "category": "audio_engine",
        "status": f5_status,
        "version": f5_version,
        "path": f5_path,
        "required": True,
        "details": f5_details,
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
        "required": True,
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
    }


@router.post("/ollama/config")
def save_ollama_config(req: OllamaConfigRequest):
    """
    Validates and updates Ollama configuration.
    Enforces SSRF prevention on endpoint URLs.
    """
    from engine.llm.registry import llm_registry
    from engine.llm.providers.ollama import validate_ollama_endpoint
    from engine.system.resources import resource_manager

    valid, err_msg = validate_ollama_endpoint(req.endpoint_url, req.is_remote)
    if not valid:
        raise HTTPException(status_code=400, detail=f"Invalid Ollama endpoint: {err_msg}")

    current_prov = llm_registry.get_ollama_provider()
    # If auth_token is not provided, preserve current token
    final_token = req.auth_token if req.auth_token is not None else current_prov.auth_token

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

    valid, err_msg = validate_ollama_endpoint(target_url, is_remote)
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
    )
    return results



