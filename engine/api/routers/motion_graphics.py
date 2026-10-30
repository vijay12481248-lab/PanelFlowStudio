"""
Motion Graphics API Router for PanelFlow Studio.
Endpoints for preset discovery, single-frame interactive preview scrubbing,
and standalone procedural motion graphics video rendering.
"""

from typing import List, Dict, Any, Optional
import io
import base64
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from PIL import Image

from engine.render.motion.models import (
    MotionPresetDefinition,
    MotionPreviewRequest,
    MotionPreviewResponse,
    MotionRenderRequest,
    MotionRenderResponse,
)
from engine.render.motion.registry import MotionRegistry
from engine.render.encoder import FFmpegEncoder

router = APIRouter(prefix="/api/motion-graphics", tags=["motion-graphics"])


@router.get("/presets", response_model=List[MotionPresetDefinition])
def list_motion_presets():
    """Returns all registered motion graphics presets and their schema definitions."""
    return MotionRegistry.list_presets()


@router.get("/presets/{preset_id}", response_model=MotionPresetDefinition)
def get_motion_preset(preset_id: str):
    """Retrieves metadata and default properties for a specific motion preset."""
    preset = MotionRegistry.get_preset(preset_id)
    if not preset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Motion preset '{preset_id}' not found.",
        )
    return preset


@router.post("/preview", response_model=MotionPreviewResponse)
def preview_motion_frame(req: MotionPreviewRequest):
    """
    Renders a single frame of a motion graphics scene at a given timestamp for UI scrubbing.
    Returns JPEG base64 data for instant interactive rendering.
    """
    try:
        scene = MotionRegistry.create_scene(
            preset_id=req.preset_id,
            props=req.props,
            duration_sec=req.duration_sec,
            bounds=(req.width, req.height),
            aspect_ratio=req.aspect_ratio,
        )
        frame_img = scene.render_frame(req.timestamp)

        # Encode to JPEG in-memory
        buf = io.BytesIO()
        frame_img.convert("RGB").save(buf, format="JPEG", quality=88, optimize=True)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        return MotionPreviewResponse(
            preset_id=req.preset_id,
            timestamp=req.timestamp,
            image_base64=img_b64,
            width=frame_img.width,
            height=frame_img.height,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to render motion preview: {e}",
        )


@router.post("/render", response_model=MotionRenderResponse)
def render_motion_clip(req: MotionRenderRequest):
    """
    Renders a complete motion graphic scene to an MP4 video file using procedural frame streaming.
    """
    try:
        encoder = FFmpegEncoder()
        runtime = encoder.check_runtime()
        if not runtime["available"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"FFmpeg not found on host: {runtime.get('error')}",
            )

        ffmpeg_bin = encoder.ffmpeg_path
        out_dir = Path("storage/motion_renders")
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = req.output_filename or f"motion_{req.preset_id}_{uuid.uuid4().hex[:8]}.mp4"
        if not filename.endswith(".mp4"):
            filename += ".mp4"
        out_path = out_dir / filename

        scene = MotionRegistry.create_scene(
            preset_id=req.preset_id,
            props=req.props,
            duration_sec=req.duration_sec,
            bounds=(req.width, req.height),
        )

        total_frames = int(req.duration_sec * req.fps)
        w, h = req.width, req.height

        # Assemble ffmpeg command
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{w}x{h}",
            "-pix_fmt", "rgb24",
            "-r", str(req.fps),
            "-i", "-",  # Video frames from stdin
        ]

        if req.audio_file_path and Path(req.audio_file_path).exists():
            cmd.extend([
                "-i", str(req.audio_file_path),
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(out_path),
        ])

        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        try:
            for frame_idx in range(total_frames):
                t = frame_idx / req.fps
                frame = scene.render_frame(t)
                raw_bytes = frame.convert("RGB").tobytes()
                proc.stdin.write(raw_bytes)
            proc.stdin.close()
            _, stderr = proc.communicate(timeout=120)
        except Exception:
            proc.kill()
            raise

        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg encoding failed with code {proc.returncode}: {stderr.decode(errors='ignore')[:300]}")

        file_size_mb = out_path.stat().st_size / (1024 * 1024)

        return MotionRenderResponse(
            success=True,
            preset_id=req.preset_id,
            output_path=str(out_path.resolve()),
            duration_sec=req.duration_sec,
            file_size_mb=round(file_size_mb, 2),
            message=f"Rendered {total_frames} frames ({req.duration_sec}s) at {req.fps} fps successfully.",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Motion graphics render failed: {e}",
        )
