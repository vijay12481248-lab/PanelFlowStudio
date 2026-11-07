"""Local music for the film: one instrumental ACE-Step cue per scene, as long as the scene needs, kept with its generation record.

Needs the ACE-Step service (port 8001) and free VRAM: unload ComfyUI/Ollama first (`free_gpu`), H3 and ACE-Step do not fit together.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Callable

from engine.audio.providers.ace_step import ACEStepProvider
from engine.original.models import OriginalStory

TAIL_SEC = 6.0  # a cue is made a little longer than its scene: film_master fades it out into the next one
MIN_SEC, MAX_SEC = 30.0, 180.0  # ACE-Step's clamp is 5-180 s; a cue shorter than 30 s has no time to develop


def free_gpu(comfy_url: str = "http://127.0.0.1:8188") -> None:
    """Unload ComfyUI's models and the local LLM so the music model has the VRAM. Best effort."""
    from engine.original.animate import release_ollama

    release_ollama()
    try:
        req = urllib.request.Request(f"{comfy_url}/free", json.dumps({"unload_models": True, "free_memory": True}).encode(), {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=20).read()
    except Exception:
        pass


def cue_prompt(story: OriginalStory, scene) -> str:
    base = scene.score or f"cinematic instrumental underscore that matches a {scene.mood} scene"
    return (f"{base}. Instrumental anime film score, no vocals, no lyrics, clear melody, dynamic arrangement that develops over time, "
            "leaves space in the 2-5 kHz range so spoken dialogue stays clear.")


def make_cues(story: OriginalStory, ws: Path, scene_seconds: dict[str, float], progress: Callable[[float, str], None] = lambda p, m: None,
              seed_base: int = 4242) -> dict[str, Path]:
    """`film/audio/music/<scene>.wav` per scene (reused when it exists). Returns {scene id: wav}."""
    provider = ACEStepProvider()
    if not provider.ensure_service_running():
        raise ConnectionError("ACE-Step is not reachable on :8001")
    music_dir = ws / "film" / "audio" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)
    log_path = ws / "film" / "score.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    cues: dict[str, Path] = {}
    for n, sc in enumerate(story.scenes, 1):
        dur = min(MAX_SEC, max(MIN_SEC, scene_seconds.get(sc.id, 60.0) + TAIL_SEC))
        have = log.get(sc.id)
        if have and Path(have["file"]).exists() and abs(have["seconds"] - dur) < 8:
            cues[sc.id] = Path(have["file"])
            continue
        progress((n - 1) / len(story.scenes), f"Scoring {sc.id} ({dur:.0f} s)")
        take = provider.generate_music_take("film", sc.id, music_dir, cue_prompt(story, sc), audio_duration=dur, bpm=sc.bpm or 100,
                                            key_scale=sc.key or "D Minor", seed=seed_base + n, use_random_seed=False, inference_steps=8, take_index=1)
        wav = Path(take.audio_file_path)
        dest = music_dir / f"{sc.id}.wav"
        dest.write_bytes(wav.read_bytes())
        cues[sc.id] = dest
        log[sc.id] = {"file": str(dest), "seconds": dur, "prompt": cue_prompt(story, sc), "bpm": sc.bpm, "key": sc.key, "source": str(wav)}
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
    progress(1.0, f"{len(cues)} cues ready")
    return cues
