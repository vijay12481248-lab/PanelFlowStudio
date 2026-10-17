"""
Core VisualTimeline, MotionScene, and Shot data models for PanelFlow Motion Director.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import uuid

from engine.motion.models.camera import NormalizedRect, CameraState, TargetResolution
from engine.motion.models.enums import (
    MotionType,
    EasingFunction,
    TimelineSourceType,
)
from engine.motion.models.effects import EffectInstruction
from engine.motion.models.transitions import TransitionInstruction
from engine.motion.models.cues import FocusTarget, CaptionCue, AnnotationCue
from engine.motion.models.layers import LayerInstruction
from engine.motion.models.warnings import MotionWarning
from engine.motion.models.input_contract import MotionStyleProfile


class Shot(BaseModel):
    """
    Individual cinematic camera shot within the visual timeline.
    Inspectable, editable, and deterministic.
    """
    shot_id: str = Field(default_factory=lambda: f"shot_{uuid.uuid4().hex[:8]}")
    scene_id: str
    beat_id: Optional[str] = None
    sequence_in_scene: int = 1
    sequence_global: int = 1

    source_asset_id: str
    source_panel_id: Optional[str] = None

    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)

    # Frame/crop region of the source visual asset used
    frame_region: NormalizedRect = Field(default_factory=lambda: NormalizedRect(x=0.0, y=0.0, width=1.0, height=1.0))

    # Camera movement instructions
    camera_start: CameraState = Field(default_factory=CameraState)
    camera_end: CameraState = Field(default_factory=CameraState)
    easing: EasingFunction = EasingFunction.EASE_IN_OUT
    motion_type: MotionType = MotionType.STATIC_HOLD

    # Focus and framing targets
    focus_targets: List[FocusTarget] = Field(default_factory=list)

    # Multi-layer / 2.5D instructions
    layer_instructions: List[LayerInstruction] = Field(default_factory=list)

    # Visual effects
    effect_instructions: List[EffectInstruction] = Field(default_factory=list)

    # In/Out transitions
    transition_in: TransitionInstruction = Field(default_factory=TransitionInstruction.hard_cut)
    transition_out: TransitionInstruction = Field(default_factory=TransitionInstruction.hard_cut)

    # Speech captions and annotations
    caption_cues: List[CaptionCue] = Field(default_factory=list)
    annotations: List[AnnotationCue] = Field(default_factory=list)

    # Explainability & audit metadata
    planning_metadata: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    locked: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, round(self.end_time - self.start_time, 4))


class MotionScene(BaseModel):
    """
    Scene-level grouping of shots aligning to NarrativeIR Scene boundaries.
    """
    scene_id: str
    sequence: int = 1
    title: str = ""
    start_time: float = Field(..., ge=0.0)
    end_time: float = Field(..., ge=0.0)
    shots: List[Shot] = Field(default_factory=list)
    location_id: Optional[str] = None
    character_ids: List[str] = Field(default_factory=list)

    @property
    def duration(self) -> float:
        return max(0.0, round(self.end_time - self.start_time, 4))


class VisualTimeline(BaseModel):
    """
    Complete render-ready visual timeline output by Motion Director.
    Serialized directly to JSON for renderer handoff.
    """
    timeline_id: str = Field(default_factory=lambda: f"vtl_{uuid.uuid4().hex[:8]}")
    project_id: str
    version: str = "1.0"
    timeline_source: TimelineSourceType = TimelineSourceType.REAL_AUDIO_TIMELINE
    total_duration_sec: float = Field(..., ge=0.0)
    target_resolution: TargetResolution = Field(default_factory=TargetResolution.standard_1080p)
    style_profile: MotionStyleProfile = Field(default_factory=MotionStyleProfile.subtle)
    scenes: List[MotionScene] = Field(default_factory=list)
    total_shots: int = 0
    warnings: List[MotionWarning] = Field(default_factory=list)
    hash: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def all_shots(self) -> List[Shot]:
        shots = []
        for scene in self.scenes:
            shots.extend(scene.shots)
        return shots

    def find_shot_by_id(self, shot_id: str) -> Optional[Shot]:
        for s in self.all_shots():
            if s.shot_id == shot_id:
                return s
        return None

    def find_shot_at_time(self, time_sec: float) -> Optional[Shot]:
        for s in self.all_shots():
            if s.start_time <= time_sec < s.end_time:
                return s
        return None

    def to_debug_string(self) -> str:
        lines = []
        lines.append("=" * 80)
        lines.append(f"VISUAL TIMELINE: {self.timeline_id} (Project: {self.project_id})")
        lines.append(f"Clock Duration:  {self.total_duration_sec:.2f}s | Source: {self.timeline_source.value}")
        lines.append(f"Resolution:      {self.target_resolution.width}x{self.target_resolution.height} @ {self.target_resolution.fps}fps ({self.target_resolution.aspect_ratio})")
        lines.append(f"Style Profile:   {self.style_profile.preset.value} (max zoom: {self.style_profile.max_zoom}x)")
        lines.append(f"Total Scenes:    {len(self.scenes)} | Total Shots: {len(self.all_shots())}")
        if self.warnings:
            lines.append(f"Active Warnings: {len(self.warnings)}")
        lines.append("-" * 80)

        for sc in self.scenes:
            lines.append(f"\nSCENE {sc.sequence:02d} [{sc.scene_id}]: '{sc.title}' ({sc.start_time:.2f}s - {sc.end_time:.2f}s, duration: {sc.duration:.2f}s)")
            for sh in sc.shots:
                foc_str = f"Focus: {sh.focus_targets[0].focus_type.value}" if sh.focus_targets else "Focus: UNKNOWN"
                if sh.focus_targets and sh.focus_targets[0].speaker_id:
                    foc_str += f" ({sh.focus_targets[0].speaker_id})"
                caps = f" | Subtitle: \"{sh.caption_cues[0].text[:30]}...\"" if sh.caption_cues else ""
                lines.append(
                    f"  {sh.start_time:05.2f}s - {sh.end_time:05.2f}s [{sh.duration:4.2f}s] "
                    f"Shot #{sh.sequence_global:02d} ({sh.shot_id}) | "
                    f"Asset: {sh.source_asset_id:<12} | "
                    f"Motion: {sh.motion_type.value:<16} | "
                    f"Zoom: {sh.camera_start.zoom:.2f} -> {sh.camera_end.zoom:.2f} | "
                    f"{foc_str}{caps}"
                )
                if sh.effect_instructions:
                    for eff in sh.effect_instructions:
                        lines.append(f"     -> Effect: {eff.effect_type.value} (intensity: {eff.intensity:.2f})")
        lines.append("=" * 80)
        return "\n".join(lines)
