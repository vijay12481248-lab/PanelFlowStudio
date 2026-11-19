"""Unit tests for Phase 1: Canonical Schemas, Scoring Formulas, and Audit Persistence."""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from engine.inspector.decision import QualityDecisionEngine
from engine.inspector.schema import (
    DefectRecord,
    FaceDetectionResult,
    InspectorConfig,
    QualityDecision,
    TemporalDefectRecord,
    VideoQualityDecision,
)


def test_defect_record_bbox_clamping_and_validation():
    """Bbox coordinates should clamp to [0.0, 1.0] and auto-order x1 <= x2 and y1 <= y2."""
    # Out of bounds coordinates that should be clamped
    d = DefectRecord(
        category="extra_hands",
        bbox=(-0.1, 1.2, 0.8, -0.05),
        confidence=0.95,
        severity="severe",
    )
    assert d.bbox is not None
    x1, y1, x2, y2 = d.bbox
    assert x1 == 0.0
    assert y1 == 0.0
    assert x2 == 0.8
    assert y2 == 1.0

    # Invalid bbox format should raise ValidationError
    with pytest.raises(ValidationError):
        DefectRecord(category="extra_hands", bbox=[0.1, 0.2])  # Less than 4 elements


def test_schema_serialization_roundtrip():
    """Verify QualityDecision and DefectRecords support 100% loss-free JSON roundtrip."""
    original = QualityDecision(
        overall_score=78.5,
        status="RETRY",
        clean=False,
        defects=[
            DefectRecord(
                category="distorted_face",
                bbox=(0.2, 0.1, 0.4, 0.3),
                confidence=0.88,
                severity="moderate",
                evidence="Melted eye shape detected",
                recommended_action="inpaint",
            )
        ],
        people_detected=1,
        faces_detected=1,
        summary="RETRY: 1 defect found",
        seconds=0.45,
    )

    json_str = original.model_dump_json()
    reconstructed = QualityDecision.model_validate_json(json_str)

    assert reconstructed.overall_score == original.overall_score
    assert reconstructed.status == original.status
    assert reconstructed.clean is False
    assert len(reconstructed.defects) == 1
    assert reconstructed.defects[0].category == "distorted_face"
    assert reconstructed.defects[0].bbox == (0.2, 0.1, 0.4, 0.3)


def test_decision_engine_clean_pass():
    """Zero defects should yield a score of 100.0, status PASS, and clean=True."""
    engine = QualityDecisionEngine()
    decision = engine.evaluate(defects=[], people_count=1, faces_count=1, seconds=0.1)

    assert decision.overall_score == 100.0
    assert decision.status == "PASS"
    assert decision.clean is True
    assert decision.people_detected == 1
    assert "clean" in decision.summary.lower()


def test_decision_engine_severe_defect_gate():
    """A severe defect must prevent a PASS status even if overall score is above pass_threshold."""
    engine = QualityDecisionEngine(config=InspectorConfig(pass_threshold=80.0, retry_threshold=60.0))

    # A single severe defect with 0.5 confidence reduces score by 30 * 0.5 = 15 -> score = 85.0
    # Score 85.0 is >= pass_threshold (80.0), BUT has severe defect -> must route to RETRY
    severe_defect = DefectRecord(
        category="extra_hands",
        confidence=0.5,
        severity="severe",
        recommended_action="inpaint",
    )
    decision = engine.evaluate(defects=[severe_defect])

    assert decision.overall_score == 85.0
    assert decision.status == "RETRY"  # Blocked from PASS by severe gate
    assert decision.clean is False


def test_decision_engine_manual_review_threshold():
    """Severe cumulative defects dropping score below retry_threshold should route to MANUAL_REVIEW."""
    engine = QualityDecisionEngine(config=InspectorConfig(pass_threshold=85.0, retry_threshold=60.0))

    multiple_defects = [
        DefectRecord(category="extra_hands", severity="severe", confidence=1.0),   # -30
        DefectRecord(category="merged_bodies", severity="severe", confidence=1.0), # -30
    ]
    # Score = 100 - 60 = 40.0 < 60.0 -> MANUAL_REVIEW
    decision = engine.evaluate(defects=multiple_defects)

    assert decision.overall_score == 40.0
    assert decision.status == "MANUAL_REVIEW"
    assert decision.clean is False


def test_decision_engine_deduplication():
    """Duplicate defect reports on the same category and tile should be deduplicated."""
    engine = QualityDecisionEngine()
    duplicate_defects = [
        DefectRecord(category="extra_hands", tile="zoom_hands", bbox=(0.1, 0.1, 0.3, 0.3)),
        DefectRecord(category="extra_hands", tile="zoom_hands", bbox=(0.1, 0.1, 0.3, 0.3)),
    ]
    decision = engine.evaluate(defects=duplicate_defects)

    assert len(decision.defects) == 1


def test_audit_persistence(tmp_path):
    """QualityDecision.save_audit persists formatted JSON to target path."""
    audit_file = tmp_path / "audits" / "sample_001_audit.json"
    decision = QualityDecision(
        overall_score=92.0,
        status="PASS",
        clean=True,
        defects=[],
        summary="Verified clean",
    )

    saved_path = decision.save_audit(audit_file)
    assert saved_path.is_file()

    data = json.loads(saved_path.read_text(encoding="utf-8"))
    assert data["overall_score"] == 92.0
    assert data["status"] == "PASS"
