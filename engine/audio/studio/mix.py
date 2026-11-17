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

from engine.audio.studio import autolevel
from engine.audio.studio.place import Placement, placement_for
from engine.audio.studio.plan import Cue, SoundPlan, Track

SR = 48000
_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_EFFECT_ROLES = ("sfx", "ambience", "foley")
_DUCK = "sidechaincompress=threshold=0.05:ratio=8:attack=20:release=400"


def _pan_filter(pan: float) -> str:
    """Middle pan across stereo space (-1.0 left to 1.0 right) using constant power."""
    p = max(-1.0, min(1.0, float(pan)))
    return f"stereotools=mpan={p:.3f}:bmode_out=power"


def _duck_filter(depth_db: float = -8.0, attack_ms: int = 20, release_ms: int = 400, threshold: float = 0.05) -> str:
    """Generate dynamic sidechain compression filter string with custom depth and timing."""
    ratio = max(2.0, min(20.0, abs(depth_db)))
    return f"sidechaincompress=threshold={threshold:.5f}:ratio={ratio:.1f}:attack={int(attack_ms)}:release={int(release_ms)}"


def _run(cmd: list[str], timeout: int = 900) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}): {' | '.join(p.stderr.strip().splitlines()[-3:])}")
    return p.stderr


def _track(plan: SoundPlan, role: str) -> Track:
    return next((t for t in plan.tracks if t.id == role), Track(id=role, role=role))


def _cue_chain(plan: SoundPlan, cue: Cue, trim_db: float = 0.0) -> str:
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
    if cue.pitch_semitones and abs(cue.pitch_semitones) >= 0.05:
        pitch_factor = 2.0 ** (cue.pitch_semitones / 12.0)
        f.append(f"rubberband=pitch={pitch_factor:.4f}")
    if cue.hpf_hz and cue.hpf_hz > 10:
        f.append(f"highpass=f={cue.hpf_hz:g}")
    if cue.lpf_hz and cue.lpf_hz < 22000:
        f.append(f"lowpass=f={cue.lpf_hz:g}")
    if cue.gain_db + trim_db:
        f.append(f"volume={cue.gain_db + trim_db:g}dB")
    if cue.fade_in > 0:
        f.append(f"afade=t=in:d={cue.fade_in:.4f}")
    if cue.fade_out > 0:
        f.append(f"afade=t=out:st={max(0.0, length - cue.fade_out):.4f}:d={cue.fade_out:.4f}")
    if cue.pan and abs(cue.pan) >= 0.01:
        f.append(_pan_filter(cue.pan))
    f += [f"adelay={pl.start_s * 1000:.3f}:all=1", f"apad=whole_dur={plan.duration:.6f}", f"atrim=duration={plan.duration:.6f}"]
    return ",".join(f)


