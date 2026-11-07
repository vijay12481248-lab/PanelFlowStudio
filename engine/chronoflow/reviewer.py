"""ChronoFlow clip review: real measurements from `engine.original.clip_eval`, no invented scores.

`analyze_video_chunk` used to return constants (sharpness 94, lighting 96, ...) and keyword-triggered praise, so every clip was "APPROVED FOR MASTER CUT". It now runs the
evaluator (camera path, hard cuts, flicker, colour drift, stillness, audio) and returns what was measured. There is NO overall score or grade by design (`overall_score`
and `grade` are None); `verdict` says how many defects were confirmed / suspected, `flags` and `observations` carry the evidence with timestamps, and `not_checked` names
what the measurements cannot see (identity, objects, prompt adherence). ChronoFlow shots may move the camera, so camera moves are reported, not flagged.
"""
from __future__ import annotations

import os
from pathlib import Path

NOT_CHECKED = "identity, objects appearing or vanishing, prompt adherence, how the audio sounds"


def analyze_video_chunk(chunk_path, prompt="", shot_index=1, total_shots=3, prev_chunk_path=None):
    """Measured review of one generated chunk. `prompt` and `prev_chunk_path` are accepted for the callers' sake and not used for any score."""
    chunk_file = Path(chunk_path)
    base = {"shot_index": shot_index, "total_shots": total_shots, "overall_score": None, "grade": None, "measured": True, "not_checked": NOT_CHECKED}
    if not chunk_file.is_file():
        return {**base, "measured": False, "verdict": "NOT INSPECTED", "metrics": {}, "flags": [], "observations": ["The clip file is not available yet."],
                "recommendation": "Nothing was measured.", "timestamp": 0}
    from engine.original.clip_eval import evaluate

    try:
        rep = evaluate(chunk_file, expect_camera="any", expect_audio=True)
    except Exception as exc:  # an unreadable clip is itself a finding, not a pass
        return {**base, "measured": False, "verdict": "NOT INSPECTED", "metrics": {}, "flags": [], "observations": [f"The clip could not be analysed: {exc}"],
                "recommendation": "Open the clip and check it by eye.", "timestamp": os.path.getmtime(str(chunk_file))}
    flags = rep["flags"]
    confirmed = [f for f in flags if f["status"] == "confirmed"]
    suspected = [f for f in flags if f["status"] == "suspected"]
    cam = rep["camera"]
    if confirmed:
        verdict = f"{len(confirmed)} DEFECT(S) CONFIRMED" + (f", {len(suspected)} suspected" if suspected else "")
        rec = "Fix the confirmed defect(s) before the master cut (the correction loop: python -m engine.original.clip_loop)."
    elif suspected:
        verdict = f"CHECK: {len(suspected)} SUSPECTED"
        rec = "Look at the flagged moments before approving."
    else:
        verdict = "NO DEFECT FLAGGED"
        rec = f"Look at the clip yourself: not checked - {NOT_CHECKED}."
    obs = [f"{f['status']} ({f['axis']}" + (f" at {f['t']}s" if f.get("t") is not None else "") + f"): {f['evidence']}" for f in flags] or ["No measurement raised a flag."]
    return {**base, "verdict": verdict, "flags": flags, "observations": obs, "recommendation": rec, "timestamp": os.path.getmtime(str(chunk_file)),
            "metrics": {"seconds": rep["seconds"], "camera_zoom_pct": cam["zoom_pct"], "camera_pan_x_pct": cam["pan_x_pct"], "camera_pan_y_pct": cam["pan_y_pct"],
                        "motion": rep["motion"], "flicker": rep["flicker"], "colour_drift": rep["drift"]["max"], "hard_cuts_s": rep["cuts_s"],
                        "has_audio": rep["audio"].get("has_audio", False)}}
