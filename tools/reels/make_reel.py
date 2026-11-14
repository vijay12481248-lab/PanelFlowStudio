"""Produce the Shorts/Reels in tools/reels/specs.py with the local PanelFlow models.

  python tools/reels/make_reel.py <stage> [slug ...]      stages: tts music art clips assemble status
  Order matters for the 16 GB GPU: tts -> music -> art -> clips (one model family at a time), assemble is CPU/ffmpeg only.

Models: Qwen3-TTS (voice clone, D:\\Tools\\Qwen3-TTS) · ACE-Step 1.5 (instrumental bed) · Qwen Image 2.1 Turbo (ArtEngine) ·
MiniMax FastH3 image-to-video (workflow fastvideo_h3_i2v). Everything is resumable: an existing file is never redone, and a missing
model fails loudly (no silent fallback to another TTS).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from specs import NEGATIVE, NO_REF, REELS, STYLE  # noqa: E402

OUT = ROOT / "output" / "reels"
SR = 48000
W, H = 1080, 1920
QWEN_PY = Path(os.environ.get("PANELFLOW_QWEN3_TTS_PYTHON", r"D:\Tools\Qwen3-TTS\.venv\Scripts\python.exe"))
QWEN_RUNNER = Path(os.environ.get("PANELFLOW_QWEN3_TTS_RUNNER", r"D:\Tools\Qwen3-TTS\runner.py"))
VOICE_DIR = Path(os.environ["LOCALAPPDATA"]) / "PanelFlow Studio" / "voice_references"
FONT = "Impact"


def pick(slugs: list[str]) -> list[dict]:
    chosen = [r for r in REELS if not slugs or any(r["slug"].startswith(s) for s in slugs)]
    if not chosen:
        sys.exit(f"no reel matches {slugs}")
    return chosen


def ridx(reel: dict) -> int:
    return [x["slug"] for x in REELS].index(reel["slug"])


def rdir(reel: dict, *sub: str) -> Path:
    p = OUT / reel["slug"]
    for s in sub:
        p = p / s
    return p


def have(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 0


def probe_duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


# ---------------------------------------------------------------- stage 1: voice
def stage_tts(reels):
    if not QWEN_PY.exists() or not QWEN_RUNNER.exists():
        sys.exit(f"Qwen3-TTS not found ({QWEN_PY} / {QWEN_RUNNER}); refusing to fall back to another voice")
    tasks = []
    for r in reels:
        ref = VOICE_DIR / f"{r['voice']}.wav"
        if not ref.exists():
            sys.exit(f"voice reference missing: {ref}")
        for i, s in enumerate(r["scenes"], 1):
            target = rdir(r, "audio", f"s{i}.wav")
            if not have(target):
                tasks.append(dict(id=f"{r['slug']}_s{i}", text=s["line"], target_path=str(target), ref_audio=str(ref), language="English"))
    if not tasks:
        return print("tts: nothing to do")
    OUT.mkdir(parents=True, exist_ok=True)
    inp, res = OUT / "_tts_in.json", OUT / "_tts_out.json"
    inp.write_text(json.dumps(tasks), encoding="utf-8")
    print(f"tts: {len(tasks)} lines through Qwen3-TTS ...")
    subprocess.run([str(QWEN_PY), str(QWEN_RUNNER), "batch", "--input", str(inp), "--output", str(res)], check=True)
    bad = [x for x in json.loads(res.read_text(encoding="utf-8")) if not x.get("success")]
    if bad:
        sys.exit(f"tts failures: {bad}")
    print("tts: done")


# ---------------------------------------------------------------- stage 2: music
def stage_music(reels):
    from engine.audio.providers.ace_step import ACEStepProvider
    prov = ACEStepProvider()
    try:
        for r in reels:
            if list(rdir(r, "audio", "music").glob("music_*.wav")):
                continue
            mdir = rdir(r, "audio", "music")
            mdir.mkdir(parents=True, exist_ok=True)
            total = 32.0
            print(f"music: {r['slug']} ...")
            rec = prov.generate_music_take("reels", r["slug"], mdir, prompt=r["music"], audio_duration=total, bpm=r["bpm"],
                                           key_scale="C Major" if r["music"].startswith("soft") else "G Major",
                                           seed=4000 + ridx(r), use_random_seed=False)
            print(f"  -> {rec.audio_file_path} ({rec.duration_sec}s)")
    finally:  # free the GPU for ComfyUI
        if prov._daemon_process is not None:
            prov._daemon_process.terminate()


# ---------------------------------------------------------------- stage 3: pictures
def _engine():
    from engine.comfyui import ComfyUIClient, ComfyWorkflowRegistry
    from engine.comfyui.art import ArtEngine
    client = ComfyUIClient()
    return client, ComfyWorkflowRegistry(client), ArtEngine


def still_prompt(r: dict, s: dict) -> str:
    return f"{STYLE}. {r['palette']}. Characters: {r['chars']}. Scene: {s['img']}."


def stage_art(reels):
    client, reg, ArtEngine = _engine()
    engine = ArtEngine(client, reg)
    for r in reels:
        anchor = rdir(r, "panels", "s1.png")
        for i, s in enumerate(r["scenes"], 1):
            out = rdir(r, "panels", f"s{i}.png")
            if have(out):
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.monotonic()
            kw = dict(reference_image=anchor) if i > 1 and have(anchor) and i not in NO_REF.get(r['slug'], ()) else {}
            art = engine.generate(prompt=still_prompt(r, s), negative_prompt=NEGATIVE, width=768, height=1344,
                                  seed=1000 + 10 * ridx(r) + i, prefix=f"reels/{r['slug']}_s{i}", **kw)
            out.write_bytes(art.png)
            print(f"art {r['slug']} s{i}: {time.monotonic() - t0:.0f}s")


# ---------------------------------------------------------------- stage 4: H3 clips
def stage_clips(reels):
    from engine.comfyui.art import _patch_workflow
    from engine.comfyui.service import _history_videos
    from engine.original.animate import release_ollama
    release_ollama()
    client, reg, ArtEngine = _engine()
    wf_id = "fastvideo_h3_i2v"
    pre = reg.preflight(wf_id)
    if not pre.get("ready"):
        sys.exit(f"H3 preflight failed: {pre}")
    workflow, _ = reg.load(wf_id)
    slots = reg.metadata(wf_id)["patch_slots"]
    engine = ArtEngine(client, reg)
    for r in reels:
        for i, s in enumerate(r["scenes"], 1):
            clip, panel = rdir(r, "clips", f"s{i}.mp4"), rdir(r, "panels", f"s{i}.png")
            if have(clip):
                continue
            if not have(panel):
                sys.exit(f"{panel} missing: run the art stage first")
            clip.parent.mkdir(parents=True, exist_ok=True)
            prompt = ("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
                      f"integrated_multimodal_description: [Shot 1] {r['chars']}. {s['act']}. The camera is a Static Shot, fixed on a tripod. "
                      "Only the action of this moment moves; everything else stays exactly as drawn in the same flat hand-drawn doodle cartoon style.\n\n"
                      "overall_soundscape: quiet light room tone, no dialogue.\n\nnon_diegetic_music: none.")
            patched = _patch_workflow(workflow, slots, prompt, negative_prompt="", width=480, height=832,
                                      seed=2000 + 10 * ridx(r) + i + int(os.environ.get('REEL_SEED_BUMP', '0')), prefix=f"reels/{r['slug']}_clip{i}",
                                      reference_image=client.upload_image(panel), duration=5.0)
            t0 = time.monotonic()
            raw, _, _ = engine.run(patched, timeout=900.0, collect=_history_videos)
            clip.write_bytes(raw)
            print(f"clip {r['slug']} s{i}: {time.monotonic() - t0:.0f}s ({len(raw) // 1024} KB)")


# ---------------------------------------------------------------- stage 5: assemble
def ass_time(t: float) -> str:
    cs = round(t * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def chunks(line: str, n: int = 3) -> list[str]:
    words = line.split()
    out, i = [], 0
    while i < len(words):
        take = n if len(words) - i != n + 1 else n + 1  # avoid a one-word orphan
        out.append(" ".join(words[i:i + take]))
        i += take
    return out


def build_ass(r: dict, starts: list[float], voice_dur: list[float]) -> str:
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            f"Style: Cap,{FONT},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,8,2,2,60,60,430,1\n"
            f"Style: Hook,{FONT},118,&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,0,0,0,0,100,100,1,0,1,9,3,8,60,60,230,1\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    ev = [f"Dialogue: 1,{ass_time(0.0)},{ass_time(2.6)},Hook,,0,0,0,,{r['hook'].upper()}"]
    for s, t0, a in zip(r["scenes"], starts, voice_dur):
        parts = chunks(s["line"].upper().replace(".", "").replace(",", ""))
        weights = [max(1, len(p)) for p in parts]
        span, t = max(a, 0.8), t0 + 0.12
        for p, w in zip(parts, weights):
            d = span * w / sum(weights)
            ev.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d)},Cap,,0,0,0,,{p}")
            t += d
    return head + "\n".join(ev) + "\n"


def read_mono(p: Path) -> np.ndarray:
    d, sr = sf.read(str(p), dtype="float32")
    if d.ndim > 1:
        d = d.mean(axis=1)
    if sr != SR:
        d = np.interp(np.linspace(0, d.size - 1, round(d.size * SR / sr)), np.arange(d.size), d).astype(np.float32)
    return d


def stage_assemble(reels):
    for r in reels:
        d = rdir(r)
        final = d / f"{r['slug']}.mp4"
        if have(final):
            continue
        n = len(r["scenes"])
        missing = [p for i in range(1, n + 1) for p in (d / "clips" / f"s{i}.mp4", d / "audio" / f"s{i}.wav") if not have(p)]
        if missing:
            print(f"assemble {r['slug']}: skipped, missing {len(missing)} files (e.g. {missing[0].name})")
            continue
        voice_parts, starts, durs, seg_files, t = [], [], [], [], 0.0
        for i in range(1, n + 1):
            v = read_mono(d / "audio" / f"s{i}.wav")
            a = v.size / SR
            dur = max(3.4, a + 0.4)
            clip = d / "clips" / f"s{i}.mp4"
            cdur = probe_duration(clip)
            seg = d / "seg" / f"s{i}.mp4"
            seg.parent.mkdir(exist_ok=True)
            vf = f"scale={W}:{H}:flags=lanczos,unsharp=5:5:0.6,fps=30,setsar=1"
            if dur > cdur:  # hold the last frame rather than loop a jump
                vf += f",tpad=stop_mode=clone:stop_duration={dur - cdur + 0.1:.2f}"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-vf", vf, "-t", f"{dur:.3f}", "-an",
                            "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", str(seg)], check=True)
            pad = np.zeros(round(dur * SR), dtype=np.float32)
            off = round(0.12 * SR)
            pad[off:off + v.size] = v[:pad.size - off]
            voice_parts.append(pad)
            starts.append(t)
            durs.append(a)
            seg_files.append(seg)
            t += dur
        voice = np.concatenate(voice_parts)
        music_files = sorted((d / "audio" / "music").glob("music_*.wav"))
        music = np.zeros_like(voice)
        if music_files:
            m = read_mono(music_files[-1])
            m = np.pad(m, (0, max(0, voice.size - m.size)))[:voice.size]
            env = np.convolve(np.abs(voice), np.ones(SR // 5) / (SR // 5), mode="same")
            duck = np.clip(env / 0.03, 0, 1)
            gain = 0.33 - 0.21 * np.convolve(duck, np.ones(SR // 4) / (SR // 4), mode="same")
            fade = np.minimum(1.0, np.linspace(1, 0, voice.size) * (voice.size / SR) / 1.5)
            music = m * gain * fade
        mix = np.clip(voice * 0.95 + music, -1, 1)
        sf.write(str(d / "mix.wav"), mix, SR, subtype="PCM_16")
        (d / "captions.ass").write_text(build_ass(r, starts, durs), encoding="utf-8")
        (d / "concat.txt").write_text("\n".join(f"file 'seg/{p.name}'" for p in seg_files), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "video_nocap.mp4"], cwd=d, check=True)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", "video_nocap.mp4", "-i", "mix.wav",
                        "-vf", "subtitles=captions.ass",
                        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final.name], cwd=d, check=True)
        (d / "PUBLISH.md").write_text(
            f"# {r['title']}\n\n**Hook (first 2 s):** {r['hook']}\n\n**Title:** {r['title']} #shorts\n\n**Description:**\n"
            f"{r['scenes'][-1]['line']}\n\n{r['tags']}\n\n_AI-generated visuals and voice: tick the altered/synthetic content disclosure on upload._\n",
            encoding="utf-8")
        print(f"assemble {r['slug']}: {final} ({probe_duration(final):.1f}s)")


def stage_status(reels):
    for r in reels:
        n = len(r["scenes"])
        c = lambda sub, ext: sum(have(rdir(r, sub, f"s{i}.{ext}")) for i in range(1, n + 1))
        m = len(list(rdir(r, "audio", "music").glob("music_*.wav")))
        print(f"{r['slug']:20s} voice {c('audio', 'wav')}/{n}  music {m}/1  art {c('panels', 'png')}/{n}  clips {c('clips', 'mp4')}/{n}  final {'YES' if have(rdir(r, f'{r['slug']}.mp4')) else '-'}")


STAGES = dict(tts=stage_tts, music=stage_music, art=stage_art, clips=stage_clips, assemble=stage_assemble, status=stage_status)

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in STAGES:
        sys.exit(__doc__)
    STAGES[sys.argv[1]](pick(sys.argv[2:]))
