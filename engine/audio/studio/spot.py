"""Spotting: find where the picture changes and draft the cues that belong there."""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from engine.audio.studio.plan import Cue, SoundPlan, snap

_PTS = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")
OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3.5:9b"


def detect_cuts(video: Path, threshold: float = 0.3) -> list[float]:
    """Scene-change times (seconds) from ffmpeg's scene score; cuts closer than 0.15 s count once."""
    proc = subprocess.run(
        [shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-i", str(video), "-an",
         "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg scene detection failed: {proc.stderr.strip().splitlines()[-1:]}")
    cuts: list[float] = []
    for t in sorted(float(m) for m in _PTS.findall(proc.stderr)):
        if not cuts or t - cuts[-1] >= 0.15:
            cuts.append(t)
    return cuts


def extract_keyframe(video: Path, timestamp: float, out_jpg: Path) -> bool:
    """Extract a single frame image around timestamp for visual analysis."""
    cmd = [
        shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(0.0, timestamp):.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "4", str(out_jpg)
    ]
    res = subprocess.run(cmd, capture_output=True, timeout=30)
    return res.returncode == 0 and out_jpg.is_file() and out_jpg.stat().st_size > 0


def analyze_frame_sound(jpg_path: Path, timeout: float = 12.0) -> dict | None:
    """Ask local Ollama vision model to name the sound effect or ambience in the frame."""
    try:
        b64 = base64.b64encode(jpg_path.read_bytes()).decode("utf-8")
        prompt = (
            "Look at this frame from a video. Identify the most prominent visual action, object, or environment that makes a sound "
            "(e.g. car engine running, sword clash, door closing, footsteps on wood, heavy rain, body impact, monster roar, quiet room). "
            "Respond ONLY with a JSON object: {\"role\": \"sfx\"|\"ambience\"|\"foley\", \"kind\": \"<single_word_genre>\", \"intent\": \"<3 to 6 words plain description>\"}"
        )
        payload = json.dumps({"model": OLLAMA_MODEL, "prompt": prompt, "images": [b64], "stream": False}).encode("utf-8")
        req = urllib.request.Request(f"{OLLAMA_ENDPOINT}/api/generate", data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data.get("response", "")
            m = re.search(r"\{[^{}]*\"intent\"[^{}]*\}", text)
            if m:
                parsed = json.loads(m.group(0))
                role = str(parsed.get("role", "sfx")).lower()
                if role not in ("dialogue", "music", "sfx", "ambience", "foley"):
                    role = "sfx"
                return {
                    "role": role,
                    "kind": re.sub(r"[^a-zA-Z0-9_-]", "", str(parsed.get("kind", "sfx")).lower()) or "sfx",
                    "intent": str(parsed.get("intent", "")).strip()[:100]
                }
    except Exception:
        return None
    return None


def draft_cues(plan: SoundPlan, cuts: list[float], use_vision: bool = False, video_path: Path | None = None) -> list[Cue]:
    """Draft cues for cuts and video underscore. If use_vision is True, uses Ollama vision on keyframes."""
    cues = []
    with tempfile.TemporaryDirectory(prefix="spot-frames-") as tmp:
        tmp_dir = Path(tmp)
        for idx, t in enumerate(cuts):
            if not 0 < t <= plan.duration:
                continue
            hit = min(snap(t, plan.fps), plan.duration)
            cid = f"cut_{len(cues) + 1:02d}"

            sound_info = None
            if use_vision and video_path and video_path.is_file():
                frame_jpg = tmp_dir / f"frame_{idx:03d}.jpg"
                if extract_keyframe(video_path, hit, frame_jpg):
                    sound_info = analyze_frame_sound(frame_jpg)

            if sound_info and sound_info.get("intent"):
                role = sound_info["role"]
                kind = sound_info["kind"]
                intent = sound_info["intent"]
                anchor = "onset" if kind in ("impact", "click", "pop", "foley", "hit") else "peak"
                cues.append(Cue(id=cid, track=role, kind=kind, anchor=anchor, hit_t=hit,
                                t_in=max(0.0, hit - 0.5), intent=intent))
            else:
                cues.append(Cue(id=cid, track="sfx", kind="whoosh", anchor="peak", hit_t=hit,
                                t_in=max(0.0, hit - 0.5), intent=f"transition whoosh into the cut at {hit:.2f}s"))

    cues.append(Cue(id="music_1", track="music", kind="music", t_in=0.0, t_out=plan.duration, intent="instrumental underscore"))
    return cues
