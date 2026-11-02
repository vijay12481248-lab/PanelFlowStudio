"""Video from panels: per-panel voice (storyteller + character voices), audio-driven timeline, Ken Burns render, captions, music.

Why not the manga project pipeline: it OCRs page images and rewrites narration from them. Here the story already has its own
narration and dialogue, so the audio length of each panel drives its length directly (the same rule as the anime review sync)
and the existing pieces (Kokoro adapter, caption/SRT helpers, NVENC detection, music bed) are reused as they are.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Callable

import numpy as np

from engine.anime.review import render as rr
from engine.anime.review.timeline import wav_seconds
from engine.narration.runtime import audio as rt
from engine.original.models import OriginalStory, Panel

NARRATORS = {"bedtime": ("af_heart", 0.88), "horror": ("bm_george", 0.92), "mystery": ("am_adam", 0.95), "fantasy": ("bm_fable", 0.95)}
CHARACTER_VOICES = ["af_sky", "am_adam", "af_nicole", "bm_fable", "af_bella", "am_michael"]  # voices cached offline
GAP_SEC, END_PAUSE_SEC, MIN_PANEL_SEC = 0.25, 0.6, 3.0
ZOOM_END = 1.12
MOTIONS = ["in", "pan_right", "out", "pan_left"]


def voices_for(story: OriginalStory) -> tuple[tuple[str, float], dict[str, tuple[str, float]]]:
    narrator = NARRATORS.get(story.bible.premise.genre, NARRATORS["fantasy"])
    pool = [v for v in CHARACTER_VOICES if v != narrator[0]]
    return narrator, {c.id: (pool[i % len(pool)], 1.0) for i, c in enumerate(story.bible.characters)}


def spoken_parts(panel: Panel) -> list[tuple[str, str | None]]:
    """(text, speaker_id or None for the storyteller) in the order they are read."""
    return ([(panel.caption, None)] if panel.caption.strip() else []) + [(ln.text, ln.speaker_id) for ln in panel.dialogue]


def voice_panel(tts, panel: Panel, narrator: tuple[str, float], chars: dict[str, tuple[str, float]], fps: float, out: Path) -> float:
    """One wav per panel: parts joined with short gaps, a closing pause, at least MIN_PANEL_SEC, padded to a whole frame."""
    gap = np.zeros(int(GAP_SEC * rt.SR), dtype=np.float32)
    pieces: list[np.ndarray] = []
    for text, who in spoken_parts(panel):
        voice, rate = narrator if who is None else chars.get(who, narrator)
        audio, _, _ = rt.normalize_silence(tts.synth(text, voice, rate))
        pieces += [audio, gap]
    audio = np.concatenate(pieces[:-1]) if pieces else np.zeros(0, dtype=np.float32)
    audio = np.concatenate([audio, np.zeros(int(END_PAUSE_SEC * rt.SR), dtype=np.float32)])
    audio = np.concatenate([audio, np.zeros(max(0, int(MIN_PANEL_SEC * rt.SR) - len(audio)), dtype=np.float32)])
    frame = rt.SR / fps
    audio = np.concatenate([audio, np.zeros(int(round(math.ceil(len(audio) / frame - 1e-9) * frame)) - len(audio), dtype=np.float32)])
    rt.write_wav_atomic(out, audio)
    return wav_seconds(out)


def motion_filter(motion: str, frames: int) -> str:
    """zoompan expression for a slow push-in/out or pan over the whole panel (linear, so no commas to escape)."""
    n = max(frames, 1)
    z = {"in": f"1+{(ZOOM_END - 1) / n:.7f}*on", "out": f"{ZOOM_END}-{(ZOOM_END - 1) / n:.7f}*on"}.get(motion, f"{ZOOM_END - 0.02}")
    x = {"pan_right": f"(iw-iw/zoom)*on/{n}", "pan_left": f"(iw-iw/zoom)*(1-on/{n})"}.get(motion, "iw/2-iw/zoom/2")
    return f"zoompan=z='{z}':x='{x}':y='ih/2-ih/zoom/2':d={n}:s={rr.W}x{rr.H}:fps={{fps}}"


def render_panel(img: Path, wav: Path, dur: float, fps: float, text: str, motion: str, ws: Path, burn: bool, out: Path,
                 fade_in: float = 0.0, fade_out: float = 0.0) -> None:
    n = round(dur * fps)
    vf = [f"scale={rr.W * 2}:{rr.H * 2}:force_original_aspect_ratio=increase", f"crop={rr.W * 2}:{rr.H * 2}",
          motion_filter(motion, n).replace("{fps}", str(fps))]
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        vf.append(f"fade=t=out:st={dur - fade_out:.3f}:d={fade_out}")
    if burn and text.strip():
        (ws / "tmp_seg.srt").write_text(rr.srt_text(rr.caption_chunks(text, max(dur - END_PAUSE_SEC, 0.5))), encoding="utf-8")
        vf.append("subtitles=tmp_seg.srt:force_style='FontName=Arial,FontSize=20,Bold=1,Outline=2,Shadow=1,MarginV=48'")
    vf.append("format=yuv420p")
    af = "aresample=48000" + (f",afade=t=in:st=0:d={fade_in}" if fade_in else "") + (
        f",afade=t=out:st={dur - fade_out:.3f}:d={fade_out}" if fade_out else "")
    head = ["ffmpeg", "-y", "-v", "error", "-i", str(img), "-i", str(wav), "-filter_complex", f"[0:v]{','.join(vf)}[v];[1:a]{af}[a]",
            "-map", "[v]", "-map", "[a]"]
    tail = ["-frames:v", str(n), "-t", f"{dur}", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)]
    try:
        rr._run(head + rr.video_encoder() + tail, ws)
    except RuntimeError:
        if rr.video_encoder() == rr.CPU_ENCODER:
            raise
        rr._run(head + rr.CPU_ENCODER + tail, ws)


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def build_video(story: OriginalStory, ws: Path, tts=None, fps: float = 30.0, burn_captions: bool = True,
                music: Path | None = rr.DEFAULT_MUSIC, name: str = "story_1080p.mp4",
                progress: Callable[[float, str], None] = lambda p, m: None) -> dict:
    """Voices and renders every panel that has an image (missing panels are listed, not faked); reruns reuse unchanged work."""
    tts = tts or rt.KokoroTts()
    narrator, chars = voices_for(story)
    (ws / "voice").mkdir(parents=True, exist_ok=True)
    (ws / "segments").mkdir(exist_ok=True)
    panels = [p for p in story.panels if (ws / "panels" / f"{p.id}.png").exists()]
    missing = [p.id for p in story.panels if p not in panels]
    if not panels:
        raise ValueError("no panel images found; run the art step first")
    meta_path = ws / "video_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    entries, t = [], 0.0
    try:
        for i, p in enumerate(panels):
            progress(i / len(panels) * 0.9, f"Panel {i + 1}/{len(panels)}")
            img, wav, seg = ws / "panels" / f"{p.id}.png", ws / "voice" / f"{p.id}.wav", ws / "segments" / f"{p.id}.mp4"
            vkey = _digest(json.dumps(spoken_parts(p)), json.dumps(narrator), json.dumps(chars))
            if not (wav.exists() and meta.get(p.id, {}).get("voice") == vkey):
                voice_panel(tts, p, narrator, chars, fps, wav)
            dur = wav_seconds(wav)
            last = i == len(panels) - 1
            rkey = _digest(vkey, hashlib.sha256(img.read_bytes()).hexdigest(), str(burn_captions), MOTIONS[i % 4], str(i == 0), str(last))
            if not (seg.exists() and meta.get(p.id, {}).get("render") == rkey):
                text = " ".join(x for x, _ in spoken_parts(p))
                render_panel(img, wav, dur, fps, text, MOTIONS[i % 4], ws, burn_captions, seg,
                             fade_in=0.6 if i == 0 else 0.0, fade_out=1.2 if last else 0.0)
            meta[p.id] = {"voice": vkey, "render": rkey}
            entries.append({"panel_id": p.id, "scene_id": p.scene_id, "start": round(t, 4), "duration": round(dur, 4)})
            t += round(dur, 4)
    finally:
        rt.release_audio_models()
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
    progress(0.92, "Assembling")
    lines = [(e["start"] + a, e["start"] + b, x) for e, p in zip(entries, panels)
             for a, b, x in rr.caption_chunks(" ".join(y for y, _ in spoken_parts(p)), max(e["duration"] - END_PAUSE_SEC, 0.5))]
    (ws / "story.srt").write_text(rr.srt_text(lines), encoding="utf-8")
    (ws / "concat.txt").write_text("".join(f"file 'segments/{e['panel_id']}.mp4'\n" for e in entries), encoding="utf-8")
    out = ws / name
    if music and Path(music).exists():
        rr._run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-stream_loop", "-1", "-i", str(music),
                 "-filter_complex", f"[1:a]volume={rr.MUSIC_DB - 2}dB,afade=t=out:st={max(t - 2, 0):.3f}:d=2[m];"
                                    "[0:a][m]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-16:TP=-1.5:LRA=11[a]",
                 "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{t}",
                 "-movflags", "+faststart", str(out)], ws)
    else:
        rr._run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], ws)
    for f in ("concat.txt", "tmp_seg.srt"):
        (ws / f).unlink(missing_ok=True)
    (ws / "timeline.json").write_text(json.dumps({"fps": fps, "total_sec": round(t, 4), "entries": entries}, indent=1), encoding="utf-8")
    progress(1.0, "Video ready")
    return {"video": str(out), "srt": str(ws / "story.srt"), "duration_sec": round(t, 2), "panels": len(entries), "missing_panels": missing}


def chapters(story: OriginalStory, timeline: dict) -> list[tuple[str, str]]:
    """One chapter per scene (YouTube needs 3+, each 10 s or longer, the first at 0:00)."""
    from engine.anime.review.packaging import _stamp

    starts: dict[str, float] = {}
    for e in timeline["entries"]:
        starts.setdefault(e["scene_id"], e["start"])
    scenes = {sc.id: sc for sc in story.scenes}
    out: list[tuple[float, str]] = []
    for sid, t in starts.items():
        if out and t - out[-1][0] < 10:
            continue
        out.append((t, " ".join(scenes[sid].summary.split()[:7]).rstrip(".,;")))
    return [(_stamp(t), label) for t, label in out] if len(out) >= 3 else []


def package(story: OriginalStory, ws: Path) -> dict:
    """Title, description (with the AI disclosure YouTube asks for), chapters, tags and a thumbnail from the best panel."""
    from PIL import Image, ImageDraw, ImageFont

    from engine.anime.review.packaging import IMPACT
    from engine.original.genres import GENRES

    pr = story.bible.premise
    timeline = json.loads((ws / "timeline.json").read_text())
    ch = chapters(story, timeline)
    desc = [pr.logline, ""] + (["Chapters:"] + [f"{t} {l}" for t, l in ch] + [""] if ch else []) + [
        f"An original {pr.genre} story. The story, art and narration were created with AI tools (PanelFlow Studio) and "
        "reviewed by the channel owner."]
    first = next((p for p in story.panels if (ws / "panels" / f"{p.id}.png").exists() and p.shot in ("close", "medium")), None) or next(
        p for p in story.panels if (ws / "panels" / f"{p.id}.png").exists())
    img = Image.open(ws / "panels" / f"{first.id}.png").convert("RGB").resize((1280, 720))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(IMPACT), 96) if IMPACT.exists() else ImageFont.load_default()
    lines, cur = [], ""
    for w in pr.title.upper().split():
        if cur and d.textlength(cur + " " + w, font=font) > 1160:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    y = 720 - 40 - 110 * len(lines[:3])
    for ln in lines[:3]:
        d.text((60, y), ln, font=font, fill="white", stroke_width=7, stroke_fill="black")
        y += 110
    thumb = ws / "thumbnail.jpg"
    img.save(thumb, quality=92)
    tags = [pr.genre + " story", "original story", "animated story", "story time", "AI generated story"] + [c.name for c in story.bible.characters]
    pkg = {"title": pr.title[:100], "description": chr(10).join(desc), "tags": tags, "chapters": ch,
           "thumbnail_path": str(thumb), "genre_style": GENRES[pr.genre].art_style}
    (ws / "youtube_package.json").write_text(json.dumps(pkg, indent=1), encoding="utf-8")
    return pkg
