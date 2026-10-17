"""
Compiled RenderPlan models for PanelFlow Production Renderer.
"""
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
import uuid

from engine.motion.models.camera import CameraState, NormalizedRect
from engine.motion.models.enums import MotionType, EasingFunction
from engine.motion.models.layers import LayerInstruction
from engine.motion.models.effects import EffectInstruction
from engine.motion.models.transitions import TransitionInstruction
from engine.motion.models.cues import CaptionCue
from engine.render.models.enums import ScalePolicy, BackgroundFillPolicy, MusicDurationPolicy
from engine.render.models.profiles import RenderProfile


class RenderShotPlan(BaseModel):
    """
    Frame-accurate instructions for rendering a single shot.
    """
    shot_id: str
    scene_id: str
    sequence_global: int
    source_asset_path: str
    start_frame: int = Field(..., ge=0)
    end_frame: int = Field(..., ge=0)
    total_frames: int = Field(..., gt=0)
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    duration: float = Field(..., gt=0.0)

    camera_start: CameraState
    camera_end: CameraState
    easing: EasingFunction = EasingFunction.EASE_IN_OUT
    motion_type: MotionType = MotionType.STATIC_HOLD
    frame_region: NormalizedRect = Field(default_factory=lambda: NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0))

    scale_policy: ScalePolicy = ScalePolicy.COVER
    fill_policy: BackgroundFillPolicy = BackgroundFillPolicy.BLACK

    layers: List[LayerInstruction] = Field(default_factory=list)
    effects: List[EffectInstruction] = Field(default_factory=list)
    transition_in: TransitionInstruction = Field(default_factory=TransitionInstruction.hard_cut)
    transition_out: TransitionInstruction = Field(default_factory=TransitionInstruction.hard_cut)
    captions: List[CaptionCue] = Field(default_factory=list)


class RenderAudioTrack(BaseModel):
    """
    Audio asset scheduled for mixing into the final audio stream.
    """
    track_id: str = Field(default_factory=lambda: f"trk_{uuid.uuid4().hex[:8]}")
    track_type: str = "dialogue"  # dialogue, music, sfx, ambience
    file_path: str
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    gain_db: float = 0.0
    ducking_intervals: List[Tuple[float, float, float]] = Field(
        default_factory=list,
        description="List of (start_sec, end_sec, attenuation_db) intervals applied to this track"
    )


class RenderPlan(BaseModel):
    """
    Fully compiled, deterministic render recipe ready for execution.
    """
    plan_id: str = Field(default_factory=lambda: f"rplan_{uuid.uuid4().hex[:8]}")
    project_id: str
    total_duration_sec: float = Field(..., ge=0.0)
    total_frames: int = Field(..., gt=0)
    profile: RenderProfile = Field(default_factory=RenderProfile.standard_1080p)
    shots: List[RenderShotPlan] = Field(default_factory=list)
    audio_tracks: List[RenderAudioTrack] = Field(default_factory=list)
    music_policy: MusicDurationPolicy = MusicDurationPolicy.LOOP
    hash: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def find_shot_at_frame(self, frame_index: int) -> Optional[RenderShotPlan]:
        if frame_index < 0 or frame_index >= self.total_frames:
            return None
        for shot in self.shots:
            if shot.start_frame <= frame_index < shot.end_frame:
                return shot
        if self.shots and frame_index >= self.shots[-1].start_frame:
            return self.shots[-1]
        return None
