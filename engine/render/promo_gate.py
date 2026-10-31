"""Final-video check: no scanlator promotion may be visible anywhere in a rendered video."""
from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.imaging.content_cleanup import is_promo_text, load_rules
from engine.render.encoder import FFmpegEncoder


def scan_video_for_promotion(video_path: Path | str, *, every_sec: float = 1.0, ocr_engine=None,
                             cancelled=lambda: False) -> list[dict]:
    """Sample one frame every `every_sec`, OCR it, and return every promotional text hit with its time."""
    ffmpeg = FFmpegEncoder().ffmpeg_path
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to check the rendered video for promotional text.")
    if ocr_engine is None:
        from engine.ocr.providers.registry import ocr_registry
        ocr_engine = ocr_registry.get_default_engine()
    if "mock" in ocr_engine.engine_id.lower() or not ocr_engine.is_available():
        raise RuntimeError("Checking the video for promotional text requires real OCR.")
    labels = load_rules().labels
    hits = []
    with TemporaryDirectory(prefix="panelflow-promo-gate-") as temp:
        subprocess.run([ffmpeg, "-v", "error", "-i", str(video_path), "-vf", f"fps=1/{every_sec}", "-q:v", "3",
                        str(Path(temp) / "f_%05d.jpg")], check=True, capture_output=True, timeout=1800)
        for frame in sorted(Path(temp).glob("f_*.jpg")):
            if cancelled():
                raise RuntimeError("Promotional text check cancelled")
            time_sec = (int(frame.stem[2:]) - 1) * every_sec
            for region in ocr_engine.extract_text(frame, "video-frame").regions:
                if region.detected_text.strip() and is_promo_text(region.detected_text, labels):
                    hits.append({"time_sec": round(time_sec, 1), "text": region.detected_text, "bbox": region.bbox})
    return hits


def describe_hits(hits: list[dict], limit: int = 5) -> str:
    shown = ", ".join(f"{int(h['time_sec'] // 60)}:{h['time_sec'] % 60:04.1f} \"{h['text']}\"" for h in hits[:limit])
    more = f" and {len(hits) - limit} more" if len(hits) > limit else ""
    return f"Promotional text is visible in the video at {shown}{more}."
