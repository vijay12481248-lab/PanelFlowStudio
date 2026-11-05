"""Render: timeline -> 1080p MP4 (NVENC with CPU fallback), ducked source audio, music, burned-in + sidecar captions."""
from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path

from engine.anime.review.models import ReviewScript, Timeline, TimelineEntry

W, H = 1920, 1080
SLOW_ZOOM_MIN_HOLD = 0.75
SLOW_ZOOM_END = 1.10
DUCK_DB = -22.0     # original anime audio under the narration
MUSIC_DB = -24.0
MAX_CAPTION_WORDS = 9
DEFAULT_MUSIC = Path(__file__).resolve().parents[3] / "apps" / "desktop" / "public" / "assets" / "demo" / "crystal_resonance_bgm.mp3"


@lru_cache(maxsize=1)
def video_encoder() -> list[str]:
    """NVENC when a 1-frame test encode succeeds on this machine, else libx264."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.1", "-frames:v", "1",
                        "-c:v", "h264_nvenc", "-f", "null", "-"], capture_output=True)
    if r.returncode == 0:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


CPU_ENCODER = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def caption_chunks(text: str, speech_sec: float) -> list[tuple[float, float, str]]:
    """Split narration into short caption lines timed in proportion to their word counts."""
    words = text.split()
    chunks = [" ".join(words[i:i + MAX_CAPTION_WORDS]) for i in range(0, len(words), MAX_CAPTION_WORDS)]
    total = sum(len(c.split()) for c in chunks) or 1
    out, t = [], 0.0
    for c in chunks:
        d = speech_sec * len(c.split()) / total
        out.append((t, t + d, c))
        t += d
    return out


def _srt_time(s: float) -> str:
    ms = round(s * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt_text(chunks: list[tuple[float, float, str]], offset: float = 0.0) -> str:
    return "".join(f"{i}\n{_srt_time(a + offset)} --> {_srt_time(b + offset)}\n{t}\n\n" for i, (a, b, t) in enumerate(chunks, 1))


def _run(cmd: list[str], cwd: Path) -> None:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-600:]}")


def render_segment(e: TimelineEntry, text: str, source: Path, has_audio: bool, fps: float, ws: Path,
                   burn_captions: bool, out: Path, watermark: Path | None = None) -> None:
    n_frames = round(e.audio_sec * fps)
    vf = [f"setpts=PTS/{e.speed}", f"scale={W}:{H}:force_original_aspect_ratio=increase", f"crop={W}:{H}", f"fps={fps}"]
    if e.hold_sec > 0:
        vf.append(f"tpad=stop_mode=clone:stop_duration={e.hold_sec + 1:.3f}")
    if e.hold_sec >= SLOW_ZOOM_MIN_HOLD:
        # a frozen frame looks broken; a slow push-in on it looks intentional (and uses no extra footage)
        cf = round(e.src_len / e.speed * fps)
        step = (SLOW_ZOOM_END - 1) / max(n_frames - cf, 1)
        vf.append(f"scale={W * 2}:{H * 2},zoompan=z='if(lte(on,{cf}),1,min(1+(on-{cf})*{step:.6f},{SLOW_ZOOM_END}))'"
                  f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={fps}")
    if burn_captions:
        srt = ws / "tmp_seg.srt"
        srt.write_text(srt_text(caption_chunks(text, max(e.audio_sec - 0.25, 0.5))), encoding="utf-8")
        # relative name + cwd=workspace sidesteps drive-letter escaping in the subtitles filter
        vf.append("subtitles=tmp_seg.srt:force_style='FontName=Arial,FontSize=20,Bold=1,Outline=2,Shadow=1,MarginV=48'")
    vf.append("format=yuv420p")
    if has_audio:
        af = (f"[0:a]atempo={e.speed},volume={DUCK_DB}dB,aresample=48000,apad[o];[1:a]aresample=48000[v];"
              "[o][v]amix=inputs=2:normalize=0:duration=longest[a]")
    else:
        af = "[1:a]aresample=48000[a]"
    cmd_in = ["ffmpeg", "-y", "-v", "error", "-ss", f"{e.src_start}", "-t", f"{e.src_len}", "-i", str(source),
              "-i", e.audio_path]
    video = f"[0:v]{','.join(vf)}[vv]"
    if watermark:  # channel branding: logo top-right, 80 px tall
        cmd_in += ["-i", str(watermark)]
        video = f"[0:v]{','.join(vf)}[v0];[2:v]scale=-1:80[lg];[v0][lg]overlay=W-w-30:30,format=yuv420p[vv]"
    tail = ["-filter_complex", f"{video};{af}", "-map", "[vv]", "-map", "[a]",
            "-frames:v", str(n_frames), "-t", f"{e.audio_sec}", "-r", str(fps), "-c:a", "aac", "-b:a", "192k",
            "-ar", "48000", "-ac", "2", str(out)]
    try:
        _run(cmd_in + tail[:6] + video_encoder() + tail[6:], ws)
    except RuntimeError:
        if video_encoder() == CPU_ENCODER:
            raise
        _run(cmd_in + tail[:6] + CPU_ENCODER + tail[6:], ws)  # NVENC refused this job (e.g. sessions busy)


def render_review(script: ReviewScript, tl: Timeline, source: Path, has_audio: bool, ws: Path,
                  burn_captions: bool = True, music: Path | None = DEFAULT_MUSIC, name: str = "review_1080p.mp4",
                  watermark: Path | None = None) -> Path:
    seg_dir = ws / "render_segments"
    seg_dir.mkdir(exist_ok=True)
    texts = {s.id: s.text for s in script.segments}
    parts = []
    for e in tl.entries:
        p = seg_dir / f"{e.segment_id}.mp4"
        render_segment(e, texts[e.segment_id], source, has_audio, tl.fps, ws, burn_captions, p, watermark)
        parts.append(p)
    (ws / "review.srt").write_text(srt_text(
        [c for e in tl.entries for c in [(a + e.timeline_start, b + e.timeline_start, t)
                                         for a, b, t in caption_chunks(texts[e.segment_id], max(e.audio_sec - 0.25, 0.5))]]),
        encoding="utf-8")
    lst = ws / "concat.txt"
    lst.write_text("".join(f"file '{p.relative_to(ws).as_posix()}'\n" for p in parts), encoding="utf-8")
    out = ws / name
    if music and music.exists():
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-stream_loop", "-1", "-i", str(music),
              "-filter_complex", f"[1:a]volume={MUSIC_DB}dB,afade=t=out:st={max(tl.total_sec - 2, 0):.3f}:d=2[m];"
                                 "[0:a][m]amix=inputs=2:normalize=0:duration=first[a]",
              "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", f"{tl.total_sec}",
              "-movflags", "+faststart", str(out)], ws)
    else:
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy",
              "-movflags", "+faststart", str(out)], ws)
    lst.unlink(missing_ok=True)
    (ws / "tmp_seg.srt").unlink(missing_ok=True)
    return out
