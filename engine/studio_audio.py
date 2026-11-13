"""Music and speech jobs for the AI Game Studio, run through the engine's job queue (so the VRAM gate and the job history apply).

Music is ACE-Step 1.5 (its own local API server, started by the provider when needed); speech is Kokoro-82M in-process. Both
persist the result as a project asset with its provenance, like the ComfyUI jobs. Hugging Face runs offline, so a missing
weight is an error and never a silent download.
"""
from __future__ import annotations

import hashlib
import io
import os
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from engine.database.models import AssetRecord, ProjectRecord
from engine.jobs.workflow import register_operation_factory
from engine.security.paths import open_contained_output, resolve_contained_path

MUSIC_JOB_TYPE = "STUDIO_MUSIC_GENERATION"
SPEECH_JOB_TYPE = "STUDIO_SPEECH_GENERATION"
MUSIC_VRAM_MB = 3000   # measured 2026-11-13: ACE-Step turbo raised GPU use by 2.1 GB (a 24 s take, cold start 152 s); the gate admits on this number
SPEECH_VRAM_MB = 1500  # Kokoro-82M: measured +1.2 GB (a 5 s line, 14 s)
KOKORO_SR = 24000


class StudioAudioError(RuntimeError):
    """Raised when studio audio cannot be generated or persisted."""


def _project(db: Session, project_id: str) -> tuple[ProjectRecord, Path]:
    project = db.query(ProjectRecord).filter(ProjectRecord.id == project_id).first()
    if not project:
        raise StudioAudioError("Project not found")
    return project, Path(str(project.workspace_path))


def _persist(db: Session, project_id: str, workspace: Path, wav: bytes, asset_type: str, provenance: dict[str, Any]) -> dict[str, Any]:
    import soundfile as sf

    info = sf.info(io.BytesIO(wav))
    if info.frames <= 0:
        raise StudioAudioError("the generated audio is empty")
    asset_id = str(uuid.uuid4())
    filename = f"{asset_id}.wav"
    relative = Path("generated") / "studio_audio" / filename
    target = resolve_contained_path(workspace, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open_contained_output(workspace, relative, exclusive=True) as out:
        out.write(wav)
    sha256 = hashlib.sha256(wav).hexdigest()
    db.add(AssetRecord(id=asset_id, project_id=project_id, asset_type=asset_type, filename=filename, relative_path=relative.as_posix(),
                       content_type="audio/wav", byte_size=len(wav), sha256=sha256, status="READY",
                       provenance={**provenance, "seconds": round(info.frames / info.samplerate, 3), "sample_rate": info.samplerate, "channels": info.channels}))
    db.commit()
    return {"asset_id": asset_id, "relative_path": relative.as_posix(), "filename": filename, "content_type": "audio/wav", "byte_size": len(wav),
            "sha256": sha256, "seconds": round(info.frames / info.samplerate, 3), "sample_rate": info.samplerate}


def generate_music_operation(db: Session, progress, is_cancelled, *, project_id: str, prompt: str, seconds: float, bpm: int, key_scale: str, seed: int,
                             model: str = "acestep-v15-turbo", inference_steps: int = 8) -> dict[str, Any]:
    from engine.audio.providers.ace_step import ACEStepProvider  # lazy: heavy

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    _, workspace = _project(db, project_id)
    music_dir = workspace / "audio" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    try:
        take = ACEStepProvider().generate_music_take(project_id=project_id, cue_id=f"studio_{seed}", workspace_music_dir=music_dir, prompt=prompt,
                                                     audio_duration=seconds, bpm=bpm, key_scale=key_scale, seed=seed, use_random_seed=False,
                                                     inference_steps=inference_steps, model=model, progress_cb=progress, cancel_check=is_cancelled)
    except Exception as exc:  # the provider raises ConnectionError, TimeoutError, cancellation: all become one job failure with the reason
        raise StudioAudioError(f"ACE-Step: {exc}") from exc
    wav = Path(take.audio_file_path).read_bytes()
    result = _persist(db, project_id, workspace, wav, "STUDIO_MUSIC", {"provider": "ace_step", "model": model, "prompt": prompt, "bpm": bpm,
                                                                         "key_scale": key_scale, "seed": seed, "requested_seconds": seconds})
    progress(1.0, "Music take persisted")
    return result


def generate_speech_operation(db: Session, progress, is_cancelled, *, project_id: str, text: str, voice: str, speed: float) -> dict[str, Any]:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import soundfile as sf
    from kokoro import KPipeline

    _, workspace = _project(db, project_id)
    if is_cancelled():
        raise StudioAudioError("Speech generation cancelled before it started")
    progress(0.1, f"Speaking with Kokoro voice {voice}")
    try:
        pipe = KPipeline(lang_code=voice[0])  # 'a' American, 'b' British: the voice name's first letter
        chunks = [np.asarray(a.detach().cpu() if hasattr(a, "detach") else a) for _, _, a in pipe(text, voice=voice, speed=speed)]
    except Exception as exc:
        raise StudioAudioError(f"Kokoro: {exc}") from exc
    if not chunks:
        raise StudioAudioError(f"Kokoro produced no audio for '{text[:40]}'")
    buf = io.BytesIO()
    sf.write(buf, np.concatenate(chunks), KOKORO_SR, format="WAV", subtype="PCM_16")
    result = _persist(db, project_id, workspace, buf.getvalue(), "STUDIO_SPEECH", {"provider": "kokoro", "model": "kokoro-82m", "voice": voice, "speed": speed, "text": text})
    progress(1.0, "Speech persisted")
    return result


def build_music_operation(project_id: str, payload: dict[str, Any]):
    return lambda db, progress, is_cancelled: generate_music_operation(
        db, progress, is_cancelled, project_id=project_id, prompt=payload["prompt"], seconds=payload["seconds"], bpm=payload["bpm"],
        key_scale=payload["key_scale"], seed=payload["seed"], model=payload.get("model", "acestep-v15-turbo"), inference_steps=payload.get("inference_steps", 8))


def build_speech_operation(project_id: str, payload: dict[str, Any]):
    return lambda db, progress, is_cancelled: generate_speech_operation(
        db, progress, is_cancelled, project_id=project_id, text=payload["text"], voice=payload["voice"], speed=payload["speed"])


register_operation_factory(MUSIC_JOB_TYPE, build_music_operation)
register_operation_factory(SPEECH_JOB_TYPE, build_speech_operation)
