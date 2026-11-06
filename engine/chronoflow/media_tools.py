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
