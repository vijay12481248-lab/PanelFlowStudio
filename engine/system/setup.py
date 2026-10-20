"""
PanelFlow Studio — System Setup, Dependency Auto-Discovery & Provisioning Engine.

Handles autonomous discovery and runtime configuration of:
1. FFmpeg & FFprobe binary discovery across system, scoop, winget, and portable roots.
2. Default Voice Reference profile provisioning into user AppData.
3. Playwright Chromium browser binary automated installation.
4. Ollama LLM model download and pull orchestration.
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

import httpx

from engine.config.settings import settings
from engine.llm.providers.ollama import validate_ollama_endpoint

logger = logging.getLogger("panelflow.system.setup")


# ---------------------------------------------------------------------------
# 1. FFmpeg Auto-Discovery & Dynamic PATH Injection
# ---------------------------------------------------------------------------

def locate_and_configure_ffmpeg() -> Dict[str, Any]:
    """
    Scans system PATH and common installation directories for FFmpeg and FFprobe.
    If found outside PATH, dynamically prepends the directory to os.environ["PATH"]
    so all child processes and libraries can access it seamlessly.
    """
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")

    if ffmpeg_bin and ffprobe_bin:
        version = _get_ffmpeg_version(ffmpeg_bin)
        return {
            "found": True,
            "ffmpeg_path": ffmpeg_bin,
            "ffprobe_path": ffprobe_bin,
            "version": version,
            "injected_into_path": False,
        }

    # Search candidates on Windows
    candidate_dirs: List[Path] = []

    # 1. Local Tools directory
    tools_root = Path(os.environ.get("PANELFLOW_LOCAL_TOOLS_ROOT", r"C:\Tools"))
    candidate_dirs.extend([
        tools_root / "ffmpeg" / "bin",
        tools_root / "ffmpeg",
        Path(r"C:\ffmpeg\bin"),
        Path(r"C:\ffmpeg"),
        Path(r"C:\Program Files\ffmpeg\bin"),
    ])

    # 2. LocalAppData WinGet packages
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_packages = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_packages.exists():
            try:
                for match in winget_packages.glob("**/ffmpeg.exe"):
                    candidate_dirs.append(match.parent)
            except Exception:
                pass

        # Also check PanelFlow Studio local bin
        candidate_dirs.append(Path(local_app_data) / "PanelFlow Studio" / "bin")

    # 3. UserProfile Scoop apps
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidate_dirs.append(Path(user_profile) / "scoop" / "apps" / "ffmpeg" / "current" / "bin")

    # 4. Portable executable relative dirs
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidate_dirs.extend([
            exe_dir / "bin",
            exe_dir / "resources" / "bin",
            exe_dir / "resources" / "ffmpeg" / "bin",
        ])

    for cdir in candidate_dirs:
        if cdir.exists():
            f_exe = cdir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
            p_exe = cdir / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
            if f_exe.exists():
                str_cdir = str(cdir.resolve())
                # Dynamically prepend to PATH
                current_path = os.environ.get("PATH", "")
                if str_cdir not in current_path.split(os.pathsep):
                    os.environ["PATH"] = str_cdir + os.pathsep + current_path
                    logger.info("Auto-injected FFmpeg directory into PATH: %s", str_cdir)

                ver = _get_ffmpeg_version(str(f_exe))
                return {
                    "found": True,
                    "ffmpeg_path": str(f_exe),
                    "ffprobe_path": str(p_exe) if p_exe.exists() else None,
                    "version": ver,
                    "injected_into_path": True,
                }

    return {
        "found": False,
        "ffmpeg_path": None,
        "ffprobe_path": None,
        "version": None,
        "injected_into_path": False,
    }


def _get_ffmpeg_version(binary_path: str) -> str:
    try:
        out = subprocess.check_output(
            [binary_path, "-version"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=2.0,
        )
        return out.splitlines()[0] if out else "Unknown"
    except Exception:
        return "Available"


# ---------------------------------------------------------------------------
# 2. Voice Reference Profiles Resolution & Provisioning
# ---------------------------------------------------------------------------

def get_voice_reference_dir() -> Path:
    """
    Returns the primary voice reference directory for TTS zero-shot cloning.
    Checks:
      1. PANELFLOW_VOICE_REF_DIR environment variable
      2. C:\\Tools\\voice_references (if present)
      3. %LOCALAPPDATA%\\PanelFlow Studio\\voice_references
      4. Bundled package directory engine/audio/voice_references
    """
    custom = os.environ.get("PANELFLOW_VOICE_REF_DIR")
    if custom and Path(custom).exists():
        return Path(custom)

    tools_voices = Path(r"C:\Tools\voice_references")
    if tools_voices.exists() and len(list(tools_voices.glob("*.*"))) > 0:
        return tools_voices

    # User AppData voice reference directory
    app_data_voices = settings.app_data_dir / "voice_references"
    app_data_voices.mkdir(parents=True, exist_ok=True)
    if len(list(app_data_voices.glob("*.*"))) > 0:
        return app_data_voices

    # Bundled package fallback
    pkg_bundled = Path(__file__).resolve().parent.parent / "audio" / "voice_references"
    if pkg_bundled.exists() and len(list(pkg_bundled.glob("*.*"))) > 0:
        return pkg_bundled

    return app_data_voices


def provision_default_voices() -> Dict[str, Any]:
    """
    Ensures default neural voice profiles (Aria, Marcus, Seraphina) exist in
    AppData so TTS synthesis functions out of the box on any machine.
    """
    target_dir = settings.app_data_dir / "voice_references"
    target_dir.mkdir(parents=True, exist_ok=True)

    bundled_dirs = [
        Path(r"C:\Tools\voice_references"),
        Path(__file__).resolve().parent.parent / "audio" / "voice_references",
    ]

    copied = 0
    for b_dir in bundled_dirs:
        if b_dir.exists():
            for src_file in b_dir.glob("*.*"):
                if src_file.suffix.lower() in (".wav", ".mp3", ".ogg", ".flac"):
                    dest_file = target_dir / src_file.name
                    if not dest_file.exists() or dest_file.stat().st_size == 0:
                        try:
                            shutil.copy2(src_file, dest_file)
                            copied += 1
                        except Exception as e:
                            logger.warning("Could not copy voice profile %s: %s", src_file.name, e)

    # Collect available profiles
    profiles = []
    for f in sorted(target_dir.glob("*.*")):
        if f.suffix.lower() in (".wav", ".mp3", ".ogg"):
            profiles.append({
                "name": f.stem,
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "path": str(f),
            })

    return {
        "success": True,
        "voice_directory": str(target_dir),
        "copied_count": copied,
        "total_profiles": len(profiles),
        "profiles": profiles,
    }


# ---------------------------------------------------------------------------
# 3. Playwright Automated Browser Binary Installer
# ---------------------------------------------------------------------------

class PlaywrightInstallManager:
    """
    Manages non-blocking asynchronous Playwright Chromium installation.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.status = "IDLE"  # "IDLE" | "RUNNING" | "COMPLETED" | "FAILED"
        self.log_lines: List[str] = []
        self.error_message: Optional[str] = None
        self.exit_code: Optional[int] = None

    def start_install(self) -> Dict[str, Any]:
        with self._lock:
            if self.status == "RUNNING":
                return {"status": "ALREADY_RUNNING", "message": "Browser installation is already in progress."}

            self.status = "RUNNING"
            self.log_lines = []
            self.error_message = None
            self.exit_code = None

            t = threading.Thread(target=self._run_install, daemon=True)
            t.start()
            return {"status": "STARTED", "message": "Playwright Chromium installation started."}

    def _run_install(self):
        logger.info("Starting background Playwright Chromium installation...")
        try:
            cmd = [sys.executable, "-m", "playwright", "install", "chromium"]
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in proc.stdout:
                clean = line.strip()
                if clean:
                    self.log_lines.append(clean)
                    if len(self.log_lines) > 200:
                        self.log_lines.pop(0)

            proc.wait(timeout=300)
            self.exit_code = proc.returncode

            with self._lock:
                if proc.returncode == 0:
                    self.status = "COMPLETED"
                    self.log_lines.append("Chromium installed successfully.")
                else:
                    self.status = "FAILED"
                    self.error_message = f"Process exited with non-zero code {proc.returncode}"
        except Exception as e:
            with self._lock:
                self.status = "FAILED"
                self.error_message = str(e)
                self.log_lines.append(f"Error: {e}")

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "log_lines": list(self.log_lines),
                "error_message": self.error_message,
                "exit_code": self.exit_code,
            }


