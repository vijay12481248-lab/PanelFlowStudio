"""
Provider-neutral MotionDirectorInput contract, VisualSource, MasterAudioTimeline,
and MotionStyleProfile models for PanelFlow Motion Director.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid

from engine.motion.models.camera import NormalizedRect, TargetResolution
from engine.motion.models.enums import (
    MotionPreset,
    EasingFunction,
    SpeechBalloonPolicy,
    TimelineSourceType,
)
from engine.motion.models.overrides import MotionOverrides
from engine.story.models import (
    VideoScript,
    ScriptSegment,
    SceneEntity,
    StoryBeatEntity,
    CharacterEntity,
)


class VisualSource(BaseModel):
    """
    Normalized visual asset representation (manga/webtoon panel, splash illustration, video frame).
    """
    asset_id: str
    panel_id: Optional[str] = None
    page_id: Optional[str] = None
    sequence_global: int = 1
    file_path: Optional[str] = None
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    panel_bounds: Optional[NormalizedRect] = None
    character_bounding_boxes: Dict[str, NormalizedRect] = Field(
        default_factory=dict,
        description="Map of character_id to normalized bounding box inside this visual source"
    )
    speech_balloon_boxes: List[NormalizedRect] = Field(default_factory=list)
    reading_direction: str = "ltr"
    panel_type: str = "STANDARD"
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(self.height, 1)


class AudioInterval(BaseModel):
    """
    Authoritative time interval on the master audio timeline.
    """
    interval_id: str = Field(default_factory=lambda: f"aint_{uuid.uuid4().hex[:8]}")
    script_segment_id: Optional[str] = None
    speaker_character_id: Optional[str] = None
    text: str = ""
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    is_speech: bool = True
    audio_file_uri: Optional[str] = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)


class MasterAudioTimeline(BaseModel):
    """
    Master clock produced by Audio Director, authoritative for all motion cuts and camera timings.
    """
    timeline_id: str = Field(default_factory=lambda: f"mat_{uuid.uuid4().hex[:8]}")
    total_duration_sec: float = Field(..., ge=0.0)
    timeline_source: TimelineSourceType = TimelineSourceType.REAL_AUDIO_TIMELINE
    intervals: List[AudioInterval] = Field(default_factory=list)
    sample_rate: int = 44100
    channels: int = 2

    def find_interval_for_segment(self, segment_id: str) -> Optional[AudioInterval]:
        for iv in self.intervals:
            if iv.script_segment_id == segment_id:
                return iv
        return None

    def find_intervals_in_range(self, start_sec: float, end_sec: float) -> List[AudioInterval]:
        return [
            iv for iv in self.intervals
            if not (iv.end_time <= start_sec or iv.start_time >= end_sec)
        ]

    @classmethod
    def create_fixture(cls, intervals: List[AudioInterval]) -> "MasterAudioTimeline":
        max_t = max([iv.end_time for iv in intervals], default=0.0)
        return cls(
            total_duration_sec=round(max_t, 3),
            timeline_source=TimelineSourceType.DEVELOPMENT_TIMELINE_FIXTURE,
            intervals=intervals,
        )


class MotionStyleProfile(BaseModel):
    """
    Configurable motion intensity and aesthetic pacing parameters.
    """
    profile_id: str = "subtle_default"
    preset: MotionPreset = MotionPreset.SUBTLE
    max_zoom: float = Field(default=1.20, ge=1.0, le=2.5)
    min_zoom: float = Field(default=1.00, ge=0.5, le=1.5)
    max_pan_distance: float = Field(default=0.20, ge=0.0, le=0.8)
    movement_speed: float = Field(default=1.0, ge=0.2, le=3.0)
    min_shot_duration: float = Field(default=1.5, ge=0.5, le=5.0)
    comfortable_dialogue_min: float = Field(default=2.5, ge=1.0, le=10.0)
    comfortable_dialogue_max: float = Field(default=6.0, ge=2.0, le=20.0)
    establishing_shot_duration: float = Field(default=3.0, ge=1.0, le=8.0)
    reaction_hold_duration: float = Field(default=1.2, ge=0.4, le=4.0)
    transition_duration: float = Field(default=0.5, ge=0.0, le=2.0)
    parallax_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    effect_intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    camera_easing: EasingFunction = EasingFunction.EASE_IN_OUT
    speech_balloon_policy: SpeechBalloonPolicy = SpeechBalloonPolicy.BALANCED

    @classmethod
    def subtle(cls) -> "MotionStyleProfile":
        return cls(
            profile_id="preset_subtle",
            preset=MotionPreset.SUBTLE,
            max_zoom=1.15,
            max_pan_distance=0.15,
            camera_easing=EasingFunction.SMOOTHSTEP,
            transition_duration=0.4,
            effect_intensity=0.3,
        )

    @classmethod
    def cinematic(cls) -> "MotionStyleProfile":
        return cls(
            profile_id="preset_cinematic",
            preset=MotionPreset.CINEMATIC,
            max_zoom=1.25,
            max_pan_distance=0.25,
            camera_easing=EasingFunction.EASE_IN_OUT,
            transition_duration=0.6,
            effect_intensity=0.6,
        )

    @classmethod
    def energetic(cls) -> "MotionStyleProfile":
        return cls(
            profile_id="preset_energetic",
            preset=MotionPreset.ENERGETIC,
            max_zoom=1.35,
            max_pan_distance=0.35,
            movement_speed=1.4,
            min_shot_duration=1.0,
            camera_easing=EasingFunction.EASE_OUT,
            transition_duration=0.3,
            effect_intensity=0.8,
        )

    @classmethod
    def minimal(cls) -> "MotionStyleProfile":
        return cls(
            profile_id="preset_minimal",
            preset=MotionPreset.MINIMAL,
            max_zoom=1.05,
            max_pan_distance=0.08,
            movement_speed=0.6,
            min_shot_duration=2.0,
            camera_easing=EasingFunction.SMOOTHSTEP,
            transition_duration=0.5,
            effect_intensity=0.1,
        )


class MotionDirectorInput(BaseModel):
    """
    Comprehensive input package supplied to MotionDirector.
    """
    project_id: str
    script: VideoScript
    visual_sources: List[VisualSource]
    master_audio_timeline: MasterAudioTimeline
    scenes: List[SceneEntity] = Field(default_factory=list)
    beats: List[StoryBeatEntity] = Field(default_factory=list)
    characters: List[CharacterEntity] = Field(default_factory=list)
    target_resolution: TargetResolution = Field(default_factory=TargetResolution.standard_1080p)
    style_profile: MotionStyleProfile = Field(default_factory=MotionStyleProfile.subtle)
    manual_overrides: Optional[MotionOverrides] = None
    seed: int = 42