def render_cue(plan: SoundPlan, cue: Cue, out: Path, trim_db: float = 0.0) -> Path:
    """The cue alone, placed on the timeline: one wav as long as the video. trim_db: the auto-level correction (render_roles), on top of the cue's gain."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    take = cue.chosen()
    if take is None:
        raise ValueError(f"cue {cue.id!r} has no chosen take")
    _run([_FFMPEG, "-v", "error", "-y", "-i", take.path, "-af", _cue_chain(plan, cue, trim_db),
          "-ac", "2", "-ar", str(SR), "-c:a", "pcm_f32le", str(out)])
    return out


def _sum(out: Path, items: list[tuple[Path, float]], duration: float, sidechain: Path | None = None,
         duck_filter: str | None = None) -> Path:
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
        duck_cmd = duck_filter or _DUCK
        # sidechaincompress drops the last frames when its inputs end together (a different amount every run): pad both, trim after
        parts += [f"[m]apad=whole_dur={duration + 1:.6f}[mp]", f"[{len(items)}:a]apad=whole_dur={duration + 1:.6f}[sp]",
                  f"[mp][sp]{duck_cmd}[d]"]
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
    has_solo = any(t.solo for t in plan.tracks)

    placed: dict[str, list[tuple[Path, float]]] = {"music": [], "effects": [], "beds": [], "voice": []}
    later: list[tuple[Cue, str, float]] = []   # music and effects wait for the dialogue stem: effects are levelled against it
    for cue in plan.cues:
        t = _track(plan, cue.track)
        is_muted = t.mute or (has_solo and not t.solo)
        if cue.chosen() is None or is_muted:
            continue
        if cue.track == "dialogue":
            placed["voice"].append((render_cue(plan, cue, cue_dir / f"{cue.id}.wav"), t.gain_db))
        elif cue.track == "music":
            later.append((cue, "music", t.gain_db))
        else:   # an ambience track or a long span without a hit point is a bed: it ducks under speech; the rest are hits
            bed = cue.track == "ambience" or (cue.hit_t is None and cue.t_out is not None and cue.t_out - cue.t_in >= 2.0)
            later.append((cue, "beds" if bed else "effects", t.gain_db))

    dlg_track = _track(plan, "dialogue")
    dialogue = out_dir / "dialogue.wav"
    dlg_muted = dlg_track.mute or (has_solo and not dlg_track.solo)
    items = list(placed["voice"])   # narration lines
    if plan.keep_original_audio and _has_audio(plan.dialogue_path) and not dlg_muted:
        orig = out_dir / "original.wav"
        dlg_filters = [f"aresample={SR}", f"volume={dlg_track.gain_db:g}dB"]
        if dlg_track.hpf_hz and dlg_track.hpf_hz > 10:
            dlg_filters.append(f"highpass=f={dlg_track.hpf_hz:g}")
        if dlg_track.pan and abs(dlg_track.pan) >= 0.01:
            dlg_filters.append(_pan_filter(dlg_track.pan))
        dlg_filters += [f"apad=whole_dur={D:.6f}", f"atrim=duration={D:.6f}"]
        _run([_FFMPEG, "-v", "error", "-y", "-i", plan.dialogue_path, "-vn", "-af", ",".join(dlg_filters),
              "-ac", "2", "-ar", str(SR), "-c:a", "pcm_f32le", str(orig)])
        items.insert(0, (orig, 0.0))   # its gain is already in the filter chain
    _sum(dialogue, items, D)
    has_dialogue = bool(items)

    music_track = _track(plan, "music")
    custom_duck = (music_track.ducking_depth_db is not None or
                   music_track.ducking_attack_ms is not None or
                   music_track.ducking_release_ms is not None)
    duck_str = _duck_filter(
        depth_db=music_track.ducking_depth_db if music_track.ducking_depth_db is not None else -8.0,
        attack_ms=music_track.ducking_attack_ms if music_track.ducking_attack_ms is not None else 20,
        release_ms=music_track.ducking_release_ms if music_track.ducking_release_ms is not None else 400
    ) if custom_duck else _DUCK

    voice = autolevel.profile(dialogue) if has_dialogue else None
    for cue, group, gain in later:
        trim = autolevel.trim_db(cue, "bed" if group == "beds" else "effects", voice) if group != "music" else 0.0
        placed[group].append((render_cue(plan, cue, cue_dir / f"{cue.id}.wav", trim), gain))

    duck = dialogue if has_dialogue and music_track.duck_under == "dialogue" else None
    music = _sum(out_dir / "music.wav", placed["music"], D, sidechain=duck, duck_filter=duck_str)
    effect_items = list(placed["effects"])
    if placed["beds"]:   # beds sink further under speech than music does, and come back slowly
        beds = _sum(out_dir / "beds.wav", placed["beds"], D, sidechain=dialogue if has_dialogue else None,
                     duck_filter=_duck_filter(-10.0, 30, 500, autolevel.duck_threshold(voice) if voice else 0.05))
        effect_items.append((beds, 0.0))
    effects = _sum(out_dir / "effects.wav", effect_items, D)
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
