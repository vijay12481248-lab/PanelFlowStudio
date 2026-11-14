"""Read-only media helpers for the ChronoFlow timeline: probe, frame filmstrip and audio waveform.

The editor shows the real frames and the real voice track of every clip, so the browser asks for a
filmstrip sprite and a peak list instead of decoding whole videos. Results are cached next to the
outputs and keyed by the source file's mtime, so a regenerated clip invalidates its own cache.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from array import array
from pathlib import Path

from engine.chronoflow.pipeline import COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR

CACHE_DIR = STUDIO_OUTPUT_DIR / ".nle_cache"
_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
_FFPROBE = shutil.which("ffprobe") or "ffprobe"
_TIMEOUT = 60


def resolve_media(name: str) -> Path | None:
    """Map a bare file name (never a path) to a file in the studio output or input folders."""
    name = str(name or "")
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    for folder in (STUDIO_OUTPUT_DIR, COMFY_INPUT_DIR):
        candidate = folder / name
        if candidate.is_file():
            return candidate
    return None


def probe(path: Path) -> dict:
    """Duration, fps, size and audio presence of a media file."""
    out = subprocess.run(
        [_FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=_TIMEOUT, check=True,
    )
    data = json.loads(out.stdout or "{}")
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    num, _, den = str(video.get("r_frame_rate", "24/1")).partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    return {
        "duration": float(data.get("format", {}).get("duration") or 0.0),
        "fps": round(fps, 3) or 24.0,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
        "is_image": path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"},
    }


def _cache_path(path: Path, tag: str, ext: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{path.stem}_{path.stat().st_mtime_ns}_{tag}.{ext}"


def filmstrip(path: Path, count: int, height: int = 72) -> Path:
    """One JPEG sprite: `count` evenly spaced frames of the clip side by side."""
    count = max(1, min(int(count), 240))
    height = max(24, min(int(height), 240))
    info = probe(path)
    if info["duration"] <= 0 or not info["width"]:
        raise ValueError("source has no video stream")
    out = _cache_path(path, f"film{count}x{height}", "jpg")
    if out.exists():
        return out
    tile_w = max(2, round(height * info["width"] / info["height"] / 2) * 2)
    vf = f"fps={count}/{info['duration']:.6f},scale={tile_w}:{height},tile={count}x1"
    tmp = out.with_suffix(".tmp.jpg")
    subprocess.run(
        [_FFMPEG, "-v", "error", "-y", "-i", str(path), "-vf", vf, "-frames:v", "1", "-q:v", "5", str(tmp)],
        capture_output=True, timeout=_TIMEOUT, check=True,
    )
    tmp.replace(out)
    return out


def waveform(path: Path, bins: int) -> list[float]:
    """Peak amplitude (0..1) per bin of the clip's audio; empty list when the clip is silent/absent."""
    bins = max(8, min(int(bins), 4000))
    out = _cache_path(path, f"wave{bins}", "json")
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    pcm = subprocess.run(
        [_FFMPEG, "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
        capture_output=True, timeout=_TIMEOUT,
    ).stdout
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
    peaks: list[float] = []
    if samples:
        step = len(samples) / bins
        for i in range(bins):
            chunk = samples[int(i * step): max(int(i * step) + 1, int((i + 1) * step))]
            peaks.append(round(max(abs(v) for v in chunk) / 32768.0, 3) if chunk else 0.0)
    out.write_text(json.dumps(peaks), encoding="utf-8")
    return peaks


def extract_frame(path: Path, timestamp: float, output_path: Path) -> Path:
    """Extract a single visual frame from a media file at timestamp."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ts = max(0.0, float(timestamp))
    subprocess.run(
        [_FFMPEG, "-v", "error", "-y", "-ss", f"{ts:.3f}", "-i", str(path), "-frames:v", "1", "-q:v", "2", str(output_path)],
        capture_output=True, timeout=_TIMEOUT, check=True
    )
    return output_path


def splice_timeline_range(base_video: Path, replacement_clip: Path, t_start: float, t_end: float, output_path: Path) -> Path:
    """
    Splice replacement_clip into base_video for interval [t_start, t_end].
    Non-destructive: untouched sections are preserved with exact timestamps.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base_info = probe(base_video)
    rep_info = probe(replacement_clip)
    base_dur = base_info.get("duration", 0.0)
    rep_dur = rep_info.get("duration", 0.0)

    t0 = max(0.0, min(float(t_start), float(t_end)))
    t1 = max(t0, max(float(t_start), float(t_end)))
    if t1 <= t0:
        t1 = t0 + rep_dur

    has_audio = base_info.get("has_audio", False) and rep_info.get("has_audio", False)

    # Edge case 1: replacement covers entire video (or almost entire)
    if t0 <= 0.05 and t1 >= (base_dur - 0.05):
        shutil.copy2(replacement_clip, output_path)
        return output_path

    # Build filter complex
    if t0 <= 0.05:
        # Replacement at start, followed by tail of base
        if has_audio:
            filter_str = (
                f"[1:v]setpts=PTS-STARTPTS[v0];[1:a]asetpts=PTS-STARTPTS[a0];"
                f"[0:v]trim=start={t1:.3f},setpts=PTS-STARTPTS[v1];[0:a]atrim=start={t1:.3f},asetpts=PTS-STARTPTS[a1];"
                f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]"
            )
            cmd = [_FFMPEG, "-v", "error", "-y", "-i", str(base_video), "-i", str(replacement_clip),
                   "-filter_complex", filter_str, "-map", "[outv]", "-map", "[outa]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output_path)]
        else:
            filter_str = (
                f"[1:v]setpts=PTS-STARTPTS[v0];"
                f"[0:v]trim=start={t1:.3f},setpts=PTS-STARTPTS[v1];"
                f"[v0][v1]concat=n=2:v=1:a=0[outv]"
            )
            cmd = [_FFMPEG, "-v", "error", "-y", "-i", str(base_video), "-i", str(replacement_clip),
                   "-filter_complex", filter_str, "-map", "[outv]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output_path)]
    elif t1 >= (base_dur - 0.05):
        # Head of base, followed by replacement at end
        if has_audio:
            filter_str = (
                f"[0:v]trim=end={t0:.3f},setpts=PTS-STARTPTS[v0];[0:a]atrim=end={t0:.3f},asetpts=PTS-STARTPTS[a0];"
                f"[1:v]setpts=PTS-STARTPTS[v1];[1:a]asetpts=PTS-STARTPTS[a1];"
                f"[v0][a0][v1][a1]concat=n=2:v=1:a=1[outv][outa]"
            )
            cmd = [_FFMPEG, "-v", "error", "-y", "-i", str(base_video), "-i", str(replacement_clip),
                   "-filter_complex", filter_str, "-map", "[outv]", "-map", "[outa]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output_path)]
        else:
            filter_str = (
                f"[0:v]trim=end={t0:.3f},setpts=PTS-STARTPTS[v0];"
                f"[1:v]setpts=PTS-STARTPTS[v1];"
                f"[v0][v1]concat=n=2:v=1:a=0[outv]"
            )
            cmd = [_FFMPEG, "-v", "error", "-y", "-i", str(base_video), "-i", str(replacement_clip),
                   "-filter_complex", filter_str, "-map", "[outv]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output_path)]
    else:
        # Three segments: head + replacement + tail
        if has_audio:
            filter_str = (
                f"[0:v]trim=start=0:end={t0:.3f},setpts=PTS-STARTPTS[v0];[0:a]atrim=start=0:end={t0:.3f},asetpts=PTS-STARTPTS[a0];"
                f"[1:v]setpts=PTS-STARTPTS[v1];[1:a]asetpts=PTS-STARTPTS[a1];"
                f"[0:v]trim=start={t1:.3f},setpts=PTS-STARTPTS[v2];[0:a]atrim=start={t1:.3f},asetpts=PTS-STARTPTS[a2];"
                f"[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[outv][outa]"
            )
            cmd = [_FFMPEG, "-v", "error", "-y", "-i", str(base_video), "-i", str(replacement_clip),
                   "-filter_complex", filter_str, "-map", "[outv]", "-map", "[outa]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(output_path)]
        else:
            filter_str = (
                f"[0:v]trim=start=0:end={t0:.3f},setpts=PTS-STARTPTS[v0];"
                f"[1:v]setpts=PTS-STARTPTS[v1];"
                f"[0:v]trim=start={t1:.3f},setpts=PTS-STARTPTS[v2];"
                f"[v0][v1][v2]concat=n=3:v=1:a=0[outv]"
            )
            cmd = [_FFMPEG, "-v", "error", "-y", "-i", str(base_video), "-i", str(replacement_clip),
                   "-filter_complex", filter_str, "-map", "[outv]",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output_path)]

    subprocess.run(cmd, capture_output=True, timeout=_TIMEOUT * 3, check=True)
    return output_path
