"""
Data models for Automated Anime Review & Recap Video Production in PanelFlow Studio.
"""
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from pathlib import Path
from pydantic import BaseModel, Field


class ActType(str, Enum):
    HOOK_AND_SETUP = "HOOK_AND_SETUP"
    PLOT_DEVELOPMENT = "PLOT_DEVELOPMENT"
    KEY_BATTLE = "KEY_BATTLE"
    TURNING_POINT_CLIMAX = "TURNING_POINT_CLIMAX"
    REVIEWER_VERDICT = "REVIEWER_VERDICT"


class AnimeEpisodeSource(BaseModel):
    source_uri: str = Field(..., description="Local video file path or stream URL")
    series_title: str = Field(..., description="Name of the anime series, e.g. 'Solo Leveling'")
    episode_number: float = Field(default=1.0, description="Episode number, e.g. 1.0, 12.0")
    episode_title: Optional[str] = None
    duration_sec: float = 0.0
    width: int = 1920
    height: int = 1080
    fps: float = 24.0
    has_audio: bool = True
    audio_sample_rate: int = 44100
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class AnimeSceneCut(BaseModel):
    cut_id: str
    sequence: int
    start_sec: float
    end_sec: float
    duration_sec: float
    clip_path: Optional[str] = None
    keyframe_path: Optional[str] = None
    motion_score: float = 0.5
    has_speech: bool = False
    dialogue_transcript: Optional[str] = None
    is_opening_or_ending: bool = False


class ReviewStoryBeat(BaseModel):
    beat_id: str
    sequence: int
    act_type: ActType = ActType.PLOT_DEVELOPMENT
    voiceover_text: str = Field(..., description="Narrator/reviewer commentary script")
    emotion: str = "SERIOUS"
    assigned_cut_ids: List[str] = Field(default_factory=list, description="IDs of scene cuts to display")
    voice_audio_path: Optional[str] = None
    voice_duration_sec: float = 0.0
    video_start_offset: float = 0.0


class AnimeReviewConfig(BaseModel):
    source_video: str
    series_title: str
    episode_number: float = 1.0
    episode_title: Optional[str] = None
    target_review_duration_minutes: Optional[float] = None
    max_cut_length_sec: float = 4.5  # Prevents copyright detection and keeps dynamic pacing
    min_cut_length_sec: float = 2.0
    tts_voice: str = "am_michael"
    tts_speed: float = 1.0
    original_audio_duck_db: float = -18.0  # Subtle original anime BGM/SFX under voice
    crop_to_1080p: bool = True
    anti_copyright_transform: bool = True  # Subtle 1.02x scale, reframe, anti-content-ID
    output_dir: Optional[str] = None
    subtitles: bool = True


class AnimeReviewResult(BaseModel):
    series_title: str
    episode_number: float
    output_video_path: str
    video_duration_sec: float
    total_scene_cuts: int
    total_review_beats: int
    voice_voiceover_duration_sec: float
    youtube_metadata_path: Optional[str] = None
    created_at: float = 0.0
