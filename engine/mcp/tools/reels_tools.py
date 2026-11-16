"""Reels and Shorts MCP tools: 9:16 vertical reframing, focal tracking, and animated karaoke subtitles."""
from __future__ import annotations

from typing import Any

from engine.mcp.client_bridge import bridge
from engine.mcp.registry import registry

_BASE = "/api/reels"


def _schema(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def _body(**kw: Any) -> dict[str, Any]:
    return {k: v for k, v in kw.items() if v is not None}


@registry.tool(
    name="panelflow_reels_autocut",
    description="Convert a horizontal 16:9 video into a vertical 9:16 YouTube Short or Instagram Reel with AI focal tracking reframing, animated karaoke subtitles, and -14 LUFS mastered audio.",
    input_schema=_schema(
        {
            "input_video_path": {"type": "string", "description": "Absolute path to source horizontal 16:9 video file"},
            "output_path": {"type": "string", "description": "Optional destination path for the 9:16 vertical mp4"},
            "hook_text": {"type": "string", "description": "Punchy hook banner displayed in top-third for the first 2.5 seconds"},
            "transcript": {"type": "string", "description": "Full narration or dialogue text for karaoke subtitles"},
            "audio_path": {"type": "string", "description": "Optional separate audio file for word alignment"},
            "shot_cuts": {"type": "array", "items": {"type": "number"}, "description": "Optional shot cut timestamps in seconds"},
            "burn_subtitles": {"type": "boolean", "description": "Whether to burn animated karaoke subtitles (default: true)"},
            "target_duration": {"type": "number", "description": "Optional maximum duration in seconds (clamped to 58s max for Shorts)"},
            "reframing_mode": {
                "type": "string",
                "enum": ["shot_stable", "smooth_pan", "center"],
                "description": "Reframing camera mode (default: shot_stable)",
            },
            "title": {"type": "string", "description": "Title of the reel for metadata and publishing copy"},
            "tags": {"type": "string", "description": "Hashtags for publishing copy"},
        },
        ["input_video_path"],
    ),
    domain="chronoflow",
)
async def reels_autocut(
    input_video_path: str,
    output_path: str | None = None,
    hook_text: str | None = None,
    transcript: str | None = None,
    audio_path: str | None = None,
    shot_cuts: list[float] | None = None,
    burn_subtitles: bool | None = None,
    target_duration: float | None = None,
    reframing_mode: str | None = None,
    title: str | None = None,
    tags: str | None = None,
) -> dict[str, Any]:
    return await bridge.post(
        f"{_BASE}/autocut",
        _body(
            input_video_path=input_video_path,
            output_path=output_path,
            hook_text=hook_text or "",
            transcript=transcript or "",
            audio_path=audio_path,
            shot_cuts=shot_cuts,
            burn_subtitles=burn_subtitles if burn_subtitles is not None else True,
            target_duration=target_duration,
            reframing_mode=reframing_mode or "shot_stable",
            title=title or "Shorts Reel",
            tags=tags or "#shorts #story #viral #panelflow",
        ),
    )


@registry.tool(
    name="panelflow_reels_preview_reframing",
    description="Calculate and preview the 9:16 focal crop trajectory, shot crops, and FFmpeg filter expression without performing full video encoding.",
    input_schema=_schema(
        {
            "video_path": {"type": "string", "description": "Absolute path to source horizontal video file"},
            "shot_cuts": {"type": "array", "items": {"type": "number"}, "description": "Optional shot cut timestamps in seconds"},
            "reframing_mode": {"type": "string", "enum": ["shot_stable", "smooth_pan", "center"], "description": "Reframing camera mode"},
        },
        ["video_path"],
    ),
    domain="chronoflow",
)
async def reels_preview_reframing(
    video_path: str,
    shot_cuts: list[float] | None = None,
    reframing_mode: str | None = None,
) -> dict[str, Any]:
    return await bridge.post(
        f"{_BASE}/preview_reframing",
        _body(
            video_path=video_path,
            shot_cuts=shot_cuts,
            reframing_mode=reframing_mode or "shot_stable",
        ),
    )


@registry.tool(
    name="panelflow_reels_generate_subtitles",
    description="Compile animated word-by-word karaoke ASS subtitles from dialogue transcript.",
    input_schema=_schema(
        {
            "transcript": {"type": "string", "description": "Narration or dialogue transcript text"},
            "hook": {"type": "string", "description": "Optional top hook text displayed in the first 2.5 seconds"},
            "audio_path": {"type": "string", "description": "Optional audio wav path for Whisper word alignment"},
            "duration_sec": {"type": "number", "description": "Total duration of speech in seconds"},
        },
        ["transcript"],
    ),
    domain="chronoflow",
)
async def reels_generate_subtitles(
    transcript: str,
    hook: str | None = None,
    audio_path: str | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    return await bridge.post(
        f"{_BASE}/generate_subtitles",
        _body(
            transcript=transcript,
            hook=hook or "",
            audio_path=audio_path,
            duration_sec=duration_sec,
        ),
    )
