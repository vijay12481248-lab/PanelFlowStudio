"""Verification test for Task 4: Corrected Semantic Alignment Requirements."""
import pytest
from typing import Dict, List, Any, Tuple


def validate_semantic_cues_corrected(
    scenes: List[Dict[str, Any]],
    narration_clips: List[Dict[str, Any]],
    require_silence_at_cuts: bool = False
) -> Tuple[List[str], List[str]]:
    """
    Corrected validator conforming to Task 4:
    1. Does NOT require visual transitions to occur exclusively during acoustic silence.
    2. Supports narration-driven panel changes at verified word/event timestamps.
    3. For sequential multi-panel narration (1:N), validates each visual span separately
       (does NOT require all panels to remain visible across the whole segment).
    4. Treats Whisper timestamps as estimates without raising false-positive blocking errors.
    """
    issues = []
    warnings = []

    # Map visual presence per panel: panel_id -> list of (start_sec, end_sec)
    panel_presence: Dict[str, List[Tuple[float, float]]] = {}
    for sc in scenes:
        sc_start = float(sc.get("start_time_sec", 0))
        sc_dur = float(sc.get("duration_sec", 0))
        sc_end = sc_start + sc_dur
        for layer in sc.get("layers", []):
            p_id = layer.get("source_panel_id")
            if p_id:
                panel_presence.setdefault(p_id, []).append((sc_start, sc_end))

    for clip in narration_clips:
        c_id = clip.get("id", "unnamed")
        c_start = float(clip.get("start_time_sec", 0))
        c_dur = float(clip.get("duration_sec", 0))
        c_end = c_start + c_dur
        cues = clip.get("speech_cues", [])

        if not cues:
            if not clip.get("allow_unanchored", False):
                warnings.append(f"Clip '{c_id}' has no speech cues; alignment is unverified.")
            continue

        for idx, cue in enumerate(cues):
            cue_start = c_start + float(cue.get("start_sec", 0))
            cue_end = c_start + float(cue.get("end_sec", 0))
            cue_panels = cue.get("panel_ids", [])
            is_estimated = cue.get("timestamp_source") == "whisper_estimate"

            if not cue_panels and not clip.get("allow_unanchored"):
                issues.append(f"Clip '{c_id}' cue {idx} has no panel references.")
                continue

            # Task 4 Requirement 3: Validate each span separately for sequential multi-panel
            for pid in cue_panels:
                intervals = panel_presence.get(pid, [])
                # Tolerance is broader for estimated timestamps (100ms) than verified ones (33ms)
                tolerance = 0.100 if is_estimated else 0.033
                covered = any(
                    iv_start <= cue_start + tolerance and iv_end >= cue_end - tolerance
                    for iv_start, iv_end in intervals
                )
                if not covered:
                    issues.append(
                        f"Clip '{c_id}' cue {idx} (span {cue_start:.2f}-{cue_end:.2f}s) "
                        f"is not covered by panel '{pid}'."
                    )

            if is_estimated:
                warnings.append(
                    f"Clip '{c_id}' cue {idx} uses Whisper estimated timestamps; treat as provisional."
                )

    return issues, warnings


def test_sequential_multi_panel_validates_each_span_separately():
    """
    Verifies that for a 1:N narration clip (e.g. 0-8s take), Panel A is shown 0-4s and Panel B 4-8s.
    The validator must pass this as completely valid, without demanding Panel A stay visible until 8s.
    """
    scenes = [
        {
            "id": "scene_A",
            "start_time_sec": 0.0,
            "duration_sec": 4.0,
            "layers": [{"type": "panel", "source_panel_id": "panel_A"}]
        },
        {
            "id": "scene_B",
            "start_time_sec": 4.0,
            "duration_sec": 4.0,
            "layers": [{"type": "panel", "source_panel_id": "panel_B"}]
        }
    ]

    # One single 8s narration clip covering both panels sequentially
    narration_clips = [
        {
            "id": "clip_seq_1",
            "start_time_sec": 0.0,
            "duration_sec": 8.0,
            "speech_cues": [
                {
                    "id": "cue_0",
                    "start_sec": 0.0,
                    "end_sec": 4.0,
                    "panel_ids": ["panel_A"],
                    "timestamp_source": "whisper_estimate"
                },
                {
                    "id": "cue_1",
                    "start_sec": 4.0,
                    "end_sec": 8.0,
                    "panel_ids": ["panel_B"],
                    "timestamp_source": "whisper_estimate"
                }
            ]
        }
    ]

    issues, warnings = validate_semantic_cues_corrected(scenes, narration_clips)
    assert len(issues) == 0, f"Expected zero semantic issues for sequential multi-panel, got: {issues}"
    assert len(warnings) == 2, "Expected warnings noting Whisper estimated timestamps"


def test_narration_driven_mid_speech_panel_cut():
    """
    Verifies that panel cut at t=3.25s during active speech is valid
    without requiring acoustic silence at the transition point.
    """
    scenes = [
        {
            "id": "scene_1",
            "start_time_sec": 0.0,
            "duration_sec": 3.25,
            "layers": [{"type": "panel", "source_panel_id": "panel_1"}]
        },
        {
            "id": "scene_2",
            "start_time_sec": 3.25,
            "duration_sec": 4.75,
            "layers": [{"type": "panel", "source_panel_id": "panel_2"}]
        }
    ]

    narration_clips = [
        {
            "id": "clip_continuous",
            "start_time_sec": 0.0,
            "duration_sec": 8.0,
            "speech_cues": [
                {
                    "id": "phrase_1",
                    "start_sec": 0.0,
                    "end_sec": 3.25,
                    "panel_ids": ["panel_1"],
                    "timestamp_source": "word_timestamp"
                },
                {
                    "id": "phrase_2",
                    "start_sec": 3.25,
                    "end_sec": 8.0,
                    "panel_ids": ["panel_2"],
                    "timestamp_source": "word_timestamp"
                }
            ]
        }
    ]

    issues, warnings = validate_semantic_cues_corrected(scenes, narration_clips)
    assert len(issues) == 0, f"Word timestamp cut during active speech must be valid: {issues}"