playwright_installer = PlaywrightInstallManager()


# ---------------------------------------------------------------------------
# 4. Ollama Automated Model Pull Manager
# ---------------------------------------------------------------------------

class OllamaModelPullManager:
    """
    Manages non-blocking asynchronous Ollama model downloads via REST API.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.status = "IDLE"  # "IDLE" | "PULLING" | "COMPLETED" | "FAILED"
        self.model_name: str = ""
        self.status_text: str = ""
        self.completed_bytes: int = 0
        self.total_bytes: int = 0
        self.percent: float = 0.0
        self.error_message: Optional[str] = None

    async def start_pull(self, model_name: str, endpoint_url: str = "http://127.0.0.1:11434") -> Dict[str, Any]:
        endpoint_host = httpx.URL(endpoint_url).host or ""
        is_remote = endpoint_host.lower() not in {"localhost", "127.0.0.1", "::1"}
        valid, error = validate_ollama_endpoint(endpoint_url, is_remote=is_remote)
        if not valid:
            return {"status": "FAILED", "model": model_name, "message": error}
        with self._lock:
            if self.status == "PULLING":
                return {
                    "status": "ALREADY_RUNNING",
                    "model": self.model_name,
                    "message": f"Download of {self.model_name} is already in progress.",
                }

            self.status = "PULLING"
            self.model_name = model_name
            self.status_text = f"Initializing download of {model_name}..."
            self.completed_bytes = 0
            self.total_bytes = 0
            self.percent = 0.0
            self.error_message = None

        asyncio.create_task(self._pull_worker(model_name, endpoint_url))
        return {"status": "STARTED", "model": model_name}

    async def _pull_worker(self, model_name: str, endpoint_url: str):
        url = f"{endpoint_url.rstrip('/')}/api/pull"
        logger.info("Initiating Ollama model pull for %s from %s", model_name, url)

        try:
            async with httpx.AsyncClient(timeout=600.0, follow_redirects=False) as client:
                async with client.stream("POST", url, json={"name": model_name, "stream": True}) as response:
                    if response.status_code != 200:
                        text = await response.aread()
                        with self._lock:
                            self.status = "FAILED"
                            self.error_message = f"HTTP {response.status_code}: {text.decode(errors='replace')}"
                        return

                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            with self._lock:
                                self.status_text = data.get("status", self.status_text)
                                comp = data.get("completed", 0)
                                tot = data.get("total", 0)
                                if tot > 0:
                                    self.completed_bytes = comp
                                    self.total_bytes = tot
                                    self.percent = round((comp / tot) * 100, 1)
                        except Exception:
                            pass

            with self._lock:
                self.status = "COMPLETED"
                self.status_text = f"Model {model_name} successfully downloaded and ready."
                self.percent = 100.0
        except Exception as e:
            with self._lock:
                self.status = "FAILED"
                self.error_message = str(e)
                self.status_text = f"Failed to download {model_name}: {e}"

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": self.status,
                "model_name": self.model_name,
                "status_text": self.status_text,
                "completed_bytes": self.completed_bytes,
                "total_bytes": self.total_bytes,
                "percent": self.percent,
                "error_message": self.error_message,
            }


ollama_pull_manager = OllamaModelPullManager()
