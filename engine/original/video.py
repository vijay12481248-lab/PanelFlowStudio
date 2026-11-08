"""Video from panels: per-panel voice (storyteller + character voices), audio-driven timeline, still full-frame render, captions, music.

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

NARRATORS = {"bedtime": ("af_heart", 0.88), "horror": ("bm_george", 0.92), "mystery": ("am_adam", 0.95), "fantasy": ("bm_fable", 0.95), "mythology": ("bm_george", 0.90),
             "vox": ("am_michael", 1.06)}  # brisk, deadpan explainer pace
CHARACTER_VOICES = ["af_sky", "am_adam", "af_nicole", "bm_fable", "af_bella", "am_michael"]  # voices cached offline
MALE_VOICES = ["am_adam", "bm_fable", "am_michael", "bm_george"]
FEMALE_VOICES = ["af_sky", "af_bella", "af_nicole", "af_heart"]
GAP_SEC, END_PAUSE_SEC, MIN_PANEL_SEC = 0.25, 0.6, 3.0
FIT_TOLERANCE = 0.03  # a picture this close to 16:9 is scaled to fill (a 1.6% stretch cannot be seen); anything else is shown whole on a blurred copy
RENDER_LOOK = "still-fit-1"  # part of every cached segment's key: bump it when the look changes so old clips are not reused


def voices_for(story: OriginalStory, narrator: tuple[str, float] | None = None) -> tuple[tuple[str, float], dict[str, tuple[str, float]]]:
    narrator = narrator or NARRATORS.get(story.bible.premise.genre, NARRATORS["fantasy"])
    m_pool = [v for v in MALE_VOICES if v != narrator[0]] or MALE_VOICES
    f_pool = [v for v in FEMALE_VOICES if v != narrator[0]] or FEMALE_VOICES
    all_pool = [v for v in CHARACTER_VOICES if v != narrator[0]] or CHARACTER_VOICES
    chars = {}
    m_idx = f_idx = 0
    for i, c in enumerate(story.bible.characters):
        speed = 0.92 if getattr(c, "age_group", "") == "elder" else 1.0
        if getattr(c, "gender", "") == "male":
            v = m_pool[m_idx % len(m_pool)]
            m_idx += 1
        elif getattr(c, "gender", "") == "female":
            v = f_pool[f_idx % len(f_pool)]
            f_idx += 1
        else:
            v = all_pool[i % len(all_pool)]
        chars[c.id] = (v, speed)
    return narrator, chars


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


def motion_fx_filters(fx: str | None) -> list[str]:
    """Generates FFmpeg video filter fragments for motion graphics and visual atmosphere."""
    if not fx or fx in ("none", "clean"):
        return []
    out = []
    if fx == "letterbox":
        out.append(f"drawbox=y=0:h={int(rr.H * 0.075)}:color=black:t=fill,drawbox=y={int(rr.H * 0.925)}:h={int(rr.H * 0.075)}:color=black:t=fill")
    elif fx == "vignette":
        out.append("vignette=angle=PI/5,eq=contrast=1.04:saturation=1.08")
    elif fx == "film_grain":
        out.append("noise=alls=9:allf=t+u")
    elif fx == "warm_cinema":
        out.append("eq=contrast=1.06:saturation=1.12:gamma=0.98")
    return out

def fit_graph(aspect: float, size: tuple[int, int] | None = None) -> str:
    """Filter graph [0:v] -> [v0]: the WHOLE picture on a 16:9 canvas. Nothing is cropped and nothing moves.

    Square close-ups and portrait sheets sit centred on a blurred, darkened copy of themselves, so no black bars show and no head,
    hand or glass is cut off.
    """
    W, H = size or (rr.W, rr.H)
    if abs(aspect / (W / H) - 1) < FIT_TOLERANCE:
        return f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1[v0]"
    return (f"[0:v]split[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=25:5,eq=brightness=-0.15:saturation=1.1[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")


def frame_canvas(story: OriginalStory) -> tuple[int, int] | None:
    """The render canvas a story asks for: a 9:16 story (a YouTube Short) is 1080x1920; anything else keeps the default landscape canvas."""
    return (1080, 1920) if (story.meta or {}).get("frame") == "9:16" else None


def caption_style(size: tuple[int, int] | None) -> str:
    """libass style: landscape keeps the long-form look; a vertical canvas gets a bigger font in short lines, placed in the lower third
    (above the Shorts UI, which covers the very bottom), so a 9-word chunk wraps to two lines instead of running off the narrow frame."""
    if size and size[1] > size[0]:
        # libass scales these by PlayResY=288 (and PlayResX = 288 * w/h = 162 on a 9:16 canvas): FontSize 10 is ~64 px of 1920, MarginV 70 puts the
        # lines ~470 px above the bottom edge, MarginL/R 10 leave ~88% of the width. (Measured: MarginV 300 pushed the text off the frame.)
        return "FontName=Arial,FontSize=10,Bold=1,Outline=1,Shadow=0,BorderStyle=1,Alignment=2,MarginV=70,MarginL=10,MarginR=10"
    return "FontName=Arial,FontSize=20,Bold=1,Outline=1,Shadow=0,BackColour=&H80000000,BorderStyle=4,MarginV=36"


def render_panel(img: Path, wav: Path, dur: float, fps: float, text: str, ws: Path, burn: bool, out: Path,
                 fade_in: float = 0.0, fade_out: float = 0.0, fx: str | None = None, size: tuple[int, int] | None = None) -> None:
    n = round(dur * fps)
    from PIL import Image
    try:
        with Image.open(img) as im:
            aspect = im.width / max(im.height, 1)
    except Exception:
        aspect = (size or (rr.W, rr.H))[0] / (size or (rr.W, rr.H))[1]

    vf = []
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        vf.append(f"fade=t=out:st={dur - fade_out:.3f}:d={fade_out}")
    if burn and text.strip():
        (ws / "tmp_seg.srt").write_text(rr.srt_text(rr.caption_chunks(text, max(dur - END_PAUSE_SEC, 0.5))), encoding="utf-8")
        vf.append(f"subtitles=tmp_seg.srt:force_style='{caption_style(size)}'")
    vf.extend(motion_fx_filters(fx))
    vf.append("format=yuv420p")

    af = "aresample=48000" + (f",afade=t=in:st=0:d={fade_in}" if fade_in else "") + (
        f",afade=t=out:st={dur - fade_out:.3f}:d={fade_out}" if fade_out else "")
    head = ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", str(img), "-i", str(wav),
            "-filter_complex", f"{fit_graph(aspect, size)};[v0]{','.join(vf)}[v];[1:a]{af}[a]", "-map", "[v]", "-map", "[a]"]
    tail = ["-frames:v", str(n), "-t", f"{dur}", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)]
    try:
        rr._run(head + rr.video_encoder() + tail, ws)
    except RuntimeError:
        if rr.video_encoder() == rr.CPU_ENCODER:
            raise
        rr._run(head + rr.CPU_ENCODER + tail, ws)


def clip_aspect(clip: Path) -> float:
    """Width / height of a video file (ffprobe)."""
    import subprocess

    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(clip)],
                         capture_output=True, text=True, check=True).stdout.strip().split(",")
    return int(out[0]) / max(int(out[1]), 1)


def pingpong(clip: Path, ws: Path) -> Path:
    """The clip played forward and then backward (cached beside it). A 5 s AI shot can then cover a longer narrated line with no visible
    jump: the end of the cycle is the first frame again, which suits the small movements these shots have."""
    pp = clip.with_suffix(".pingpong.mp4")
    if not (pp.exists() and pp.stat().st_mtime >= clip.stat().st_mtime):
        rr._run(["ffmpeg", "-y", "-v", "error", "-i", str(clip), "-an", "-filter_complex",
                 "[0:v]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1:a=0[o]", "-map", "[o]",
                 "-c:v", "libx264", "-crf", "12", "-preset", "fast", "-pix_fmt", "yuv420p", str(pp)], ws)
    return pp


def render_ai_panel(clip: Path, wav: Path, dur: float, fps: float, text: str, ws: Path, burn: bool, out: Path,
                    fade_in: float = 0.0, fade_out: float = 0.0, fx: str | None = None) -> None:
    """An AI-generated shot + the narration: the whole shot is shown (same fit as still pictures), its own sound is dropped, a shot shorter
    than the line is stretched by a ping-pong, subtitles are burned, and the length is conformed to the narration."""
    n = round(dur * fps)
    vf = []
    if fade_in:
        vf.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        vf.append(f"fade=t=out:st={dur - fade_out:.3f}:d={fade_out}")
    if burn and text.strip():
        (ws / "tmp_seg.srt").write_text(rr.srt_text(rr.caption_chunks(text, max(dur - END_PAUSE_SEC, 0.5))), encoding="utf-8")
        vf.append("subtitles=tmp_seg.srt:force_style='FontName=Arial,FontSize=20,Bold=1,Outline=1,Shadow=0,BackColour=&H80000000,BorderStyle=4,MarginV=36'")
    vf.extend(motion_fx_filters(fx))
    vf.append("format=yuv420p")
    af = "aresample=48000" + (f",afade=t=in:st=0:d={fade_in}" if fade_in else "") + (
        f",afade=t=out:st={dur - fade_out:.3f}:d={fade_out}" if fade_out else "")
    src = pingpong(clip, ws)
    graph = fit_graph(clip_aspect(clip)).replace("[0:v]", "[c]", 1)  # the same whole-picture fit as stills, fed by the fps-conformed clip
    head = ["ffmpeg", "-y", "-v", "error", "-stream_loop", "-1", "-i", str(src), "-i", str(wav),
            "-filter_complex", f"[0:v]fps={fps}[c];{graph};[v0]{','.join(vf)}[v];[1:a]{af}[a]",
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
                progress: Callable[[float, str], None] = lambda p, m: None, narrator: tuple[str, float] | None = None,
                engine: str = "auto", fx: str = "none", size: tuple[int, int] | None = None) -> dict:
    """Voices and renders every panel that has an image (missing panels are listed, not faked); reruns reuse unchanged work."""
    ws = Path(ws).resolve()
    tts = tts or rt.KokoroTts()
    narrator, chars = voices_for(story, narrator)
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
            clip = ws / "clips" / f"{p.id}.mp4"
            use_clip = clip.exists() and engine != "still"
            rkey = _digest(vkey, hashlib.sha256(img.read_bytes()).hexdigest(), str(burn_captions), RENDER_LOOK, str(i == 0), str(last), str(size), caption_style(size),
                           hashlib.sha256(clip.read_bytes()).hexdigest() if use_clip else "still", str(fx))  # a new clip invalidates its segment
            if not (seg.exists() and meta.get(p.id, {}).get("render") == rkey):
                text_content = " ".join(x for x, _ in spoken_parts(p))
                if use_clip:
                    render_ai_panel(clip, wav, dur, fps, text_content, ws, burn_captions, seg,
                                    fade_in=0.6 if i == 0 else 0.0, fade_out=1.2 if last else 0.0, fx=fx)
                else:
                    render_panel(img, wav, dur, fps, text_content, ws, burn_captions, seg,
                                 fade_in=0.6 if i == 0 else 0.0, fade_out=1.2 if last else 0.0, fx=fx, size=size)
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
        sc = scenes[sid]
        out.append((t, sc.title.strip() or " ".join(sc.summary.split()[:7]).rstrip(".,;")))
    return [(_stamp(t), label) for t, label in out] if len(out) >= 3 else []


def thumbnail_with_text(src: Path, text: str, out: Path) -> Path:
    """1280x720 thumbnail from a panel picture with 1-3 big stacked words (Impact, white then yellow, black outline) on the side of the
    picture that has less going on (lower edge energy), so the text does not cover the face; the words never repeat the title (author's choice)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    from engine.anime.review.packaging import IMPACT

    img = Image.open(src).convert("RGB").resize((1280, 720), Image.LANCZOS)
    g = np.asarray(img.convert("L"), dtype=np.float32)
    edge = np.abs(np.diff(g, axis=1))[:-1, :] + np.abs(np.diff(g, axis=0))[:, :-1]
    rgb = np.asarray(img, dtype=np.float32)
    r_, g_, b_ = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    face = ((r_ > 140) & (g_ > 80) & (g_ < 0.78 * r_) & (b_ < 0.75 * g_ + 20)) | (g.astype(np.float32) < 40)  # skin tones and near-black hair
    face = face[:-1, :-1]

    def busy(sl):  # how much is going on, with a heavy penalty for a face or hair under the text column
        return edge[:, sl].mean() + 3000 * face[:, sl].mean()

    left, right = busy(slice(0, 470)), busy(slice(-470, None))
    words = text.upper().split()[:3] or [""]
    font_path = str(IMPACT) if IMPACT.exists() else None
    d = ImageDraw.Draw(img)
    zone = 470  # text column width in pixels
    size = 230
    while font_path and size > 70 and (max(d.textlength(w, font=ImageFont.truetype(font_path, size)) for w in words) > zone
                                       or size * 1.08 * len(words) > 660):  # also keep a 3-word stack inside the frame
        size -= 6
    font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
    line_h = int(size * 1.08)
    total = line_h * len(words)
    y0 = max(20, (720 - total) // 2 - 10)
    for i, w in enumerate(words):
        w_px = d.textlength(w, font=font)
        x = 36 if left <= right else 1280 - 36 - w_px
        d.text((x, y0 + i * line_h), w, font=font, fill="white" if i % 2 == 0 else "#FFD400", stroke_width=max(6, size // 16), stroke_fill="black")
    img.save(out, quality=92)
    return out


def package(story: OriginalStory, ws: Path, extra_tags: list[str] | None = None, footer: str = "") -> dict:
    """Title, description (with the AI disclosure YouTube asks for), chapters, tags and a thumbnail from the best panel."""
    from PIL import Image, ImageDraw, ImageFont

    from engine.anime.review.packaging import IMPACT
    from engine.original.genres import GENRES

    pr = story.bible.premise
    meta = story.meta or {}
    timeline = json.loads((ws / "timeline.json").read_text())
    ch = chapters(story, timeline)
    disclosure = ("Script, pictures and narration were made with AI tools." if meta.get("hook") else
                  f"An original {pr.genre} story. The story, art and narration were created with AI tools (PanelFlow Studio) and reviewed by the channel owner.")
    desc = [meta.get("hook") or pr.logline, ""] + ([pr.logline, ""] if meta.get("hook") else []) + (
        ["Chapters:"] + [f"{t} {l}" for t, l in ch] + [""] if ch else []) + ([meta["cta"], ""] if meta.get("cta") else []) + [disclosure] + (
        ["", footer] if footer else [])
    has = lambda p: (ws / "panels" / f"{p.id}.png").exists()  # noqa: E731
    first = next((p for p in story.panels if p.id == meta.get("thumb_panel") and has(p)), None) or next(
        (p for p in story.panels if has(p) and p.shot in ("close", "medium")), None) or next(p for p in story.panels if has(p))
    thumb = ws / "thumbnail.jpg"
    if frame_canvas(story):  # a Short has no custom thumbnail (YouTube takes a frame); a landscape one would be a squashed picture
        pass
    elif meta.get("thumb_text"):
        thumbnail_with_text(ws / "panels" / f"{first.id}.png", meta["thumb_text"], thumb)
    else:
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
        img.save(thumb, quality=92)
    tags = list(meta["tags"]) if meta.get("tags") else (
        [pr.genre + " story", "original story", "animated story", "story time", "AI generated story"] + [c.name for c in story.bible.characters])
    tags += extra_tags or []
    pkg = {"title": pr.title[:100], "description": chr(10).join(desc), "tags": tags, "chapters": ch,
           "thumbnail_path": str(thumb), "genre_style": GENRES[pr.genre].art_style}
    (ws / "youtube_package.json").write_text(json.dumps(pkg, indent=1), encoding="utf-8")
    return pkg
