"""Motion Bank Ingest: Rights gate validation, video acquisition (upload/URL/YouTube), and ffprobe analysis."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from engine.acquisition.rights.models import RightsDeclaration, RightsStatus
from engine.motion_bank.models import MotionIngestRecord, MotionSourceType

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}


def probe_video(path: Path) -> dict:
    """Probes media metadata using ffprobe; raises ValueError when not playable video."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise ValueError(f"Not a readable media file: {r.stderr.strip()[:200]}")
    data = json.loads(r.stdout)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        raise ValueError("File contains no readable video stream")
    num, _, den = v.get("r_frame_rate", "24/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    return {
        "duration": float(data.get("format", {}).get("duration") or v.get("duration") or 0),
        "width": int(v.get("width", 0)),
        "height": int(v.get("height", 0)),
        "fps": round(fps, 3),
        "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


def compute_sha256(path: Path) -> str:
    """Calculates SHA256 checksum of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download_url(url: str, dest_dir: Path) -> Path:
    """Downloads a video stream via yt-dlp."""
    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError("URL ingest requires yt-dlp (pip install yt-dlp); or pass a local file path.") from e

    dest_dir.mkdir(parents=True, exist_ok=True)
    out_template = str(dest_dir / "download.%(ext)s")
    opts = {
        "outtmpl": out_template,
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        out_path = Path(filename).with_suffix(".mp4")
        if not out_path.exists():
            out_path = Path(filename)
        return out_path


def ingest_motion_source(
    source: str,
    workspace: Path,
    rights: RightsDeclaration,
    title: str | None = None,
) -> MotionIngestRecord:
    """
    Ingests video into the Motion Bank workspace.
    Validates the rights gate (refuses UNKNOWN and COMMENTARY_REVIEW without notes).
    """
    rights.validate_for_acquisition()
    workspace.mkdir(parents=True, exist_ok=True)
    source_clean = source.strip().strip('"')

    is_url = bool(re.match(r"https?://", source_clean))
    is_yt = bool(re.search(r"(youtube\.com|youtu\.be)", source_clean, re.IGNORECASE))

    if is_url:
        source_type = MotionSourceType.YOUTUBE if is_yt else MotionSourceType.URL
        local = _download_url(source_clean, workspace)
    else:
        source_type = MotionSourceType.LOCAL_FILE
        src = Path(source_clean)
        if not src.is_file():
            raise FileNotFoundError(f"Source file not found: {source_clean}")
        if src.suffix.lower() not in VIDEO_EXTS:
            raise ValueError(f"Unsupported video format: {src.suffix}")
        local = workspace / f"source{src.suffix.lower()}"
        if src.resolve() != local.resolve():
            shutil.copy2(src, local)

    info = probe_video(local)
    if info["duration"] <= 0:
        raise ValueError("Video duration is zero or unreadable")

    rec = MotionIngestRecord(
        source_uri=source_clean,
        source_type=source_type,
        local_path=str(local.resolve()),
        sha256=compute_sha256(local),
        title=title or (Path(source_clean).stem if not is_url else local.stem),
        duration_sec=round(info["duration"], 3),
        width=info["width"],
        height=info["height"],
        fps=info["fps"],
        has_audio=info["has_audio"],
        rights=rights,
        ingested_at=time.time(),
    )

    (workspace / "source.json").write_text(rec.model_dump_json(indent=2), encoding="utf-8")
    return rec
