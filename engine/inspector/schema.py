"""Canonical data schemas for AI Visual Quality Inspector & Auto-Correction System."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple
from pydantic import BaseModel, Field, field_validator

DefectSeverity = Literal["minor", "moderate", "severe"]
DefectAction = Literal["inpaint", "redraw", "manual"]
DecisionStatus = Literal["PASS", "RETRY", "MANUAL_REVIEW"]

DEFECT_CATEGORIES = (
    "extra_hands",
    "extra_limbs",
    "missing_hand",
    "distorted_face",
    "extra_head",
    "duplicate_character",
    "stray_text",
    "duplicate_object",
    "merged_bodies",
    "temporal_jitter",
    "identity_drift",
    "flickering_limbs",
    "scene_transition_error",
    "dropped_actor",
    "pose_missing",
)


class DefectRecord(BaseModel):
    """Structured evidence for a single visual or anatomical defect."""
    defect_id: str = Field(default_factory=lambda: f"def_{uuid.uuid4().hex[:8]}")
    category: str
    bbox: Optional[Tuple[float, float, float, float]] = None  # Normalised (x1, y1, x2, y2)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    severity: DefectSeverity = "moderate"
    evidence: str = ""
    recommended_action: DefectAction = "inpaint"
    tile: str = "whole"
    details: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("bbox", mode="before")
    @classmethod
    def clamp_and_validate_bbox(cls, v):
        if v is None:
            return None
        if isinstance(v, (list, tuple)) and len(v) == 4:
            x1 = max(0.0, min(1.0, float(v[0])))
            y1 = max(0.0, min(1.0, float(v[1])))
            x2 = max(0.0, min(1.0, float(v[2])))
            y2 = max(0.0, min(1.0, float(v[3])))
            if x1 > x2:
                x1, x2 = x2, x1
            if y1 > y2:
                y1, y2 = y2, y1
            return (round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4))
        raise ValueError("bbox must be a tuple of 4 normalized floats (x1, y1, x2, y2)")


class TemporalDefectRecord(BaseModel):
    """Structured evidence for temporal inconsistency, jitter, or identity drift in video."""
    defect_id: str = Field(default_factory=lambda: f"vdef_{uuid.uuid4().hex[:8]}")
    category: str
    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(ge=0.0)
    frame_indices: List[int] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    severity: DefectSeverity = "moderate"
    evidence: str = ""
    recommended_action: DefectAction = "redraw"  # "redraw" (shot redo) or "inpaint" (frame fix)
    details: Dict[str, Any] = Field(default_factory=dict)


class FaceDetectionResult(BaseModel):
    """Bounding box and landmark data for a single detected face."""
    bbox: Tuple[float, float, float, float]  # Normalised (x1, y1, x2, y2)
    confidence: float = Field(ge=0.0, le=1.0)
    landmarks: List[Tuple[float, float]] = Field(default_factory=list)  # (x, y) coordinates
    embedding: Optional[List[float]] = None  # 128-dim or 512-dim normalized feature vector


class QualityDecision(BaseModel):
    """Overall evaluation output, composite score, and pipeline routing decision for still images."""
    overall_score: float = Field(ge=0.0, le=100.0)
    status: DecisionStatus
    clean: bool = False
    defects: List[DefectRecord] = Field(default_factory=list)
    people_detected: Optional[int] = None
    faces_detected: int = 0
    hands_detected: Optional[int] = None
    summary: str = ""
    seconds: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def save_audit(self, file_path: str | Path) -> Path:
        """Persists canonical JSON audit trail for inspection lineage."""
        out_p = Path(file_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return out_p


class VideoQualityDecision(BaseModel):
    """Overall temporal evaluation output, consistency score, and decision for video sequences."""
    overall_score: float = Field(ge=0.0, le=100.0)
    status: DecisionStatus
    clean: bool = False
    defects: List[TemporalDefectRecord] = Field(default_factory=list)
    duration_sec: float = 0.0
    total_frames: int = 0
    fps: float = 24.0
    shots_detected: int = 1
    summary: str = ""
    seconds: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def save_audit(self, file_path: str | Path) -> Path:
        """Persists canonical JSON audit trail for temporal inspection lineage."""
        out_p = Path(file_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return out_p


class InspectorConfig(BaseModel):
    """Operational parameters, thresholds, and module toggles."""
    pass_threshold: float = 85.0
    retry_threshold: float = 60.0
    face_confidence: float = 0.60
    identity_similarity_threshold: float = 0.82
    jitter_velocity_threshold: float = 0.18  # Normalized Euclidean displacement per frame
    enable_vlm: bool = True
    enable_cv_topology: bool = True
    enable_face_check: bool = True
    max_inpaint_attempts: int = 2
    max_redraw_attempts: int = 3
