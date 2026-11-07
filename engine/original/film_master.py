"""Master of the film: clips -> 1080p picture + clip sound, a ducked local-music bed, captions (SRT), loudness-normalised mp4, and a QA report.

No clip is looped, stretched or held: the cut is the clips in story order, each exactly as long as H3 made it (its length was set by the line it carries).
Music comes from the local ACE-Step service (one cue per scene, `score.py`), sits under the sound of the clips and is ducked by it, so speech stays clear.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from engine.original import ambience, film
from engine.original.models import OriginalStory

SR = 48000
W, H = 1920, 1080
MUSIC_DB = -27.0  # music bed RMS before ducking; the voices sit near -23 dB, so music stays under them (-17 buried the quiet crystal line)
TARGET_LUFS = -16.0


def _run(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{args[0]} failed: {r.stderr[-600:]}")
    return r.stderr + r.stdout


def clip_seconds(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def timeline(story: OriginalStory, ws: Path, ids: list[str] | None = None) -> list[dict]:
    """The cut: shots in story order that have a clip, with start offsets (seconds) in the master."""
    cuts, t = [], 0.0
    for p in story.panels:
        clip = ws / "film" / "clips" / f"{p.id}.mp4"
        if (ids and p.id not in ids) or not clip.exists():
            continue
        d = clip_seconds(clip)
        cuts.append({"id": p.id, "scene": p.scene_id, "clip": clip, "start": round(t, 3), "seconds": round(d, 3), "panel": p})
        t += d
    return cuts


VOICE_MEAN_DB = -23.0  # mean level of the lip-synced voices H3 returns; a voice mixed in at master is brought to it


def voice_gain_db(wav: Path, target: float = VOICE_MEAN_DB, cap: float = 12.0) -> float:
    x, _ = sf.read(str(wav), dtype="float32", always_2d=True)
    rms = float(np.sqrt(np.mean(x ** 2))) or 1e-6
    return float(np.clip(target - 20 * np.log10(rms), 0.0, cap))


def normalize(cut: dict, ws: Path) -> Path:
    """1080p / 24 fps / yuv420p picture and 48 kHz stereo sound with 12 ms edge fades (no clicks at cuts), to an intermediate mkv.
    A silent clip gets the weather its shot describes (`ambience.py`), under the narrator."""
    out = ws.resolve() / "film" / "norm" / f"{cut['id']}.mkv"
    out.parent.mkdir(parents=True, exist_ok=True)
    d = cut["seconds"]
    p = cut["panel"]
    voice = ws / "film" / "voice" / f"{p.id}.wav"
    amb = ambience.ensure(cut["clip"], " ".join([p.atmosphere, p.action, p.end_state]), ws / "film" / "ambience" / f"{p.id}.wav", d, seed=sum(map(ord, p.id)))
    newest = max(cut["clip"].stat().st_mtime, voice.stat().st_mtime if voice.exists() else 0, amb.stat().st_mtime if amb else 0)
    if out.exists() and out.stat().st_mtime >= newest:
        return out
    fade = f"afade=t=in:d=0.012,afade=t=out:st={max(0, d - 0.012):.3f}:d=0.012"
    vf = f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.45:5:5:0.0,fps={film.FPS},format=yuv420p,setsar=1"
    inputs, chains, labels = ["-i", str(cut["clip"])], [f"[0:a]aresample={SR},aformat=channel_layouts=stereo[a0]"], ["[a0]"]
    if p.dialogue and p.dialogue[0].speaker_id in film.FACELESS and voice.exists() and p.id not in native_ids(ws):  # a faceless speaker's TTS voice is laid over the picture
        inputs += ["-i", str(voice)]
        chains.append(f"[{len(labels)}:a]volume={voice_gain_db(voice):.1f}dB,alimiter=limit=0.9,aresample={SR},aformat=channel_layouts=stereo[a{len(labels)}]")
        labels.append(f"[a{len(labels)}]")
    if amb:
        inputs += ["-i", str(amb)]
        chains.append(f"[{len(labels)}:a]aresample={SR},aformat=channel_layouts=stereo[a{len(labels)}]")
        labels.append(f"[a{len(labels)}]")
    mix = f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0,{fade}[a]" if len(labels) > 1 else f"[a0]{fade}[a]"
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-vf", vf, "-filter_complex", ";".join(chains + [mix]),
          "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-c:a", "pcm_s16le", str(out)])
    return out


def concat(cuts: list[dict], ws: Path) -> Path:
    lst = ws / "film" / "norm" / "list.txt"
    lst.write_text("".join(f"file '{normalize(c, ws).as_posix()}'\n" for c in cuts), encoding="utf-8")
    out = ws / "film" / "norm" / "cut.mkv"
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out


def music_bed(cuts: list[dict], ws: Path, cues: dict[str, Path], total: float) -> Path:
    """One wav the length of the film: each scene's cue starts at the scene's first shot, fades in over 1.2 s and out over 3 s into the next scene's cue."""
    n = int(total * SR)
    bed = np.zeros((n, 2), dtype=np.float32)
    scenes: dict[str, float] = {}
    for c in cuts:
        scenes.setdefault(c["scene"], c["start"])
    order = list(scenes)
    for k, sc in enumerate(order):
        cue = cues.get(sc)
        if cue is None or not cue.exists():
            continue
        tmp = ws / "film" / "audio" / f"_{sc}.wav"
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(cue), "-ar", str(SR), "-ac", "2", str(tmp)])
        x, _ = sf.read(str(tmp), dtype="float32", always_2d=True)
        tmp.unlink(missing_ok=True)
        start = int(scenes[sc] * SR)
        end = int((scenes[order[k + 1]] if k + 1 < len(order) else total) * SR)
        span = min(len(x), end - start + 3 * SR if k + 1 < len(order) else end - start)  # a cue runs 3 s into the next scene, then is gone
        x = x[:span]
        if len(x) < 4 * SR:
            continue
        rms = float(np.sqrt(np.mean(x ** 2))) or 1.0
        x = x * (10 ** (MUSIC_DB / 20) / rms)
        fi, fo = int(1.2 * SR), min(len(x), int(3.0 * SR))
        x[:fi] *= np.linspace(0, 1, fi)[:, None]
        x[-fo:] *= np.linspace(1, 0, fo)[:, None]
        seg = bed[start:start + len(x)]
        seg += x[: len(seg)]
    peak = float(np.max(np.abs(bed))) or 1.0
    if peak > 0.9:
        bed *= 0.9 / peak
    out = ws / "film" / "audio" / "music_bed.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), bed, SR, subtype="PCM_16")
    return out


