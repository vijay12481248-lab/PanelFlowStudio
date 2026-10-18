"""
ACE-Step 1.5 Local Music Provider Adapter for PanelFlow Studio (Chapter 9).

Connects to the official local ACE-Step REST API daemon on port 8001.
Implements robust task submission, query polling, file validation,
headroom-aware normalization, waveform extraction, and immutable persistence.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import random
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import soundfile as sf

from engine.audio.models.music_plan import MusicTakeRecord

logger = logging.getLogger("panelflow.audio.ace_step")

DEFAULT_ACE_STEP_URL = os.environ.get("ACESTEP_API_URL", "http://127.0.0.1:8001")
TOOLS_ROOT = Path(os.environ.get("PANELFLOW_LOCAL_TOOLS_ROOT", r"C:\Tools"))
ACE_STEP_DIR = TOOLS_ROOT / "ACE-Step-1.5"
ACE_STEP_PYTHON = ACE_STEP_DIR / ".venv" / "Scripts" / "python.exe"


class ACEStepProvider:
    """
    Local AI Music Provider Adapter interfacing with ACE-Step 1.5 REST API.
    """

    def __init__(self, base_url: str = DEFAULT_ACE_STEP_URL):
        self.base_url = base_url.rstrip("/")
        self._daemon_process: Optional[subprocess.Popen] = None

    def check_health(self, timeout: float = 2.0) -> Dict[str, Any]:
        """Checks whether the ACE-Step API daemon is responding."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            health_data = data.get("data", {})
            return {
                "available": True,
                "status": health_data.get("status", "ok"),
                "service": health_data.get("service", "ACE-Step API"),
                "models_initialized": health_data.get("models_initialized", False),
                "loaded_model": health_data.get("loaded_model", "acestep-v15-turbo"),
                "base_url": self.base_url,
            }
        except Exception as e:
            return {
                "available": False,
                "status": "offline",
                "error": str(e),
                "base_url": self.base_url,
            }

    def ensure_service_running(self) -> bool:
        """Verifies the service is up; if not, attempts to launch it once."""
        health = self.check_health(timeout=1.5)
        if health["available"]:
            return True

        if not ACE_STEP_PYTHON.exists():
            logger.warning(f"ACE-Step Python executable not found at {ACE_STEP_PYTHON}")
            return False

        logger.info("ACE-Step daemon is offline. Attempting automatic start...")
        try:
            self._daemon_process = subprocess.Popen(
                [
                    str(ACE_STEP_PYTHON),
                    "-m",
                    "acestep.api_server",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8001",
                ],
                cwd=str(ACE_STEP_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Poll up to 15 seconds for startup
            for _ in range(15):
                time.sleep(1.0)
                if self.check_health(timeout=1.0)["available"]:
                    logger.info("ACE-Step daemon launched successfully.")
                    return True
        except Exception as e:
            logger.error(f"Failed to start ACE-Step daemon: {e}")

        return False

    def get_models(self, timeout: float = 2.0) -> List[Dict[str, Any]]:
        """Lists available models from the ACE-Step server."""
        try:
            req = urllib.request.Request(f"{self.base_url}/v1/models")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("data", [])
        except Exception as e:
            logger.debug(f"Failed to query /v1/models: {e}")
            return []

    def generate_music_take(
        self,
        project_id: str,
        cue_id: str,
        workspace_music_dir: Path,
        prompt: str,
        audio_duration: float = 10.0,
        bpm: int = 85,
        key_scale: str = "D Minor",
        time_signature: str = "4/4",
        seed: Optional[int] = None,
        use_random_seed: bool = True,
        inference_steps: int = 8,
        guidance_scale: float = 7.0,
        model: str = "acestep-v15-turbo",
        take_index: int = 1,
        progress_cb: Optional[Callable[[float, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> MusicTakeRecord:
        """
        Submits, polls, downloads, postprocesses, and persists a real music take.
        """
        start_wall_time = time.time()
        if progress_cb:
            progress_cb(0.05, "Verifying ACE-Step server connectivity...")

        health = self.check_health(timeout=3.0)
        if not health["available"]:
            if not self.ensure_service_running():
                raise ConnectionError(
                    f"ACE-Step 1.5 API server is unreachable at {self.base_url}. "
                    f"Please launch 'start_api_server.bat' in C:\\Tools\\ACE-Step-1.5"
                )

        if cancel_check and cancel_check():
            raise asyncio.CancelledError("Music generation cancelled by user before submission")

        # Prepare payload
        final_seed = seed if (seed is not None and not use_random_seed) else random.randint(10000, 99999999)
        clamped_duration = float(min(180.0, max(5.0, audio_duration)))

        payload = {
            "prompt": prompt.strip(),
            "lyrics": "[Instrumental]",
            "audio_duration": clamped_duration,
            "bpm": int(bpm),
            "key_scale": key_scale.strip() or "D Minor",
            "time_signature": time_signature.strip() or "4/4",
            "audio_format": "wav",
            "batch_size": 1,
            "thinking": False,
            "inference_steps": int(inference_steps),
            "guidance_scale": float(guidance_scale),
            "seed": final_seed,
            "use_random_seed": False,
            "model": model,
        }

        if progress_cb:
            progress_cb(0.15, "Submitting synthesis task to ACE-Step...")

        # 1. Submit to /release_task
        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/release_task",
            data=req_data,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"ACE-Step /release_task submission failed: {e}")

        task_id = resp_json.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"ACE-Step did not return a valid task_id: {resp_json}")

        logger.info(f"ACE-Step task released: task_id={task_id}, cue={cue_id}")

        # 2. Poll /query_result
        max_poll_iterations = 90  # 90 * 1.5s = 135s timeout
        download_url: Optional[str] = None
        poll_count = 0

        while poll_count < max_poll_iterations:
            if cancel_check and cancel_check():
                raise asyncio.CancelledError(f"Music generation cancelled by user for task {task_id}")

            time.sleep(1.5)
            poll_count += 1

            query_data = json.dumps({"task_id_list": [task_id]}).encode("utf-8")
            q_req = urllib.request.Request(
                f"{self.base_url}/query_result",
                data=query_data,
                headers={"Content-Type": "application/json"},
            )

            try:
                with urllib.request.urlopen(q_req, timeout=10) as q_resp:
                    query_json = json.loads(q_resp.read().decode("utf-8"))
            except Exception as e:
                logger.warning(f"Error during query_result poll: {e}")
                continue

            rows = query_json.get("data", [])
            if not rows:
                continue

            row = rows[0]
            status = row.get("status")
            progress_text = row.get("progress_text", "Synthesizing...")

            # Calculate reasonable UI progress fraction
            est_progress = min(0.85, 0.20 + (poll_count / max_poll_iterations) * 0.65)
            if progress_cb:
                progress_cb(est_progress, f"ACE-Step: {progress_text[:50]}")

            if status == 1:  # Succeeded
                result_raw = row.get("result")
                if isinstance(result_raw, str):
                    try:
                        result_raw = json.loads(result_raw)
                    except Exception:
                        pass
                track_info = result_raw[0] if isinstance(result_raw, list) else result_raw
                audio_subpath = track_info.get("file", "") if isinstance(track_info, dict) else ""
                if not audio_subpath:
                    raise RuntimeError(f"ACE-Step reported success but returned empty file path: {row}")

                download_url = (
                    f"{self.base_url}{audio_subpath}"
                    if audio_subpath.startswith("/")
                    else f"{self.base_url}/{audio_subpath}"
                )
                break
            elif status == 2:  # Failed
                error_msg = row.get("result", "Generation failed on ACE-Step server")
                raise RuntimeError(f"ACE-Step generation failed for task {task_id}: {error_msg}")

        if not download_url:
            raise TimeoutError(f"ACE-Step generation timed out after {poll_count * 1.5:.0f}s for task {task_id}")

        if progress_cb:
            progress_cb(0.90, "Downloading generated audio master...")

        # 3. Download generated audio
        workspace_music_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = int(time.time())
        clean_cue = "".join(c for c in cue_id if c.isalnum() or c in ("-", "_")) or "cue"
        target_filename = f"music_{clean_cue}_t{take_index}_{timestamp_str}.wav"
        target_path = workspace_music_dir / target_filename

        dl_req = urllib.request.Request(
            download_url,
            headers={"User-Agent": "PanelFlowStudio/Chapter9"},
        )
        try:
            with urllib.request.urlopen(dl_req, timeout=30) as dl_resp:
                raw_bytes = dl_resp.read()
            target_path.write_bytes(raw_bytes)
        except Exception as e:
            raise IOError(f"Failed to download audio from {download_url}: {e}")

        # 4. Audio Quality Validation & Peak Headroom Normalization
        if progress_cb:
            progress_cb(0.95, "Validating audio samples, headroom, and waveform...")

        info = sf.info(str(target_path))
        data_np, sr = sf.read(str(target_path), dtype="float32")

        if len(data_np) == 0:
            target_path.unlink(missing_ok=True)
            raise ValueError("ACE-Step output file is empty (0 samples)")

        # Ensure stereo representation
        if data_np.ndim == 1:
            data_np = np.column_stack([data_np, data_np])
        elif data_np.shape[1] > 2:
            data_np = data_np[:, :2]

        # Measure peak and RMS
        peak_amp = float(np.max(np.abs(data_np)))
        rms_amp = float(np.sqrt(np.mean(data_np**2)))
        peak_dbfs = 20.0 * np.log10(max(peak_amp, 1e-6))
        rms_dbfs = 20.0 * np.log10(max(rms_amp, 1e-6))

        # Peak headroom normalization: target 0.95 (-0.45 dBFS) for broadcast headroom
        target_peak = 0.95
        if peak_amp > 0.001 and (peak_amp > 0.98 or peak_amp < 0.70):
            data_np = (data_np / peak_amp) * target_peak
            peak_amp = target_peak
            peak_dbfs = 20.0 * np.log10(peak_amp)

        # Write clean 48 kHz 16-bit PCM master
        sf.write(str(target_path), data_np, sr, subtype="PCM_16")

        # 5. Extract 100-point normalized waveform envelope for fast UI display
        waveform_peaks = self._compute_waveform_peaks(data_np, points=100)

        # Compute SHA256 checksum
        hasher = hashlib.sha256()
        hasher.update(target_path.read_bytes())
        file_sha256 = hasher.hexdigest()

        duration_sec = round(len(data_np) / float(sr), 3)
        generation_time = round(time.time() - start_wall_time, 2)

        # 6. Build immutable take record
        take_id = f"take_{clean_cue}_{timestamp_str}_{take_index}"
        record = MusicTakeRecord(
            take_id=take_id,
            cue_id=cue_id,
            project_id=project_id,
            take_index=take_index,
            audio_file_path=str(target_path.resolve()),
            audio_file_uri=f"/api/projects/{project_id}/music/assets/{target_filename}",
            duration_sec=duration_sec,
            sample_rate=sr,
            channels=2,
            format="wav",
            file_size_bytes=target_path.stat().st_size,
            checksum_sha256=file_sha256,
            prompt=prompt,
            seed=final_seed,
            bpm=bpm,
            key_scale=key_scale,
            time_signature=time_signature,
            model_id=model,
            inference_steps=inference_steps,
            guidance_scale=guidance_scale,
            measured_peak_dbfs=round(peak_dbfs, 2),
            measured_rms_dbfs=round(rms_dbfs, 2),
            waveform_peaks=waveform_peaks,
            approval_status="DRAFT",
            created_at=time.time(),
            generation_time_sec=generation_time,
        )

        # 7. Write sidecar JSON metadata
        sidecar_path = workspace_music_dir / f"{target_filename}.music.json"
        sidecar_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

        if progress_cb:
            progress_cb(1.0, f"Music take ready ({duration_sec}s, {generation_time}s)")

        logger.info(f"Successfully generated music take: {take_id} ({duration_sec}s, peak {peak_dbfs:.1f} dBFS)")
        return record

    def _compute_waveform_peaks(self, audio_data: np.ndarray, points: int = 100) -> List[float]:
        """Calculates normalized peak envelope for fast UI canvas rendering."""
        if audio_data.ndim > 1:
            mono = np.max(np.abs(audio_data), axis=1)
        else:
            mono = np.abs(audio_data)

        total_samples = len(mono)
        if total_samples == 0:
            return [0.0] * points

        chunk_size = max(1, total_samples // points)
        peaks: List[float] = []
        for i in range(points):
            start = i * chunk_size
            end = min(total_samples, start + chunk_size)
            if start < end:
                val = float(np.max(mono[start:end]))
            else:
                val = 0.0
            peaks.append(round(min(1.0, val), 3))
        return peaks


local_music_provider = ACEStepProvider()
