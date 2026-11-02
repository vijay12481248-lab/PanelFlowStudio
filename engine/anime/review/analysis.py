"""Analyse: ffmpeg scene detection, audio extraction, transcript (embedded subs first, ASR fallback)."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from engine.anime.review.models import EpisodeAnalysis, IngestRecord, Segment, Shot

MIN_SHOT_SEC = 0.5


def detect_shots(video: Path, duration: float, threshold: float = 0.3) -> list[Shot]:
    """Shot boundaries from ffmpeg's scene score; tiny shots are merged into their predecessor."""
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(video), "-an", "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True)
    cuts = [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]
    bounds = [0.0]
    for t in sorted(cuts):
        if t - bounds[-1] >= MIN_SHOT_SEC and duration - t >= MIN_SHOT_SEC:
            bounds.append(t)
    bounds.append(duration)
    return [Shot(idx=i, start=round(a, 3), end=round(b, 3)) for i, (a, b) in enumerate(zip(bounds, bounds[1:]))]


def extract_audio(video: Path, wav: Path) -> Path:
    wav.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                   check=True, capture_output=True)
    return wav


TEXT_SUB_CODECS = {"subrip", "ass", "ssa", "mov_text", "webvtt", "text"}
ENGLISH = {"eng", "en", "english"}


def english_subtitle_index(video: Path) -> int | None:
    """Absolute stream index of the first English *text* subtitle track (image subs cannot be converted)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries",
                        "stream=index,codec_name:stream_tags=language", "-of", "json", str(video)],
                       capture_output=True, text=True)
    for s in json.loads(r.stdout or "{}").get("streams", []):
        if s.get("codec_name") in TEXT_SUB_CODECS and s.get("tags", {}).get("language", "").lower() in ENGLISH:
            return s["index"]
    return None


def embedded_subtitles(video: Path, tmp: Path) -> list[Segment]:
    """English embedded subtitles as segments; [] when there are none (other languages go through ASR translation)."""
    idx = english_subtitle_index(video)
    if idx is None:
        return []
    srt = tmp / "embedded.srt"
    r = subprocess.run(["ffmpeg", "-y", "-i", str(video), "-map", f"0:{idx}", str(srt)], capture_output=True)
    if r.returncode != 0 or not srt.exists():
        return []
    return parse_srt(srt.read_text(encoding="utf-8", errors="ignore"))


def _ts(s: str) -> float:
    h, m, rest = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest.replace(",", "."))


def parse_srt(text: str) -> list[Segment]:
    out = []
    for block in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n")):
        lines = block.split("\n")
        i = next((k for k, ln in enumerate(lines) if "-->" in ln), None)
        if i is None:
            continue
        a, b = (x.strip() for x in lines[i].split("-->"))
        body = re.sub(r"<[^>]+>|\{[^}]*\}", "", " ".join(lines[i + 1:])).strip()
        if body:
            out.append(Segment(start=_ts(a), end=_ts(b.split()[0]), text=body))
    return out


def transcribe(wav: Path) -> tuple[list[Segment], str | None]:
    """faster-whisper (the narration stack's cached model); non-English speech is translated to English."""
    from engine.narration.runtime import audio as rt  # reuse offline setup + 16k loader + STT config
    from engine.narration.runtime.roles import load_stt_config

    rt._force_offline()
    from faster_whisper import WhisperModel

    cfg = load_stt_config()
    model = WhisperModel(cfg.model, device=cfg.device, compute_type=cfg.compute_type)
    try:
        segs, info = model.transcribe(rt.to_16k(wav), task="translate", vad_filter=True, beam_size=3)
        return [Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip()) for s in segs if s.text.strip()], info.language
    finally:
        del model
        rt.release_audio_models()


def analyze(rec: IngestRecord, workspace: Path, use_asr: bool = True) -> EpisodeAnalysis:
    video = Path(rec.local_path)
    shots = detect_shots(video, rec.duration_sec)
    transcript, source, lang, wav = embedded_subtitles(video, workspace), "embedded_subs", None, None
    if rec.has_audio:
        wav = extract_audio(video, workspace / "audio_16k.wav")
    if not transcript:
        source = "none"
        if rec.has_audio and use_asr:
            transcript, lang = transcribe(wav)
            source = "asr" if transcript else "none"
    result = EpisodeAnalysis(duration_sec=rec.duration_sec, shots=shots, transcript=transcript,
                             transcript_source=source, language=lang, audio_path=str(wav) if wav else None)
    (workspace / "analysis.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result
