"""Quality Decision Engine: Multi-Witness Evidence Fusion & Scoring."""
from __future__ import annotations

import time
from typing import List, Optional
from engine.inspector.schema import DecisionStatus, DefectRecord, InspectorConfig, QualityDecision


class QualityDecisionEngine:
    """
    Fuses deterministic CV metrics (DWPose, YuNet/SFace) and semantic VLM review.
    Computes normalized quality score (0-100) and routes to PASS, RETRY, or MANUAL REVIEW.
    """

    def __init__(self, config: Optional[InspectorConfig] = None):
        self.config = config or InspectorConfig()

    def evaluate(
        self,
        defects: List[DefectRecord],
        people_count: Optional[int] = None,
        faces_count: int = 0,
        hands_count: Optional[int] = None,
        seconds: float = 0.0,
    ) -> QualityDecision:
        """
        Fuses all defect records, calculates composite score, and outputs decision.
        """
        score = 100.0
        penalties = {
            "severe": 30.0,
            "moderate": 18.0,
            "minor": 8.0,
        }

        # Deduplicate defects with identical category and tile
        seen_keys = set()
        unique_defects: List[DefectRecord] = []
        for d in defects:
            key = (d.category, d.tile, round(d.bbox[0], 2) if d.bbox else None)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_defects.append(d)

        # Apply weighted penalties
        for d in unique_defects:
            p = penalties.get(d.severity, 15.0) * d.confidence
            score -= p

        overall_score = max(0.0, min(100.0, round(score, 1)))
        has_severe = any(d.severity == "severe" for d in unique_defects)

        # Decision thresholding with severe defect gate
        if overall_score < self.config.retry_threshold:
            status: DecisionStatus = "MANUAL_REVIEW"
        elif overall_score >= self.config.pass_threshold and not has_severe:
            status = "PASS"
        else:
            status = "RETRY"

        clean = len(unique_defects) == 0 and status == "PASS"

        # Construct concise summary
        if clean:
            summary = f"PASS ({overall_score:.0f}/100): Image clean, anatomy verified, 0 defects detected."
        else:
            categories = list({d.category for d in unique_defects})
            summary = (
                f"{status} ({overall_score:.0f}/100): Found {len(unique_defects)} defect(s) "
                f"[{', '.join(categories)}]. Action: {unique_defects[0].recommended_action.upper()}."
            )

        return QualityDecision(
            overall_score=overall_score,
            status=status,
            clean=clean,
            defects=unique_defects,
            people_detected=people_count,
            faces_detected=faces_count,
            hands_detected=hands_count,
            summary=summary,
            seconds=round(seconds, 2),
        )
