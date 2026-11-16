"""Mix a Sound Plan with ffmpeg: place each cue, build dialogue/music/effects stems (music ducked under dialogue), master to a loudness target.

Every intermediate file is 48 kHz stereo float32 wav, so stems add up exactly; only the master is limited and normalised.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from engine.audio.studio.place import Placement, placement_for
from engine.audio.studio.plan import Cue, SoundPlan, Track

SR = 48000
_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_EFFECT_ROLES = ("sfx", "ambience", "foley")
_DUCK = "sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400"


def _run(cmd: list[str], timeout: int = 900) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}): {' | '.join(p.stderr.strip().splitlines()[-3:])}")
    return p.stderr


def _track(plan: SoundPlan, role: str) -> Track:
    return next((t for t in plan.tracks if t.id == role), Track(id=role, role=role))


def _cue_chain(plan: SoundPlan, cue: Cue) -> str:
    take = cue.chosen()
    if take is None:
        raise ValueError(f"cue {cue.id!r} has no chosen take")
    anchor = take.peak_s if cue.anchor == "peak" else take.onset_s
    pl = placement_for(cue.hit_t, anchor) if cue.hit_t is not None else Placement(cue.t_in, 0.0)
    span = (cue.t_out - cue.t_in) if cue.t_out is not None else None
    avail = max(take.duration_s - pl.trim_s, 0.01)
    f = [f"aresample={SR}"]
    if pl.trim_s > 0:
        f.append(f"atrim=start={pl.trim_s:.6f},asetpts=PTS-STARTPTS")
    if span is not None and avail < span - 0.01:  # a bed shorter than its span repeats, with soft edges so the seam does not click
        edge = min(0.05, avail / 4)
        f += [f"afade=t=in:d={edge:.4f}", f"afade=t=out:st={avail - edge:.4f}:d={edge:.4f}",
              f"aloop=loop=-1:size={int(avail * SR) + 1}"]
    if span is not None:
        f.append(f"atrim=duration={span:.6f}")
    length = span if span is not None else avail
    if cue.gain_db:
        f.append(f"volume={cue.gain_db:g}dB")
    if cue.fade_in > 0:
        f.append(f"afade=t=in:d={cue.fade_in:.4f}")
    if cue.fade_out > 0:
        f.append(f"afade=t=out:st={max(0.0, length - cue.fade_out):.4f}:d={cue.fade_out:.4f}")
    f += [f"adelay={pl.start_s * 1000:.3f}:all=1", f"apad=whole_dur={plan.duration:.6f}", f"atrim=duration={plan.duration:.6f}"]
    return ",".join(f)


def render_cue(plan: SoundPlan, cue: Cue, out: Path) -> Path:
    """The cue alone, placed on the timeline: one wav as long as the video."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    take = cue.chosen()
    if take is None:
        raise ValueError(f"cue {cue.id!r} has no chosen take")
    _run([_FFMPEG, "-v", "error", "-y", "-i", take.path, "-af", _cue_chain(plan, cue),
          "-ac", "2", "-ar", str(SR), "-c:a", "pcm_f32le", str(out)])
    return out


def _sum(out: Path, items: list[tuple[Path, float]], duration: float, sidechain: Path | None = None) -> Path:
    """Add wavs (each with a gain in dB) without scaling; optionally duck the sum under `sidechain`."""
    cmd = [_FFMPEG, "-v", "error", "-y"]
    if not items:
        cmd += ["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-t", f"{duration:.6f}", "-c:a", "pcm_f32le", str(out)]
        _run(cmd)
        return out
    for p, _ in items:
        cmd += ["-i", str(p)]
    parts = [f"[{i}:a]volume={g:g}dB[a{i}]" for i, (_, g) in enumerate(items)]
    parts.append("".join(f"[a{i}]" for i in range(len(items))) + f"amix=inputs={len(items)}:normalize=0:duration=longest[m]")
    last = "m"
    if sidechain is not None:
        cmd += ["-i", str(sidechain)]
        # sidechaincompress drops the last frames when its inputs end together (a different amount every run): pad both, trim after
        parts += [f"[m]apad=whole_dur={duration + 1:.6f}[mp]", f"[{len(items)}:a]apad=whole_dur={duration + 1:.6f}[sp]",
                  f"[mp][sp]{_DUCK}[d]"]
        last = "d"
    parts.append(f"[{last}]atrim=duration={duration:.6f}[o]")
    _run(cmd + ["-filter_complex", ";".join(parts), "-map", "[o]", "-ac", "2", "-ar", str(SR), "-c:a", "pcm_f32le", str(out)])
    return out


