"""
Music Direction Plan and Generation Domain Models for PanelFlow Studio (Chapter 9).

Defines structured models for story-aware music direction, multi-scene cues,
candidate takes, and audio asset persistence.
"""
from __future__ import annotations

import time
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class MusicTakeRecord(BaseModel):
    """An immutable generated music take for a cue."""
    take_id: str
    cue_id: str
    project_id: str
    take_index: int
    audio_file_path: str
    audio_file_uri: str
    duration_sec: float
    sample_rate: int = 48000
    channels: int = 2
    format: str = "wav"
    file_size_bytes: int = 0
    checksum_sha256: str = ""
    prompt: str
    seed: int
    bpm: int = 85
    key_scale: str = "D Minor"
    time_signature: str = "4/4"
    model_id: str = "acestep-v15-turbo"
    inference_steps: int = 8
    guidance_scale: float = 7.0
    measured_peak_dbfs: float = -1.0
    measured_rms_dbfs: float = -18.0
    waveform_peaks: List[float] = Field(default_factory=list)
    approval_status: Literal["DRAFT", "APPROVED", "REJECTED"] = "DRAFT"
    created_at: float = Field(default_factory=time.time)
    generation_time_sec: float = 0.0


class MusicCuePlan(BaseModel):
    """A story-aware musical cue spanning one or more manga scenes."""
    cue_id: str
    title: str
    scene_ids: List[str]
    start_time_sec: float = 0.0
    end_time_sec: float = 10.0
    duration_sec: float = 10.0
    narrative_function: Literal[
        "opening_mystery",
        "character_discovery",
        "rising_threat",
        "confrontation",
        "emotional_resolution",
        "ambient_underscore",
        "transitional_stinger",
    ] = "ambient_underscore"
    emotional_direction: str = "mysterious and atmospheric"
    intensity: float = 0.5  # 0.0 (subtle) to 1.0 (climax)
    genre_style: str = "cinematic dark-fantasy underscore"
    instrumentation: List[str] = Field(
        default_factory=lambda: ["low strings", "crystal chimes", "subtle synth pad"]
    )
    tempo_bpm: int = 85
    tonal_center: str = "D Minor"
    time_signature: str = "4/4"
    instrumental: bool = True
    musical_continuity: str = "establishes harmonic theme"
    editable_prompt: str = ""
    selected_take_id: Optional[str] = None
    takes: List[MusicTakeRecord] = Field(default_factory=list)


class MusicDirectionPlan(BaseModel):
    """The complete project soundtrack plan structured across manga scenes."""
    plan_id: str
    project_id: str
    storyboard_id: Optional[str] = None
    overall_musical_theme: str = "Ancient crystal techno-magic and dark fantasy"
    harmonic_key: str = "D Minor / D Dorian"
    recommended_headroom_notes: str = (
        "Leave 2 kHz - 5 kHz acoustic space for dialogue, jump SFX, and resonance pulses. "
        "Maintain controlled dynamics and smooth motif development."
    )
    cues: List[MusicCuePlan] = Field(default_factory=list)
    total_score_duration_sec: float = 0.0
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class MusicGenerationRequest(BaseModel):
    """Request payload to trigger music synthesis."""
    cue_id: Optional[str] = None
    prompt: str
    audio_duration: float = 10.0
    bpm: int = 85
    key_scale: str = "D Minor"
    time_signature: str = "4/4"
    seed: Optional[int] = None
    use_random_seed: bool = True
    inference_steps: int = 8
    guidance_scale: float = 7.0
    model: str = "acestep-v15-turbo"
    thinking: bool = False


class MusicGenerationJob(BaseModel):
    """Active or historical music generation job."""
    job_id: str
    project_id: str
    cue_id: Optional[str] = None
    task_id: Optional[str] = None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    progress: float = 0.0
    progress_text: str = "Initializing..."
    error_message: Optional[str] = None
    request_params: Dict[str, Any] = Field(default_factory=dict)
    take: Optional[MusicTakeRecord] = None
    started_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None


class SFXCapabilityReport(BaseModel):
    """Honest capability report of local sound effect synthesis models."""
    local_ai_sfx_model_available: bool = False
    detected_models: List[str] = Field(default_factory=list)
    curated_sfx_library_available: bool = True
    available_categories: List[str] = Field(
        default_factory=lambda: [
            "movement",
            "impact",
            "magic",
            "ambient",
            "environmental",
            "character",
            "transitions",
        ]
    )
    notes: str = (
        "No dedicated local neural SFX generator (such as AudioLDM or AudioGen) is installed in C:\\Tools. "
        "In accordance with Chapter 9 engineering rules, PanelFlow uses its high-fidelity curated "
        "Sound Effects Library with precise timeline cues rather than mislabeling music fragments as SFX."
    )
