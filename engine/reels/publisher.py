"""PanelFlow Studio - YouTube Shorts & Reels Packaging and Publishing Pipeline.

Coordinates horizontal 16:9 to vertical 9:16 auto-cut, focal tracking reframing,
karaoke subtitle burning, EBU R128 (-14 LUFS) audio mastering, and publishing metadata.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from engine.reels.reframer import compute_reframing_plan, probe_video_meta
from engine.reels.subtitles import align_transcript_words, build_karaoke_ass

logger = logging.getLogger("panelflow.reels.publisher")


@dataclass
class ReelAutoCutRequest:
    input_video_path: str
    output_path: str | None = None
    output_dir: str | None = None
    hook_text: str = ""
    transcript: str = ""
    audio_path: str | None = None
    shot_cuts: list[float] | None = None
    burn_subtitles: bool = True
    target_duration: float | None = None
    reframing_mode: str = "shot_stable"  # "shot_stable", "smooth_pan", "center"
    title: str = "Shorts Reel"
    tags: str = "#shorts #story #viral #panelflow"


@dataclass
class ReelAutoCutResult:
    success: bool
    output_video_path: str
    duration_sec: float
    aspect_ratio: str = "9:16"
    resolution: list[int] = field(default_factory=lambda: [1080, 1920])
    publish_meta_path: str = ""
    subtitles_ass_path: str | None = None
    crop_filter_expr: str = ""
    message: str = ""


def has_audio_stream(video_path: Path | str) -> bool:
    """Check if video contains an audio stream via ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "json",
        str(video_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        return len(data.get("streams", [])) > 0
    except Exception:
        return False


def autocut_horizontal_to_reel(request: ReelAutoCutRequest) -> ReelAutoCutResult:
    """Convert horizontal video into high-engagement vertical 9:16 YouTube Short or Reel."""
    input_str = str(request.input_video_path)
    if input_str.startswith("/chronoflow/outputs/"):
        from engine.chronoflow.pipeline import STUDIO_OUTPUT_DIR
        input_path = STUDIO_OUTPUT_DIR / Path(input_str).name
    elif input_str.startswith("http://") or input_str.startswith("https://"):
        from engine.chronoflow.pipeline import STUDIO_OUTPUT_DIR
        input_path = STUDIO_OUTPUT_DIR / Path(input_str).name
    else:
        input_path = Path(input_str)

    if not input_path.exists() or input_path.stat().st_size == 0:
        return ReelAutoCutResult(
            success=False,
            output_video_path="",
            duration_sec=0.0,
            message=f"Input video does not exist or is empty: {input_path}",
        )

    # 1. Probe input video
    meta = probe_video_meta(input_path)
    in_w = meta["width"]
    in_h = meta["height"]
    total_dur = meta["duration"]

    # Duration limit: YouTube Shorts max is 60s, sweet spot is 20-58s
    max_short_duration = 58.5
    render_dur = total_dur
    if request.target_duration and request.target_duration > 0:
        render_dur = min(request.target_duration, total_dur)
    elif total_dur > max_short_duration:
        render_dur = max_short_duration

    # 2. Determine destination directories
    if request.output_path:
        out_file = Path(request.output_path)
        out_dir = out_file.parent
    else:
        out_dir = Path(request.output_dir) if request.output_dir else input_path.parent / "reels"
        out_file = out_dir / f"{input_path.stem}_reel_9x16.mp4"

    out_dir.mkdir(parents=True, exist_ok=True)

    # 3. Compute 9:16 reframing trajectory
    logger.info("Computing 9:16 reframing plan for %s...", input_path.name)
    trajectory = compute_reframing_plan(
        video_path=input_path,
        cuts=request.shot_cuts,
        mode=request.reframing_mode,
        target_w=1080,
        target_h=1920,
    )

    vf_base = trajectory.to_ffmpeg_vf()

    # 4. Compile animated karaoke subtitles
    ass_path = None
    if request.burn_subtitles:
        audio_src = request.audio_path or str(input_path)
        words = align_transcript_words(
            audio_path=audio_src,
            transcript=request.transcript,
            duration_sec=render_dur,
        )
        if words or request.hook_text:
            ass_path = out_dir / f"{input_path.stem}_captions.ass"
            build_karaoke_ass(
                words=words,
                hook=request.hook_text,
                output_path=ass_path,
            )

    # 5. Build FFmpeg command
    vf = vf_base
    if ass_path and ass_path.exists():
        # Escape path for FFmpeg subtitles filter on Windows
        escaped_ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
        vf += f",subtitles='{escaped_ass}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-v", "error",
        "-i", str(input_path),
    ]

    # Duration clamp if needed
    if render_dur < total_dur:
        cmd.extend(["-t", f"{render_dur:.3f}"])

    cmd.extend(["-vf", vf])

    # Audio mastering: loudnorm to -14.0 LUFS
    has_audio = has_audio_stream(input_path)
    if has_audio:
        cmd.extend([
            "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
        ])
    else:
        cmd.append("-an")

    # Video codec settings
    cmd.extend([
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out_file),
    ])

    logger.info("Running FFmpeg 9:16 packaging to %s...", out_file.name)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        logger.error("FFmpeg reel rendering failed: %s\nStderr: %s", exc, exc.stderr)
        return ReelAutoCutResult(
            success=False,
            output_video_path="",
            duration_sec=0.0,
            message=f"FFmpeg error: {exc.stderr}",
        )

    # 6. Generate viral publishing metadata (PUBLISH.md)
    pub_path = out_dir / f"{input_path.stem}_PUBLISH.md"
    hook_line = request.hook_text if request.hook_text else request.title
    pub_content = (
        f"# {request.title}\n\n"
        f"**Hook (First 2.5s):** {hook_line}\n\n"
        f"**Suggested Title:** {request.title} #shorts\n\n"
        f"**Description:**\n"
        f"{request.transcript or 'An intense original story unfold in this vertical cut.'}\n\n"
        f"{request.tags}\n\n"
        f"---\n"
        f"_Notice: AI-generated visuals, animation, and voice. Tick synthetic/altered content disclosure upon upload._\n"
    )
    pub_path.write_text(pub_content, encoding="utf-8")

    actual_meta = probe_video_meta(out_file)

    return ReelAutoCutResult(
        success=True,
        output_video_path=str(out_file),
        duration_sec=actual_meta["duration"],
        aspect_ratio="9:16",
        resolution=[actual_meta["width"], actual_meta["height"]],
        publish_meta_path=str(pub_path),
        subtitles_ass_path=str(ass_path) if ass_path else None,
        crop_filter_expr=trajectory.to_ffmpeg_crop_expr(),
        message="Shorts / Reel vertical cut rendered successfully.",
    )
