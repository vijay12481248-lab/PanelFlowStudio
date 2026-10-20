"""
Hardware resource telemetry and GPU admission controller for PanelFlow Studio.
Provides safe monitoring of RAM, NVIDIA GPU VRAM, active Ollama runtime allocations,
and enforces bounded concurrency across multi-project jobs.
"""
import os
import shutil
import subprocess
import time
import asyncio
import logging
from typing import Dict, Any, Tuple, Optional, Set
import psutil
import httpx
from urllib.parse import urlsplit
from engine.llm.providers.ollama import (
    OllamaEndpointAuthorization,
    load_ollama_endpoint_authorization,
    validate_ollama_endpoint,
)

logger = logging.getLogger("panelflow.system.resources")


def _validated_ollama_url(
    endpoint_url: str,
    authorization: OllamaEndpointAuthorization | None = None,
) -> str:
    """Validate again at the network boundary, independent of API callers."""
    local_ok, _ = validate_ollama_endpoint(endpoint_url)
    remote_ok, _ = validate_ollama_endpoint(
        endpoint_url,
        is_remote=True,
        authorization=authorization or load_ollama_endpoint_authorization(),
    )
    if not (local_ok or remote_ok):
        raise ValueError("Invalid Ollama endpoint")
    parsed = urlsplit(endpoint_url)
    if parsed.username or parsed.password or parsed.fragment or parsed.query or parsed.path not in ("", "/"):
        raise ValueError("Invalid Ollama endpoint: credentials, path, query and fragment are not allowed")
    return endpoint_url.rstrip("/")


