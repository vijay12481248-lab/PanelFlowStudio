"""Animate key beats with the fast MiniMax H3 image-to-video workflow (`fastvideo_h3_i2v`, registered and checksummed).

A beat's picture is the first frame; the clip lands in `<workspace>/clips/<beat>.mp4`, where `video.py` already looks (it drops the clip's own
audio, ping-pongs it to the narration length and shows it whole). The motion prompt is composed from the beat's ShotSpec and narration, the same
way image prompts are: nothing is typed per story. H3 continues whatever action it sees in the picture, so the prompt names the moment from the
narration and asks for everything else to stay as drawn.

Measured on the owner's machine (2026-11-06, 864x480, 90 frames = 4.7 s): about 65 s per clip, against ~180 s expected for the earlier turbo graph.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine, ComfyImageGenerationError, _patch_workflow
from engine.original.models import OriginalStory, Panel
from engine.original.shotspec import ShotSpec

FAST_H3_ID = "fastvideo_h3_i2v"
STATIC_CAMERA = "nothing; it is a Static Shot, fixed on a tripod, with no zoom, no pan and no tilt"  # the default: a push-in is opt-in per panel (Panel.camera)
DEFAULT_SECONDS = 3.6  # the graph turns this into 90 frames (a multiple-of-17-plus-5 rule) = 4.7 s at 19 fps; video.py ping-pongs it to the narration
BEATS_PER_CLIP = 4.5  # default: about one animated beat in 4-5


def motion_prompt(story: OriginalStory, panel: Panel) -> str:
    """The H3 text for one beat, from its ShotSpec (or, for an undirected panel, its action) and its narration."""
    chars = {c.id: c for c in story.bible.characters}
    if panel.director:
        spec = ShotSpec(**panel.director)
        who = []
        for cp in spec.characters:
            c = chars.get(cp.id)
            look = ", ".join(t.strip() for t in c.look.split(",")[:3]) if c else ""
            who.append(f"{c.name if c else cp.id} ({look}) {cp.pose}, expression {cp.expression}" + (f", {cp.action}" if cp.action else ""))
        scene = f"{spec.setting}. {'; '.join(who)}. The moment in the story: {panel.caption} Lighting: {spec.lighting}. Mood: {spec.mood}."
    else:
        scene = f"{panel.action}. The moment in the story: {panel.caption}"
    camera = panel.camera or STATIC_CAMERA
    return ("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
            f"integrated_multimodal_description: [Shot 1] {scene} The camera does {camera}. Only the action of this moment moves; everything else stays exactly as drawn.\n\n"
            "overall_soundscape: quiet, realistic ambience that matches the room, no speech.\n\nnon_diegetic_music: none.")


def _action_score(panel: Panel) -> int:
    """How much happens in a beat: the length of what its characters do, plus what must be visible. More action = a better candidate to move."""
    if not panel.director:
        return len(panel.action)
    spec = ShotSpec(**panel.director)
    return sum(len(cp.action) for cp in spec.characters) + 10 * len(spec.key_visuals)


def pick_beats(story: OriginalStory, max_clips: int | None = None) -> list[str]:
    """Generic choice of beats to animate: the most active beat of each scene, then the next most active overall, up to `max_clips`
    (default about one beat in 4-5). Returned in story order."""
    n = len(story.panels)
    limit = max(1, max_clips if max_clips is not None else round(n / BEATS_PER_CLIP))
    chosen: list[str] = []
    for sc in dict.fromkeys(p.scene_id for p in story.panels):
        best = max((p for p in story.panels if p.scene_id == sc), key=_action_score)
        chosen.append(best.id)
    rest = sorted((p for p in story.panels if p.id not in chosen), key=_action_score, reverse=True)
    if len(chosen) > limit:
        chosen = sorted(chosen, key=lambda i: _action_score(next(p for p in story.panels if p.id == i)), reverse=True)[:limit]
    chosen += [p.id for p in rest[: max(0, limit - len(chosen))]]
    order = {p.id: k for k, p in enumerate(story.panels)}
    return sorted(chosen, key=order.get)


def release_ollama() -> None:
    """Unload the local LLM so H3 has the VRAM (they do not fit together); Ollama reloads it on the next request. Best effort."""
    try:
        import httpx

        from engine.llm.registry import llm_registry

        provider = llm_registry.get_ollama_provider()
        for model in {provider.vision_model, provider.text_model, provider.reasoning_model, provider.narration_model}:
            httpx.post(f"{provider.endpoint_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=20.0)
    except Exception:
        pass


def animate_beats(story: OriginalStory, ws: Path, beat_ids: list[str] | None = None, max_clips: int | None = None, *, seconds: float = DEFAULT_SECONDS,
                  client: ComfyUIClient | None = None, timeout: float = 900.0, progress: Callable[[float, str], None] = lambda p, m: None,
                  is_cancelled: Callable[[], bool] = lambda: False, free_llm_memory: bool = True) -> dict:
    """Make `clips/<beat>.mp4` for each chosen beat (explicit ids, else `pick_beats`). A clip newer than its picture is reused; a failed beat
    is reported and the rest continue (a story with a missing clip just shows that picture still)."""
    by_id = {p.id: p for p in story.panels}
    ids = beat_ids if beat_ids else pick_beats(story, max_clips)
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise ValueError(f"unknown beats: {unknown}")
    missing = [i for i in ids if not (ws / "panels" / f"{i}.png").exists()]
    if missing:
        raise ValueError(f"no picture yet for: {missing} (draw the art first)")
    client = client or ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)
    pre = registry.preflight(FAST_H3_ID)
    if not pre["ready"]:
        raise ComfyImageGenerationError(f"ComfyUI workflow preflight failed: missing nodes={pre['missing_nodes']}, missing models={pre['missing_models']}")
    workflow, sha = registry.load(FAST_H3_ID)
    slots = registry.metadata(FAST_H3_ID)["patch_slots"]
    engine = ArtEngine(client, registry)
    from engine.comfyui.service import _history_videos

    clips = ws / "clips"
    clips.mkdir(exist_ok=True)
    log_path = clips / "animate.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    if free_llm_memory:
        release_ollama()
    done, skipped, failed = [], [], []
    for n, bid in enumerate(ids):
        if is_cancelled():
            raise RuntimeError("cancelled")
        picture, clip = ws / "panels" / f"{bid}.png", clips / f"{bid}.mp4"
        if clip.exists() and clip.stat().st_mtime >= picture.stat().st_mtime:
            skipped.append(bid)
            continue
        progress(n / len(ids), f"Animating {bid} ({n + 1}/{len(ids)})")
        seed = int(hashlib.sha256(f"{story.bible.premise.title}|{bid}".encode()).hexdigest()[:12], 16)
        text = motion_prompt(story, by_id[bid])
        started = time.monotonic()
        try:
            patched = _patch_workflow(workflow, slots, text, None, 0, 0, seed, f"video/panelflow_{bid}", reference_image=client.upload_image(picture),
                                      duration=seconds)
            raw, prompt_id, _ = engine.run(patched, timeout=timeout, is_cancelled=is_cancelled, collect=_history_videos)
        except Exception as exc:
            failed.append({"beat": bid, "error": str(exc)[:200]})
            continue
        clip.write_bytes(raw)
        log[bid] = {"clip": f"clips/{bid}.mp4", "seed": seed, "seconds": seconds, "prompt": text, "workflow": FAST_H3_ID, "workflow_sha256": sha,
                    "prompt_id": prompt_id, "elapsed_s": round(time.monotonic() - started, 1)}
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        done.append(bid)
    progress(1.0, f"Animated {len(done)}, reused {len(skipped)}, failed {len(failed)}")
    return {"animated": done, "reused": skipped, "failed": failed, "workflow": FAST_H3_ID, "workflow_sha256": sha,
            "seconds_each": [log[b]["elapsed_s"] for b in done]}
