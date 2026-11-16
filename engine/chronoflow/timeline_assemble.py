"""ChronoFlow Storyboard Timeline Assembly & Multi-Clip Sequence Normalization.

Concatenates rendered storyboard cards into a unified master timeline video, scales mixed
resolutions (e.g. 960x544, 1344x768) with letterbox/pillarbox padding to a standardized canvas,
and connects seamlessly to ChronoFlow Audio Studio by generating an aligned Sound Plan.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from engine.chronoflow.media_tools import _FFMPEG, _FFPROBE, _TIMEOUT, probe, resolve_media
from engine.chronoflow.pipeline import COMFY_INPUT_DIR, COMFY_OUTPUT_DIR, STUDIO_OUTPUT_DIR
from engine.chronoflow import start_modes

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_DIRS = [STUDIO_OUTPUT_DIR, COMFY_OUTPUT_DIR, COMFY_INPUT_DIR]


def resolve_scene_clip(scene: dict[str, Any], search_dirs: list[Path] | None = None) -> Path | None:
    """Find the rendered video file on disk for a storyboard scene.
    
    Checks `rendered_video_filename`, `filename`, `video_file`, `rendered_video`, and `video_url`.
    Returns an existing absolute Path, or None.
    """
    dirs = search_dirs or DEFAULT_SEARCH_DIRS
    candidates = [
        scene.get("rendered_video_filename"),
        scene.get("filename"),
        scene.get("video_file"),
        scene.get("rendered_video"),
        scene.get("video_url"),
    ]

    for raw in candidates:
        if not raw:
            continue
        raw_str = str(raw).strip()
        if raw_str.startswith("/chronoflow/outputs/"):
            raw_str = raw_str.replace("/chronoflow/outputs/", "")
        elif raw_str.startswith("/"):
            raw_str = Path(raw_str).name

        p = Path(raw_str)
        if p.is_file():
            return p.resolve()

        fname = p.name
        for d in dirs:
            cand = d / fname
            if cand.is_file():
                return cand.resolve()

        # Fallback to resolve_media
        cand = resolve_media(fname)
        if cand and cand.is_file():
            return cand.resolve()

    return None


def assemble_storyboard_sequence(
    scenes: list[dict[str, Any]],
    out_path: Path,
    target_width: int = 1920,
    target_height: int = 1080,
    fps: float = 24.0,
    approved_only: bool = False,
    search_dirs: list[Path] | None = None,
    create_sound_plan: bool = True,
    sound_plan_title: str | None = None,
) -> dict[str, Any]:
    """Assemble a storyboard sequence into a unified master timeline video.
    
    - Normalizes mixed-resolution shots with letterbox/pillarbox padding to target_width x target_height.
    - Standardizes frame rate and audio format (stereo 48kHz, generating silence for mute shots).
    - Concatenates normalized clips into `out_path`.
    - Automatically builds an Audio Studio Sound Plan if `create_sound_plan` is True.
    
    Raises HTTPException(400) if shots are missing or unrendered.
    """
    if not scenes:
        raise HTTPException(status_code=400, detail="Storyboard contains no shots to assemble.")

    target_scenes = [s for s in scenes if s.get("approved")] if approved_only else list(scenes)
    if not target_scenes:
        raise HTTPException(status_code=400, detail="No approved shots found to assemble.")

    # 1. Validate that all target shots have valid video files
    clip_entries: list[tuple[int, dict[str, Any], Path]] = []
    for idx, s in enumerate(target_scenes):
        shot_num = s.get("shot_index", idx + 1)
        shot_title = s.get("title") or f"Shot {shot_num}"
        resolved = resolve_scene_clip(s, search_dirs)
        if not resolved:
            raise HTTPException(
                status_code=400,
                detail=f"Shot {shot_num} ('{shot_title}') has not been rendered yet or video file is missing."
            )
        clip_entries.append((shot_num, s, resolved))

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Normalize each clip in a temporary directory
    with tempfile.TemporaryDirectory(prefix="chronoflow_assembly_") as tmpdir:
        tmp = Path(tmpdir)
        norm_chunks: list[Path] = []

        v_filter = (
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={fps}"
        )

        for i, (shot_num, scene, src_path) in enumerate(clip_entries):
            out_chunk = tmp / f"chunk_{i:04d}.mp4"
            info = probe(src_path)
            has_audio = info.get("has_audio", False)
            clip_dur = info.get("duration") or float(scene.get("duration") or start_modes.SEG_SECONDS)

            if has_audio:
                cmd = [
                    _FFMPEG, "-y",
                    "-i", str(src_path),
                    "-vf", v_filter,
                    "-af", "aformat=sample_rates=48000:channel_layouts=stereo",
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k",
                    str(out_chunk),
                ]
            else:
                cmd = [
                    _FFMPEG, "-y",
                    "-i", str(src_path),
                    "-f", "lavfi", "-t", str(clip_dur), "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                    "-vf", v_filter,
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0", "-map", "1:a:0",
                    "-shortest",
                    str(out_chunk),
                ]

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT)
            if res.returncode != 0 or not out_chunk.exists():
                logger.error("FFmpeg normalization failed for Shot %d (%s): %s", shot_num, src_path, res.stderr)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to normalize Shot {shot_num}: {res.stderr[:200]}"
                )
            norm_chunks.append(out_chunk)

        # 3. Concatenate normalized chunks via concat demuxer
        list_file = tmp / "concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for chunk in norm_chunks:
                # Format for FFmpeg concat: file 'path' with escaped single quotes
                escaped = str(chunk.resolve()).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        cmd_concat = [
            _FFMPEG, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(out_path),
        ]
        res_concat = subprocess.run(cmd_concat, capture_output=True, text=True, timeout=_TIMEOUT)
        if res_concat.returncode != 0 or not out_path.exists():
            logger.error("FFmpeg concat failed: %s", res_concat.stderr)
            raise HTTPException(
                status_code=500,
                detail=f"Timeline assembly concatenation failed: {res_concat.stderr[:200]}"
            )

    # 4. Probe final assembled media
    final_info = probe(out_path)
    total_duration = final_info.get("duration", 0.0)

    # 5. Connect to Audio Studio Sound Plan if requested
    sound_plan_id: str | None = None
    if create_sound_plan:
        try:
            from engine.api.routers.audio_studio import get_engine
            from engine.audio.studio.plan import Cue, snap

            audio_engine = get_engine()
            plan = audio_engine.create_plan(
                video_path=out_path,
                fps=fps,
                duration=total_duration,
                mode="auto",
            )
            if sound_plan_title:
                plan.note = sound_plan_title
            else:
                plan.note = f"Soundtrack - {out_path.stem}"

            # Populate picture cuts and record scene list
            curr_t = 0.0
            cuts: list[float] = [0.0]
            scenes_list: list[dict] = []
            for idx, (_, scene, _) in enumerate(clip_entries):
                shot_dur = float(scene.get("duration") or start_modes.SEG_SECONDS)
                t_in = snap(curr_t, fps)
                if curr_t > 0.0:
                    cuts.append(t_in)
                scenes_list.append(scene)
                curr_t += shot_dur

            plan.cuts = cuts
            audio_engine.store.save(plan)

            # Auto-design atmospheric soundscapes and foley cues from scene visual semantics
            try:
                from engine.audio.studio.foley_generator import auto_populate_sound_plan
                plan = auto_populate_sound_plan(plan.id, scenes_list, auto_source=True)
            except Exception as auto_exc:
                logger.warning("Foley auto-population exception: %s", auto_exc)

            sound_plan_id = plan.id
            logger.info("Created and auto-designed Audio Studio Sound Plan %s for assembled storyboard", sound_plan_id)
        except Exception as exc:
            logger.warning("Failed to auto-create Audio Studio Sound Plan: %s", exc)

    return {
        "success": True,
        "master_video": f"/chronoflow/outputs/{out_path.name}",
        "filename": out_path.name,
        "duration": round(total_duration, 2),
        "fps": fps,
        "width": target_width,
        "height": target_height,
        "shot_count": len(clip_entries),
        "sound_plan_id": sound_plan_id,
        "local_path": str(out_path),
    }
