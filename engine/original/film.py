"""Animated anime film from a shot list: 16:9 first frames, character voices anchored to the speaking face, H3 clips, music, one master.

Why this exists (owner's brief, 2026-11-06): the earlier video showed stills, looped (ping-pong) a few clips and put a narrator over everything.
A film needs a different contract:
  * every shot is its own H3 clip made from its own first frame - nothing is looped, nothing is a still;
  * a character speaks with a voice that belongs to that character (Kokoro, one fixed voice per character), and that exact audio is anchored
    into H3 (`MiniMaxH3AddGuide`) so the mouth is generated to the words - measured: ASR of the clip returns the line, mouth motion follows it;
  * no narrator; the score is local ACE-Step music (see `score.py` in the film step), ducked under speech.

Stages are resumable: each leaves files under `<workspace>/film/` and skips what is already there.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Callable

import numpy as np

from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
from engine.comfyui.art import ArtEngine
from engine.narration.runtime import audio as rt
from engine.original import art as art_mod
from engine.original.animate import release_ollama
from engine.original.models import OriginalStory, Panel
from engine.original.shotspec import CharPose, ShotSpec

FRAME = (1344, 768)  # every first frame is 16:9, whatever the shot size (close-ups are framed tight inside it)
FPS = 24
FREE_ID, VOICE_ID = "fastvideo_h3_film_free", "fastvideo_h3_film_voice"
LEAD_SEC, TAIL_SEC = 0.15, 0.45  # silence before the first word and after the last, so the mouth closes before the cut
PEAK = 0.7  # voice peak (linear) = about -3 dBFS
DEFAULT_VOICES = {  # character id -> (Kokoro voice, speed). Overridable per story in film/voices.json.
    "mira": ("af_bella", 1.0), "rook": ("am_adam", 1.0), "oren": ("bm_fable", 0.9), "crystal": ("af_heart", 0.8)}
VOICE_FX = {"crystal": "aecho=0.8:0.6:90|180:0.4|0.25,highpass=f=140"}  # a disembodied echo for the crystal's voice
HOLD = {"extreme_close": 2.3, "close": 3.0, "medium": 3.75, "wide": 4.45}  # silent-shot length by shot size (seconds, before the H3 frame grid)
CAMERA = {"extreme_close": "a very slight, slow push-in", "close": "a slow, steady push-in", "medium": "a slow, steady push-in",
          "wide": "a smooth camera that follows the motion"}


def film_dir(ws: Path) -> Path:
    d = ws / "film"
    for sub in ("frames", "voice", "clips"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def snap_frames(seconds: float) -> int:
    """H3 renders 17k+5 frames at 24 fps (the graph's own rule: x + (5 - x % 17) % 17)."""
    x = max(5, round(seconds * FPS))
    return x + (5 - x % 17) % 17


# ------------------------------------------------------------------ first frames
def film_spec(story: OriginalStory, panel: Panel) -> ShotSpec:
    """A complete ShotSpec from the shot's authored description: no LLM in the loop (the 9B director failed or fell back on 4 of 9 shots and took 23 s
    each; the description is already concrete). The speaker is in frame with the mouth mid-word, so the voice has a face to move."""
    sides = ["center"] if len(panel.character_ids) == 1 else ["left", "center", "right"] if len(panel.character_ids) >= 3 else ["left", "right"]
    speaker = panel.dialogue[0].speaker_id if panel.dialogue else ""
    cast = []
    for k, cid in enumerate(panel.character_ids[:3]):
        cast.append(CharPose(id=cid, side=sides[k], pose="", expression="speaking, mouth open mid-sentence" if cid == speaker else "",
                             action=panel.action if k == 0 else ""))
    scene = next((s for s in story.scenes if s.id == panel.scene_id), None)
    loc = next((x for x in story.bible.locations if x.id == panel.location_id), None)
    where = loc.name if loc else ""
    if not cast:  # a shot with nobody in it (landscape, object): the description is the scene
        where = f"{where}. {panel.action}" if where else panel.action
    return ShotSpec(shot=panel.shot, camera=panel.angle, setting=where, lighting="", mood=scene.mood if scene else "",
                    key_visuals=panel.key_visuals, characters=cast)


def frame_prompt(story: OriginalStory, panel: Panel) -> tuple[str, str]:
    directed = panel.model_copy(update={"director": film_spec(story, panel).model_dump()})
    return art_mod.build_prompt(story, directed, style="natural", engine="qwen")


def make_frames(story: OriginalStory, ws: Path, runner, ids: list[str] | None = None, rerolls: dict[str, int] | None = None,
                progress: Callable[[float, str], None] = lambda p, m: None, is_cancelled: Callable[[], bool] = lambda: False) -> dict:
    """One 16:9 picture per shot through the single art workflow. `rerolls` maps a shot id to its attempt number (a new seed); a picture that
    exists with the same prompt and attempt is reused."""
    fd = film_dir(ws)
    log_path = fd / "frames.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    todo = [p for p in story.panels if not ids or p.id in ids]
    done = reused = 0
    for n, p in enumerate(todo, 1):
        if is_cancelled():
            raise RuntimeError("cancelled")
        attempt = (rerolls or {}).get(p.id, log.get(p.id, {}).get("attempt", 0))
        pos, neg = frame_prompt(story, p)
        sig = hashlib.sha256(f"{pos}|{neg}|{attempt}".encode()).hexdigest()[:16]
        img = fd / "frames" / f"{p.id}.png"
        if img.exists() and log.get(p.id, {}).get("sig") == sig:
            reused += 1
            continue
        progress(n / len(todo), f"Frame {p.id} ({n}/{len(todo)})")
        seed = art_mod.seed_for(story, p.id, attempt)
        img.write_bytes(runner.generate(pos, neg, seed, FRAME[0], FRAME[1], f"film_{p.id}"))
        log[p.id] = {"sig": sig, "attempt": attempt, "seed": seed, "prompt": pos}
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        done += 1
    return {"generated": done, "reused": reused}


# ------------------------------------------------------------------ voices
def film_voices(story: OriginalStory, ws: Path) -> dict[str, tuple[str, float]]:
    from engine.original.video import voices_for

    _, auto = voices_for(story)
    out = {**auto, **DEFAULT_VOICES}
    f = ws / "film" / "voices.json"
    if f.exists():
        out.update({k: tuple(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()})
    return out


def line_rate(text: str, rate: float) -> float:
    """A touch of delivery from the punctuation: shouted lines run a little faster, hesitant ones slower."""
    t = text.strip()
    return round(rate * (1.07 if t.endswith("!") else 0.93 if t.endswith("...") or "..." in t else 1.0), 3)


def _fx(wav: Path, filt: str) -> None:
    tmp = wav.with_suffix(".fx.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", filt, "-ar", str(rt.SR), "-ac", "1", str(tmp)], check=True)
    tmp.replace(wav)


def voice_shot(story: OriginalStory, ws: Path, panel: Panel, tts=None, voices=None) -> tuple[Path, float] | None:
    """The shot's spoken line as one wav, padded so its length is exactly the H3 frame grid. Returns (wav, clip_seconds) or None for a silent shot."""
    if not panel.dialogue:
        return None
    ln = panel.dialogue[0]
    voices = voices or film_voices(story, ws)
    voice, rate = voices.get(ln.speaker_id, ("af_bella", 1.0))
    tts = tts or rt.KokoroTts()
    audio, _, _ = rt.normalize_silence(tts.synth(ln.text, voice, line_rate(ln.text, rate)))
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0:
        audio = audio * (PEAK / peak)
    lead, tail = int(LEAD_SEC * rt.SR), int(TAIL_SEC * rt.SR)
    frames = snap_frames((lead + len(audio) + tail) / rt.SR)
    total = int(round(frames / FPS * rt.SR))
    full = np.zeros(total, dtype=np.float32)
    full[lead:lead + len(audio)] = audio.astype(np.float32)[: max(0, total - lead)]
    out = film_dir(ws) / "voice" / f"{panel.id}.wav"
    rt.write_wav_atomic(out, full)
    if ln.speaker_id in VOICE_FX:
        _fx(out, VOICE_FX[ln.speaker_id])
    return out, frames / FPS


def silent_shot(ws: Path, panel: Panel) -> tuple[Path, float]:
    """A silent wav on the H3 frame grid for a shot that must carry no voice at all."""
    seconds = snap_frames(HOLD.get(panel.shot, 3.75)) / FPS
    out = film_dir(ws) / "voice" / f"{panel.id}.silent.wav"
    rt.write_wav_atomic(out, np.zeros(int(round(seconds * rt.SR)), dtype=np.float32))
    return out, seconds


# ------------------------------------------------------------------ motion prompt and clips
def motion_prompt(story: OriginalStory, panel: Panel) -> str:
    """H3 text for one shot: only the motion (the picture already carries how everyone looks, and re-describing it makes faces melt)."""
    names = {c.id: c.name for c in story.bible.characters}
    cam = CAMERA.get(panel.shot, CAMERA["medium"])
    motion = panel.motion.rstrip(".")
    vehicle = "flying machine" in panel.motion + panel.action
    if vehicle:  # H3 reads "flying machine" as a real aircraft and swaps in jets or propeller planes: name what it is
        motion = motion.replace("flying machines", "cloth-winged gliders").replace("flying machine", "cloth-winged glider")
    parts = [f"{motion}.", f"The camera does {cam}.",
             "Single continuous take, anime film animation, smooth natural motion, consistent character appearance in every frame."]
    if vehicle:
        parts.append("The vehicles are hand-built wooden gliders with big patched canvas wings in a fantasy anime world: no jets, no airplanes, no propellers, no modern aircraft.")
    if panel.dialogue:
        ln = panel.dialogue[0]
        parts.insert(1, f"{names.get(ln.speaker_id, ln.speaker_id)}'s lips move in exact sync with the words, with natural blinks, expressive eyebrows and small head movements. "
                        f"{names.get(ln.speaker_id, ln.speaker_id)} says: \"{ln.text}\"")
        sound = "only the spoken voice, no other sound."
    else:
        sound = "realistic sound effects that match the action (wind, footsteps, rustle, impacts, creaks), no speech, no singing."
    return ("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
            f"integrated_multimodal_description: [Shot 1] {' '.join(parts)}\n\noverall_soundscape: {sound}\n\nnon_diegetic_music: none.")


def _apply(workflow: dict, slots: dict, values: dict) -> dict:
    import copy

    g = copy.deepcopy(workflow)
    for name, value in values.items():
        s = slots[name]
        g[str(s["node_id"])]["inputs"][s["input"]] = value
    return g


def clip_stats(path: Path) -> dict:
    """Frames, duration, audio present, and how much the picture moves (mean absolute difference between neighbouring frames, 0-255 gray)."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    prev, diffs, n = None, [], 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(f, (192, 108)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        if prev is not None:
            diffs.append(float(np.abs(g - prev).mean()))
        prev, n = g, n + 1
        first = g if n == 1 else first
    cap.release()
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return {"frames": n, "seconds": round(n / FPS, 2), "has_audio": "audio" in probe,
            "motion": round(float(np.mean(diffs)), 3) if diffs else 0.0, "motion_min_window": round(float(np.min(np.convolve(diffs, np.ones(12) / 12, "valid"))), 3) if len(diffs) > 12 else 0.0,
            "drift": round(float(np.abs(g - first).mean()), 2) if n > 1 else 0.0}


MIN_MOTION = 0.9  # mean frame-to-frame difference below this reads as a still picture (measured: a calm talking close-up is ~2, a held frame ~0.1)


def make_clips(story: OriginalStory, ws: Path, ids: list[str] | None = None, seeds: dict[str, int] | None = None, client: ComfyUIClient | None = None,
               timeout: float = 1500.0, progress: Callable[[float, str], None] = lambda p, m: None, is_cancelled: Callable[[], bool] = lambda: False,
               free_llm_memory: bool = True, quiet: list[str] | None = None) -> dict:
    """`film/clips/<shot>.mp4` (video + its own audio) for each shot with a frame. A clip newer than its frame, voice and prompt is reused; a clip
    that fails or comes out still is reported and the others continue. `quiet` = shots whose sound is anchored to silence: H3 sometimes invents speech
    (an unscripted voice) in a silent shot; a retry with a new seed usually fixes it, silence always does (at the cost of its sound effects)."""
    from engine.comfyui.service import _history_videos

    fd = film_dir(ws)
    client = client or ComfyUIClient()
    registry = ComfyWorkflowRegistry(client)
    for wid in (FREE_ID, VOICE_ID):
        pre = registry.preflight(wid)
        if not pre["ready"]:
            raise RuntimeError(f"ComfyUI workflow {wid} is not ready: nodes {pre['missing_nodes']}, models {pre['missing_models']}")
    wf = {wid: (registry.load(wid), registry.metadata(wid)["patch_slots"]) for wid in (FREE_ID, VOICE_ID)}
    engine = ArtEngine(client, registry)
    log_path = fd / "clips.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else {}
    tts, voices = rt.KokoroTts(), film_voices(story, ws)
    todo = [p for p in story.panels if (not ids or p.id in ids) and (fd / "frames" / f"{p.id}.png").exists()]
    if free_llm_memory:
        release_ollama()
    done, reused, failed, still = [], [], [], []
    for n, p in enumerate(todo, 1):
        if is_cancelled():
            raise RuntimeError("cancelled")
        frame, out = fd / "frames" / f"{p.id}.png", fd / "clips" / f"{p.id}.mp4"
        spoken = voice_shot(story, ws, p, tts, voices)
        if spoken is None and p.id in (quiet or []):
            spoken = silent_shot(ws, p)
        seconds = spoken[1] if spoken else snap_frames(HOLD.get(p.shot, 3.75)) / FPS
        prompt = motion_prompt(story, p)
        seed = (seeds or {}).get(p.id, int(hashlib.sha256(f"{story.bible.premise.title}|{p.id}|clip".encode()).hexdigest()[:12], 16))
        sig = hashlib.sha256(f"{prompt}|{seed}|{seconds}|{frame.stat().st_mtime_ns}|{spoken[0].stat().st_mtime_ns if spoken else 0}".encode()).hexdigest()[:16]
        if out.exists() and log.get(p.id, {}).get("sig") == sig:
            reused.append(p.id)
            continue
        progress((n - 1) / len(todo), f"Clip {p.id} ({n}/{len(todo)})")
        (workflow, _sha), slots = wf[VOICE_ID if spoken else FREE_ID]
        values = {"prompt": prompt, "seed": seed, "filename_prefix": f"video/film_{p.id}", "reference_image": client.upload_image(frame), "duration": seconds}
        if spoken:
            values["voice_audio"] = client.upload_audio(spoken[0])
        started = time.monotonic()
        try:
            raw, prompt_id, _ = engine.run(_apply(workflow, slots, values), timeout=timeout, is_cancelled=is_cancelled, collect=_history_videos)
        except Exception as exc:
            if str(exc).startswith("Image generation cancelled"):
                raise RuntimeError("cancelled")
            failed.append({"shot": p.id, "error": str(exc)[:200]})
            continue
        out.write_bytes(raw)
        stats = clip_stats(out)
        log[p.id] = {"sig": sig, "seed": seed, "seconds": seconds, "prompt": prompt, "workflow": VOICE_ID if spoken else FREE_ID, "prompt_id": prompt_id,
                     "elapsed_s": round(time.monotonic() - started, 1), "stats": stats}
        log_path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        done.append(p.id)
        if stats["motion"] < MIN_MOTION:
            still.append(p.id)
    progress(1.0, f"Clips: {len(done)} made, {len(reused)} reused, {len(failed)} failed, {len(still)} too still")
    return {"made": done, "reused": reused, "failed": failed, "too_still": still}
