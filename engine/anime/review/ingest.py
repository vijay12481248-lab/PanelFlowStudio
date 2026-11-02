"""Ingest: rights gate -> download/copy -> validate -> source.json."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from engine.acquisition.rights.models import RightsDeclaration
from engine.anime.review.models import IngestRecord

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}


def slugify(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "episode"


def probe(path: Path) -> dict:
    """ffprobe facts; raises ValueError when the file is not playable video."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError(f"not a readable media file: {r.stderr.strip()[:200]}")
    data = json.loads(r.stdout)
    v = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise ValueError("file has no video stream")
    num, _, den = v.get("r_frame_rate", "24/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    return {
        "duration": float(data["format"].get("duration") or v.get("duration") or 0),
        "width": int(v["width"]), "height": int(v["height"]), "fps": round(fps, 3),
        "has_audio": any(s["codec_type"] == "audio" for s in data["streams"]),
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _download(url: str, dest_dir: Path) -> Path:
    try:
        import yt_dlp  # optional dependency: only needed for URL sources
    except ImportError as e:
        raise RuntimeError("URL ingest needs yt-dlp (pip install yt-dlp); or pass a local file path") from e
    opts = {"outtmpl": str(dest_dir / "download.%(ext)s"), "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
            "merge_output_format": "mp4", "noplaylist": True, "quiet": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info)).with_suffix(".mp4") if not Path(ydl.prepare_filename(info)).exists() \
            else Path(ydl.prepare_filename(info))


def ingest(source: str, workspace: Path, rights: RightsDeclaration, title: str | None = None) -> IngestRecord:
    """Refuses UNKNOWN rights (and COMMENTARY_REVIEW without notes) before touching the source."""
    rights.validate_for_acquisition()
    workspace.mkdir(parents=True, exist_ok=True)
    source = source.strip().strip('"')
    if re.match(r"https?://", source):
        local = _download(source, workspace)
    else:
        src = Path(source)
        if not src.is_file():
            raise FileNotFoundError(f"source file not found: {source}")
        if src.suffix.lower() not in VIDEO_EXTS:
            raise ValueError(f"unsupported video type: {src.suffix}")
        local = workspace / f"source{src.suffix.lower()}"
        if src.resolve() != local.resolve():
            shutil.copy2(src, local)
    info = probe(local)
    if info["duration"] <= 0:
        raise ValueError("video has zero duration")
    rec = IngestRecord(
        source_uri=source, local_path=str(local.resolve()), sha256=_sha256(local),
        title=title or Path(source).stem if local.name.startswith("source") else (title or local.stem),
        duration_sec=round(info["duration"], 3), width=info["width"], height=info["height"], fps=info["fps"],
        has_audio=info["has_audio"], rights=rights, ingested_at=time.time(),
    )
    (workspace / "source.json").write_text(rec.model_dump_json(indent=2), encoding="utf-8")
    return rec