class SystemResourceManager:
    """
    Manages hardware resource detection, memory telemetry, and admission
    for GPU-intensive inference and rendering tasks.
    """

    def __init__(self):
        self._concurrency_mode: str = "MANUAL"  # "AUTO" or "MANUAL"
        self._max_gpu_concurrency: int = 1      # Default: exactly 1 active Ollama/GPU request
        self._active_gpu_jobs: Set[str] = set()
        self._lock = asyncio.Lock()

    @property
    def concurrency_mode(self) -> str:
        return self._concurrency_mode

    @property
    def max_gpu_concurrency(self) -> int:
        return self._max_gpu_concurrency

    @property
    def active_gpu_jobs_count(self) -> int:
        return len(self._active_gpu_jobs)

    def set_concurrency(self, mode: str, max_concurrency: int = 1) -> Dict[str, Any]:
        mode_upper = mode.upper()
        if mode_upper not in ("AUTO", "MANUAL"):
            raise ValueError(f"Invalid concurrency mode: {mode}. Must be 'AUTO' or 'MANUAL'.")
        clamped = max(1, min(4, int(max_concurrency)))
        self._concurrency_mode = mode_upper
        self._max_gpu_concurrency = clamped
        logger.info(f"Updated GPU inference concurrency: mode={self._concurrency_mode}, limit={self._max_gpu_concurrency}")
        return {
            "concurrency_mode": self._concurrency_mode,
            "max_gpu_concurrency": self._max_gpu_concurrency,
        }

    def get_system_memory(self) -> Dict[str, Any]:
        """Reads host RAM usage via psutil."""
        try:
            vm = psutil.virtual_memory()
            return {
                "total_bytes": vm.total,
                "available_bytes": vm.available,
                "used_bytes": vm.used,
                "total_gb": round(vm.total / (1024**3), 2),
                "available_gb": round(vm.available / (1024**3), 2),
                "used_percent": round(vm.percent, 1),
                "sufficient_for_inference": vm.available >= 1.5 * (1024**3),
            }
        except Exception as e:
            logger.warning(f"Failed to read system memory: {e}")
            return {
                "total_gb": 0.0,
                "available_gb": 0.0,
                "used_percent": 0.0,
                "sufficient_for_inference": True,
            }

    def get_gpu_memory(self) -> Dict[str, Any]:
        """
        Reads dedicated GPU VRAM using nvidia-smi with safe fallback to CPU-only telemetry.
        """
        smi = shutil.which("nvidia-smi")
        if smi:
            try:
                res = subprocess.run(
                    [
                        smi,
                        "--query-gpu=name,memory.total,memory.free,memory.used",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                )
                if res.returncode == 0 and res.stdout.strip():
                    parts = [p.strip() for p in res.stdout.strip().splitlines()[0].split(",")]
                    name = parts[0]
                    total_mb = float(parts[1])
                    free_mb = float(parts[2])
                    used_mb = float(parts[3])
                    return {
                        "available": True,
                        "device_name": name,
                        "total_mb": total_mb,
                        "free_mb": free_mb,
                        "used_mb": used_mb,
                        "used_percent": round((used_mb / max(1.0, total_mb)) * 100, 1),
                        "headroom_mb": free_mb,
                    }
            except Exception as e:
                logger.debug(f"nvidia-smi query failed: {e}")

        # Fallback PyTorch CUDA detection if available
        try:
            import torch
            if torch.cuda.is_available():
                device_name = torch.cuda.get_device_name(0)
                total_b = torch.cuda.get_device_properties(0).total_memory
                allocated_b = torch.cuda.memory_allocated(0)
                reserved_b = torch.cuda.memory_reserved(0)
                total_mb = round(total_b / (1024**2), 1)
                used_mb = round(allocated_b / (1024**2), 1)
                free_mb = max(0.0, total_mb - round(reserved_b / (1024**2), 1))
                return {
                    "available": True,
                    "device_name": device_name,
                    "total_mb": total_mb,
                    "free_mb": free_mb,
                    "used_mb": used_mb,
                    "used_percent": round((used_mb / max(1.0, total_mb)) * 100, 1),
                    "headroom_mb": free_mb,
                }
        except Exception:
            pass

        return {
            "available": False,
            "device_name": "CPU / System Integrated",
            "total_mb": 0.0,
            "free_mb": 0.0,
            "used_mb": 0.0,
            "used_percent": 0.0,
            "headroom_mb": 0.0,
        }

    async def get_ollama_runtime(
        self,
        endpoint_url: str = "http://127.0.0.1:11434",
        auth_token: Optional[str] = None,
        authorization: OllamaEndpointAuthorization | None = None,
    ) -> Dict[str, Any]:
        """
        Inspects running models, allocated VRAM, and context sizes via Ollama GET /api/ps.
        """
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            clean_url = _validated_ollama_url(endpoint_url, authorization)
            async with httpx.AsyncClient(timeout=3.0, headers=headers, follow_redirects=False) as client:
                res = await client.get(f"{clean_url}/api/ps")
                if res.status_code == 200:
                    data = res.json()
                    models = []
                    total_vram_bytes = 0
                    for m in data.get("models", []):
                        vram_bytes = m.get("size_vram", m.get("size", 0))
                        total_vram_bytes += vram_bytes
                        models.append({
                            "name": m.get("name", ""),
                            "model": m.get("model", ""),
                            "size_mb": round(m.get("size", 0) / (1024**2), 1),
                            "vram_mb": round(vram_bytes / (1024**2), 1),
                            "context_length": m.get("context_length", 0),
                            "runner": m.get("runner", "llamacpp"),
                            "expires_at": m.get("expires_at", ""),
                        })
                    return {
                        "online": True,
                        "loaded_models_count": len(models),
                        "total_ollama_vram_mb": round(total_vram_bytes / (1024**2), 1),
                        "models": models,
                    }
        except Exception as e:
            logger.debug(f"Failed to inspect Ollama /api/ps: {e}")

        return {
            "online": False,
            "loaded_models_count": 0,
            "total_ollama_vram_mb": 0.0,
            "models": [],
        }

    async def get_full_telemetry(
        self,
        ollama_endpoint: str = "http://127.0.0.1:11434",
        auth_token: Optional[str] = None,
        authorization: OllamaEndpointAuthorization | None = None,
    ) -> Dict[str, Any]:
        """Aggregates host RAM, GPU VRAM, active scheduler jobs, and Ollama runtime telemetry."""
        ram = self.get_system_memory()
        gpu = self.get_gpu_memory()
        ollama = await self.get_ollama_runtime(ollama_endpoint, auth_token, authorization)

        # Dynamic Auto-concurrency adjustment
        effective_concurrency = self._max_gpu_concurrency
        if self._concurrency_mode == "AUTO":
            # If GPU has >= 8GB free VRAM and RAM available >= 8GB, allow 2 parallel requests
            if gpu.get("available") and gpu.get("free_mb", 0) >= 8000 and ram.get("available_gb", 0) >= 8.0:
                effective_concurrency = 2
            else:
                effective_concurrency = 1

        return {
            "ram": ram,
            "gpu": gpu,
            "ollama": ollama,
            "scheduler": {
                "concurrency_mode": self._concurrency_mode,
                "configured_limit": self._max_gpu_concurrency,
                "effective_limit": effective_concurrency,
                "active_gpu_jobs": list(self._active_gpu_jobs),
                "active_count": len(self._active_gpu_jobs),
                "available_slots": max(0, effective_concurrency - len(self._active_gpu_jobs)),
            },
        }

    def can_admit_gpu_job(self, required_vram_mb: float = 0.0) -> Tuple[bool, str]:
        """
        Determines whether a GPU-bound job (VLM, LLM, TTS, or GPU render) can be admitted.
        Returns (True, 'Admitted') or (False, 'Reason').
        """
        effective_limit = self._max_gpu_concurrency
        if self._concurrency_mode == "AUTO":
            gpu = self.get_gpu_memory()
            ram = self.get_system_memory()
            if gpu.get("available") and gpu.get("free_mb", 0) >= 8000 and ram.get("available_gb", 0) >= 8.0:
                effective_limit = 2
            else:
                effective_limit = 1

        if len(self._active_gpu_jobs) >= effective_limit:
            return False, f"GPU inference queue busy ({len(self._active_gpu_jobs)}/{effective_limit} active slots)."

        # Check VRAM headroom if specified and GPU is available
        if required_vram_mb > 0:
            gpu = self.get_gpu_memory()
            if gpu.get("available") and gpu.get("free_mb", 0) < required_vram_mb:
                return False, f"Insufficient GPU VRAM: {gpu.get('free_mb', 0):.0f}MB free, required {required_vram_mb:.0f}MB."

        return True, "Admitted"

    async def acquire_gpu_slot(self, job_id: str, required_vram_mb: float = 0.0) -> bool:
        """Atomically claims a GPU inference execution slot."""
        async with self._lock:
            admitted, reason = self.can_admit_gpu_job(required_vram_mb)
            if admitted:
                self._active_gpu_jobs.add(job_id)
                logger.info(f"GPU slot acquired for job {job_id} ({len(self._active_gpu_jobs)} active)")
                return True
            return False

    async def release_gpu_slot(self, job_id: str) -> None:
        """Atomically releases a claimed GPU inference slot."""
        async with self._lock:
            if job_id in self._active_gpu_jobs:
                self._active_gpu_jobs.remove(job_id)
                logger.info(f"GPU slot released for job {job_id} ({len(self._active_gpu_jobs)} active)")

    async def benchmark_concurrency(
        self,
        endpoint_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3.5:9b",
        auth_token: Optional[str] = None,
        authorization: OllamaEndpointAuthorization | None = None,
    ) -> Dict[str, Any]:
        """
        Benchmarks sequential vs 2-request concurrent performance under identical workloads.
        """
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        clean_url = _validated_ollama_url(endpoint_url, authorization)
        test_payload = {
            "model": model,
            "prompt": "Summarize the essence of courage in exactly two sentences.",
            "stream": False,
            "options": {"num_predict": 64, "temperature": 0.1},
        }

        # 1. Measure sequential execution (2 requests back-to-back)
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=60.0, headers=headers, follow_redirects=False) as client:
            r1 = await client.post(f"{clean_url}/api/generate", json=test_payload)
            if r1.status_code != 200:
                raise RuntimeError(f"Ollama benchmark failed: HTTP {r1.status_code}")
            r2 = await client.post(f"{clean_url}/api/generate", json=test_payload)
            if r2.status_code != 200:
                raise RuntimeError(f"Ollama benchmark failed: HTTP {r2.status_code}")
        seq_duration = time.perf_counter() - t0

        # 2. Measure concurrent execution (2 requests simultaneously via asyncio.gather)
        t1 = time.perf_counter()
        async with httpx.AsyncClient(timeout=60.0, headers=headers, follow_redirects=False) as client:
            c1, c2 = await asyncio.gather(
                client.post(f"{clean_url}/api/generate", json=test_payload),
                client.post(f"{clean_url}/api/generate", json=test_payload),
            )
            for response in (c1, c2):
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama benchmark failed: HTTP {response.status_code}")
        concurrent_duration = time.perf_counter() - t1

        speedup_ratio = round(seq_duration / max(0.001, concurrent_duration), 2)
        recommendation = "2 concurrent requests supported with positive throughput scaling." if speedup_ratio >= 1.25 else "Sequential execution recommended (concurrency did not scale or caused compute bottleneck)."

        return {
            "model_tested": model,
            "sequential_duration_sec": round(seq_duration, 3),
            "concurrent_duration_sec": round(concurrent_duration, 3),
            "speedup_ratio": speedup_ratio,
            "recommendation": recommendation,
        }


resource_manager = SystemResourceManager()