def spoken_span(wav: Path) -> tuple[float, float]:
    """(first, last) second with speech in a shot's voice wav."""
    x, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    m = np.abs(x).mean(axis=1)
    idx = np.flatnonzero(m > 0.02 * max(float(m.max()), 1e-6))
    return (idx[0] / sr, idx[-1] / sr) if idx.size else (0.0, 0.0)


def native_ids(ws: Path) -> set[str]:
    """Shots whose clip carries H3's own generated voice: clips.json `native_voice`, or (older log entries) the native prompt's soundscape sentence."""
    f = ws / "film" / "clips.json"
    return {k for k, v in json.loads(f.read_text(encoding="utf-8")).items() if v.get("native_voice") or "speaks the line aloud" in v.get("prompt", "")} if f.exists() else set()


def clip_speech_span(clip: Path) -> tuple[float, float]:
    """(first, last) second of speech in a clip's own sound: 20 ms RMS frames above 4x the quiet floor and 15% of the loudest."""
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(clip), "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    n = 320
    rms = np.sqrt(np.mean(x[: len(x) // n * n].reshape(-1, n) ** 2, axis=1)) if len(x) >= n else np.zeros(1)
    idx = np.flatnonzero(rms > max(4 * float(np.percentile(rms, 20)), 0.15 * float(rms.max()), 1e-5))
    return (idx[0] * n / 16000, (idx[-1] + 1) * n / 16000) if idx.size else (0.0, 0.0)


def srt(cuts: list[dict], ws: Path) -> str:
    def stamp(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    rows, native = [], native_ids(ws)
    for c in cuts:
        p = c["panel"]
        wav = ws / "film" / "voice" / f"{p.id}.wav"
        if not p.dialogue or not (p.id in native or wav.exists()):
            continue
        a, b = clip_speech_span(c["clip"]) if p.id in native else spoken_span(wav)
        rows.append((c["start"] + a, c["start"] + b + 0.15, p.dialogue[0].text))
    return "".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(rows, 1))


TITLE_FONT = r"C\:/Windows/Fonts/impact.ttf"  # ffmpeg filter syntax: the drive colon is escaped


def title_filter(title: str, total: float, at: float = 6.0) -> str:
    """Opening title (fades in at `at`, holds, fades out) and a closing card over the last shot's final seconds; drawn on the picture, nothing is added to the cut."""
    t = title.replace("'", "").replace(":", " ")
    a = f"if(lt(t,{at}),0,if(lt(t,{at + 1}),t-{at},if(lt(t,{at + 3.5}),1,if(lt(t,{at + 4.5}),{at + 4.5}-t,0))))"
    e0 = max(0.0, total - 4.0)
    b = f"if(lt(t,{e0}),0,if(lt(t,{e0 + 1}),t-{e0},1))"
    common = f"fontfile='{TITLE_FONT}':fontcolor=white:shadowcolor=black@0.7:shadowx=5:shadowy=5:x=(w-text_w)/2"
    return (f"drawtext=text='{t.upper()}':fontsize=104:y=h*0.06:alpha='{a}':{common},"
            f"drawtext=text='{t.upper()}':fontsize=96:y=h*0.44:alpha='{b}':{common},"
            f"drawtext=text='Made with PanelFlow Studio':fontsize=34:y=h*0.58:alpha='{b}':{common}")


def render(story: OriginalStory, ws: Path, cues: dict[str, Path] | None = None, ids: list[str] | None = None, name: str = "film_master",
           title: str = "") -> dict:
    cuts = timeline(story, ws, ids)
    if not cuts:
        raise ValueError("no clips to cut")
    total = cuts[-1]["start"] + cuts[-1]["seconds"]
    cut = concat(cuts, ws)
    out = ws / f"{name}.mp4"
    base = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(cut)]
    if cues:
        bed = music_bed(cuts, ws, cues, total)
        fc = ("[0:a]asplit=2[sc][dry];[1:a]volume=1.0[m];[m][sc]sidechaincompress=threshold=0.01:ratio=10:attack=10:release=500:makeup=1[duck];"
              f"[dry][duck]amix=inputs=2:duration=first:normalize=0,loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11[a]")
        if title:
            fc = f"[0:v]{title_filter(title, total)}[v];" + fc
        args = base + ["-i", str(bed), "-filter_complex", fc, "-map", "[v]" if title else "0:v", "-map", "[a]"]
    else:
        args = base + (["-vf", title_filter(title, total)] if title else []) + ["-af", f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11", "-map", "0:v", "-map", "0:a"]
    _run(args + ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart", str(out)])
    (ws / f"{name}.srt").write_text(srt(cuts, ws), encoding="utf-8")
    return {"video": str(out), "seconds": round(total, 2), "shots": len(cuts), "music": bool(cues), "srt": str(ws / f"{name}.srt")}


def loudness(path: Path) -> dict:
    out = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"])
    g = lambda k: float(re.findall(rf"{k}:\s+(-?[\d.]+)", out)[-1])
    return {"integrated_lufs": g("I"), "lra": g("LRA"), "true_peak_dbfs": g("Peak")}