def _has_audio(path: str | None) -> bool:
    if not path or not Path(path).is_file():
        return False
    from engine.chronoflow.media_tools import probe
    return bool(probe(Path(path)).get("has_audio"))


def render_roles(plan: SoundPlan, out_dir: Path) -> dict[str, Path]:
    """dialogue.wav, music.wav (ducked under dialogue), effects.wav and premix.wav = their sum."""
    out_dir = Path(out_dir)
    cue_dir = out_dir / "cues"
    cue_dir.mkdir(parents=True, exist_ok=True)
    D = plan.duration
    placed: dict[str, list[tuple[Path, float]]] = {"music": [], "effects": [], "voice": []}
    for cue in plan.cues:
        t = _track(plan, cue.track)
        if cue.chosen() is None or t.mute:
            continue
        group = "voice" if cue.track == "dialogue" else "music" if cue.track == "music" else "effects"
        placed[group].append((render_cue(plan, cue, cue_dir / f"{cue.id}.wav"), t.gain_db))

    dlg_track = _track(plan, "dialogue")
    dialogue = out_dir / "dialogue.wav"
    items = list(placed["voice"])   # narration lines
    if plan.keep_original_audio and _has_audio(plan.dialogue_path) and not dlg_track.mute:
        orig = out_dir / "original.wav"
        _run([_FFMPEG, "-v", "error", "-y", "-i", plan.dialogue_path, "-vn",
              "-af", f"aresample={SR},apad=whole_dur={D:.6f},atrim=duration={D:.6f}", "-ac", "2", "-ar", str(SR), "-c:a", "pcm_f32le", str(orig)])
        items.insert(0, (orig, dlg_track.gain_db))
    _sum(dialogue, items, D)
    has_dialogue = bool(items)
    duck = dialogue if has_dialogue and _track(plan, "music").duck_under == "dialogue" else None
    music = _sum(out_dir / "music.wav", placed["music"], D, sidechain=duck)
    effects = _sum(out_dir / "effects.wav", placed["effects"], D)
    premix = _sum(out_dir / "premix.wav", [(dialogue, 0.0), (music, 0.0), (effects, 0.0)], D)
    return {"dialogue": dialogue, "music": music, "effects": effects, "premix": premix}


def measure_loudness(path: Path) -> dict:
    err = _run([_FFMPEG, "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"])
    summary = err[err.rfind("Summary:"):]
    def num(pat: str) -> float:
        v = re.findall(pat, summary)[-1]
        return -120.0 if v == "-inf" else float(v)  # a silent file measures -inf

    return {"integrated_lufs": num(r"I:\s+(-?\d+\.\d+|-inf) LUFS"), "lra": num(r"LRA:\s+(\d+\.\d+) LU"),
            "true_peak_db": num(r"Peak:\s+(-?\d+\.\d+|-inf) dBFS")}


def render_master(plan: SoundPlan, out_wav: Path, target_lufs: float = -14.0, video_in: Path | None = None,
                  out_video: Path | None = None, roles: dict[str, Path] | None = None) -> dict:
    """Premix -> limiter -> two-pass loudnorm (same filter the Deliver page uses) -> optional mux onto the video.
    Pass `roles` (from render_roles) to reuse already rendered stems."""
    from engine.chronoflow.deliver import loudnorm_filter
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audiostudio-") as tmp:
        premix = (roles or render_roles(plan, Path(tmp)))["premix"]
        limit = "alimiter=limit=0.89"
        first = _run([_FFMPEG, "-hide_banner", "-nostats", "-i", str(premix), "-af",
                      f"{limit},{loudnorm_filter(target_lufs, None)}:print_format=json", "-f", "null", "-"])
        stats = json.loads(first[first.rfind("{"):first.rfind("}") + 1])
        if not math.isfinite(float(stats["input_i"])):
            raise ValueError("nothing to mix: the plan has no dialogue and no ready cue")
        _run([_FFMPEG, "-v", "error", "-y", "-i", str(premix), "-af", f"{limit},{loudnorm_filter(target_lufs, stats)}",
              "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", str(out_wav)])
    result = measure_loudness(out_wav)
    if video_in and out_video:
        _run([_FFMPEG, "-v", "error", "-y", "-i", str(video_in), "-i", str(out_wav), "-map", "0:v", "-map", "1:a",
              "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out_video)])
    return result
