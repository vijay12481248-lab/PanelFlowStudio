"""FastAPI router for YouTube Shorts & Reels 9:16 Intelligent Auto-Cut."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from engine.reels.publisher import (
    ReelAutoCutRequest,
    ReelAutoCutResult,
    autocut_horizontal_to_reel,
)
from engine.reels.reframer import compute_reframing_plan
from engine.reels.subtitles import align_transcript_words, build_karaoke_ass

logger = logging.getLogger("panelflow.api.reels")

router = APIRouter(prefix="/api/reels", tags=["reels"])


class ReelAutoCutApiRequest(BaseModel):
    input_video_path: str = Field(..., description="Path to source horizontal 16:9 video file")
    output_path: str | None = Field(None, description="Optional target destination mp4 path")
    hook_text: str = Field("", description="Punchy hook text displayed on screen for the first 2.5 seconds")
    transcript: str = Field("", description="Full narration or dialogue transcript")
    audio_path: str | None = Field(None, description="Optional separate audio wav path for Whisper alignment")
    shot_cuts: list[float] | None = Field(None, description="List of shot cut timestamps in seconds")
    burn_subtitles: bool = Field(True, description="Whether to burn animated karaoke subtitles")
    target_duration: float | None = Field(None, description="Optional maximum target duration in seconds")
    reframing_mode: Literal["shot_stable", "smooth_pan", "center"] = Field(
        "shot_stable", description="Reframing mode"
    )
    title: str = Field("Shorts Reel", description="Reel title for publishing copy")
    tags: str = Field("#shorts #story #viral #panelflow", description="Publishing hashtags")


class ReelAutoCutApiResponse(BaseModel):
    success: bool
    output_video_path: str
    duration_sec: float
    aspect_ratio: str = "9:16"
    resolution: list[int]
    publish_meta_path: str
    subtitles_ass_path: str | None = None
    crop_filter_expr: str = ""
    message: str = ""


class PreviewReframingRequest(BaseModel):
    video_path: str
    shot_cuts: list[float] | None = None
    reframing_mode: Literal["shot_stable", "smooth_pan", "center"] = "shot_stable"


class PreviewReframingResponse(BaseModel):
    source_width: int
    source_height: int
    crop_width: int
    crop_height: int
    target_width: int
    target_height: int
    ffmpeg_filter: str
    crop_expression: str
    shot_crops: list[dict]


class GenerateSubtitlesRequest(BaseModel):
    transcript: str
    hook: str = ""
    audio_path: str | None = None
    duration_sec: float | None = None


class GenerateSubtitlesResponse(BaseModel):
    ass_content: str
    word_count: int


def _resolve_video_path(path_str: str) -> Path:
    if path_str.startswith("/chronoflow/outputs/"):
        from engine.chronoflow.pipeline import STUDIO_OUTPUT_DIR
        return STUDIO_OUTPUT_DIR / Path(path_str).name
    return Path(path_str)


@router.post("/autocut", response_model=ReelAutoCutApiResponse)
def autocut_reel(req: ReelAutoCutApiRequest):
    """Auto-cut a horizontal 16:9 video into a vertical 9:16 YouTube Short or Instagram Reel."""
    p = _resolve_video_path(req.input_video_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Source video file not found: {req.input_video_path}")

    req_obj = ReelAutoCutRequest(
        input_video_path=str(p),
        output_path=req.output_path,
        hook_text=req.hook_text,
        transcript=req.transcript,
        audio_path=req.audio_path,
        shot_cuts=req.shot_cuts,
        burn_subtitles=req.burn_subtitles,
        target_duration=req.target_duration,
        reframing_mode=req.reframing_mode,
        title=req.title,
        tags=req.tags,
    )

    result = autocut_horizontal_to_reel(req_obj)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return ReelAutoCutApiResponse(
        success=result.success,
        output_video_path=result.output_video_path,
        duration_sec=result.duration_sec,
        aspect_ratio=result.aspect_ratio,
        resolution=result.resolution,
        publish_meta_path=result.publish_meta_path,
        subtitles_ass_path=result.subtitles_ass_path,
        crop_filter_expr=result.crop_filter_expr,
        message=result.message,
    )


@router.post("/preview_reframing", response_model=PreviewReframingResponse)
def preview_reframing(req: PreviewReframingRequest):
    """Calculate and preview the 9:16 focal reframing trajectory without encoding."""
    p = _resolve_video_path(req.video_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Source video file not found: {req.video_path}")

    trajectory = compute_reframing_plan(
        video_path=p,
        cuts=req.shot_cuts,
        mode=req.reframing_mode,
        target_w=1080,
        target_h=1920,
    )

    return PreviewReframingResponse(
        source_width=trajectory.source_width,
        source_height=trajectory.source_height,
        crop_width=trajectory.crop_width,
        crop_height=trajectory.crop_height,
        target_width=trajectory.target_width,
        target_height=trajectory.target_height,
        ffmpeg_filter=trajectory.to_ffmpeg_vf(),
        crop_expression=trajectory.to_ffmpeg_crop_expr(),
        shot_crops=trajectory.shot_crops,
    )


@router.post("/generate_subtitles", response_model=GenerateSubtitlesResponse)
def generate_subtitles(req: GenerateSubtitlesRequest):
    """Compile animated word-by-word karaoke ASS subtitles."""
    words = align_transcript_words(
        audio_path=req.audio_path,
        transcript=req.transcript,
        duration_sec=req.duration_sec,
    )
    ass = build_karaoke_ass(words=words, hook=req.hook)
    return GenerateSubtitlesResponse(
        ass_content=ass,
        word_count=len(words),
    )
