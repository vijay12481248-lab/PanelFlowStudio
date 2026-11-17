"""Data models for Motion Bank, Ingest, Keypoint Tracking, and Guide System."""
from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from engine.acquisition.rights.models import RightsDeclaration, RightsStatus


class MotionSourceType(str, Enum):
    LOCAL_FILE = "LOCAL_FILE"
    YOUTUBE = "YOUTUBE"
    URL = "URL"
    SYNTHETIC = "SYNTHETIC"


class MotionSegment(BaseModel):
    """A continuous video cut segment without hard transitions."""
    segment_id: str
    start_sec: float
    end_sec: float
    duration_sec: float
    fps: float
    frame_count: int
    score: float = 1.0


class MotionIngestRecord(BaseModel):
    """Metadata record produced after ingesting and probing a video source."""
    source_uri: str
    source_type: MotionSourceType
    local_path: str
    sha256: str
    title: str
    duration_sec: float
    width: int
    height: int
    fps: float
    has_audio: bool
    rights: RightsDeclaration
    ingested_at: float = Field(default_factory=time.time)


class Keypoint2D(BaseModel):
    x: float
    y: float
    confidence: float


class FramePoseData(BaseModel):
    """Keypoint data for a single frame, normalized to [0, 1]."""
    frame_index: int
    timestamp_sec: float
    # Body: 18 keypoints (OpenPose standard: nose, neck, shoulders, elbows, wrists, hips, knees, ankles, eyes, ears)
    body: List[Tuple[float, float, float]] = Field(default_factory=list)
    # Hands: 21 left + 21 right = 42 keypoints
    left_hand: Optional[List[Tuple[float, float, float]]] = None
    right_hand: Optional[List[Tuple[float, float, float]]] = None
    # Face: 68 contour landmarks
    face: Optional[List[Tuple[float, float, float]]] = None
    # Bounding box of the tracked actor: [x_min, y_min, x_max, y_max] normalized
    bbox: Optional[Tuple[float, float, float, float]] = None


class MotionRecord(BaseModel):
    """Persistent Motion Bank entry stored in SQLite and referenced by ChronoFlow."""
    id: str
    source_uri: str
    action_title: str
    action_summary: str = ""
    action_tags: List[str] = Field(default_factory=list)
    duration_sec: float
    fps: float
    frame_count: int
    resolution: Tuple[int, int]
    actor_track_id: int = 1
    # Relative or absolute file paths to generated assets
    keypoints_path: str
    control_video_path: str
    preview_video_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)
