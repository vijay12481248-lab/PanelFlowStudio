"""ChronoFlow Studio — Sliding Window Video Chaining Engine & AI Cinematography.

Integrates MiniMax Fast H3 video chaining with tail-frame extraction, FLF2V bridging,
character sheet reference consistency, FLUX.1 & Qwen-Image generation, canvas inpainting,
NLE timeline EDL mastering, and autonomous video chunk quality reviewing.
"""

from engine.chronoflow.pipeline import ChronoFlowPipeline, COMFY_INPUT_DIR, STUDIO_OUTPUT_DIR
from engine.chronoflow.supervisor import JobSupervisor
from engine.chronoflow.reviewer import analyze_video_chunk

__all__ = [
    "ChronoFlowPipeline",
    "JobSupervisor",
    "analyze_video_chunk",
    "COMFY_INPUT_DIR",
    "STUDIO_OUTPUT_DIR",
]
