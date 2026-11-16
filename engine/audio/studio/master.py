"""Broadcast Loudness Mastering: Dual-Standard (-14 LUFS YouTube / -23 LUFS EBU R128),
lookahead true-peak limiting, and broadcast compliance verification.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal

from engine.audio.studio.mix import _FFMPEG, SR, _run, measure_loudness, render_roles
from engine.audio.studio.plan import SoundPlan
from engine.chronoflow.deliver import loudnorm_filter

MasterStandard = Literal["youtube", "ebu_r128", "custom"]

STANDARDS: dict[str, dict[str, Any]] = {
    "youtube": {
        "target_lufs": -14.0,
        "max_true_peak_db": -1.0,
        "tolerance_lufs": 0.5,
        "lra_target": 11.0,
        "description": "YouTube & Web Video Standard (-14 LUFS, -1.0 dBTP)",
    },
    "ebu_r128": {
        "target_lufs": -23.0,
        "max_true_peak_db": -1.0,
        "tolerance_lufs": 0.5,
        "max_short_term_lufs": -18.0,
        "lra_target": 11.0,
        "description": "EBU R128 Broadcast Standard (-23 LUFS, -1.0 dBTP)",
    },
    "custom": {
        "target_lufs": -16.0,
        "max_true_peak_db": -1.0,
        "tolerance_lufs": 0.5,
        "lra_target": 11.0,
        "description": "Custom Target Loudness",
    },
}


def get_standard_spec(standard: MasterStandard = "youtube", custom_target_lufs: float | None = None) -> dict[str, Any]:
    spec = dict(STANDARDS.get(standard, STANDARDS["youtube"]))
    if standard == "custom" and custom_target_lufs is not None:
        spec["target_lufs"] = float(custom_target_lufs)
        spec["description"] = f"Custom Target Loudness ({custom_target_lufs:.1f} LUFS)"
    elif custom_target_lufs is not None:
        spec["target_lufs"] = float(custom_target_lufs)
    return spec


def check_compliance(measured: dict[str, float], standard: MasterStandard = "youtube",
                     custom_target_lufs: float | None = None) -> dict[str, Any]:
    """Check whether a measured loudness profile complies with the chosen broadcast standard."""
    spec = get_standard_spec(standard, custom_target_lufs)
    target = spec["target_lufs"]
    tol = spec.get("tolerance_lufs", 0.5)
    max_tp = spec.get("max_true_peak_db", -1.0)

    actual_i = measured.get("integrated_lufs", -120.0)
    actual_tp = measured.get("true_peak_db", -120.0)

    # If the file is completely silent (-inf / -120), it cannot meet broadcast loudness
    is_silent = actual_i <= -100.0

    i_ok = not is_silent and (abs(actual_i - target) <= tol)
    tp_ok = actual_tp <= (max_tp + 0.1)  # small 0.1 dB float tolerance

    compliant = i_ok and tp_ok

    reasons: list[str] = []
    if is_silent:
        reasons.append("Audio is completely silent")
    elif not i_ok:
        reasons.append(f"Integrated loudness {actual_i:.1f} LUFS is outside target {target:.1f} ± {tol:.1f} LUFS")
    if not tp_ok:
        reasons.append(f"True-peak {actual_tp:.1f} dBTP exceeds maximum ceiling {max_tp:.1f} dBTP")

    return {
        "compliant": compliant,
        "standard": standard,
        "target_lufs": target,
        "measured_lufs": actual_i,
        "measured_true_peak_db": actual_tp,
        "max_true_peak_db": max_tp,
        "lra": measured.get("lra", 0.0),
        "reasons": reasons,
    }


def master_audio(
    input_wav: Path,
    out_wav: Path,
    standard: MasterStandard = "youtube",
    custom_target_lufs: float | None = None,
    video_in: Path | None = None,
    out_video: Path | None = None,
) -> dict[str, Any]:
    """Master an existing WAV to the broadcast standard using lookahead true-peak limiting and 2-pass loudnorm."""
    input_wav = Path(input_wav)
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    spec = get_standard_spec(standard, custom_target_lufs)
    target_lufs = spec["target_lufs"]

    # alimiter: true peak ceiling at 0.891 (~ -1.0 dBFS), attack 5ms, release 50ms, auto-gain compensation asc=1
    limit = "alimiter=limit=0.89:attack=5:release=50:asc=1"

    # Pass 1: measure with loudnorm json print
    first = _run([
        _FFMPEG, "-hide_banner", "-nostats", "-i", str(input_wav),
        "-af", f"{limit},{loudnorm_filter(target_lufs, None)}:print_format=json",
        "-f", "null", "-"
    ])
    stats_json = first[first.rfind("{"):first.rfind("}") + 1]
    if not stats_json:
        raise ValueError("Loudness analysis failed: no valid stats output from FFmpeg")
    stats = json.loads(stats_json)

    if not math.isfinite(float(stats.get("input_i", "-inf"))):
        raise ValueError("Nothing to master: input audio contains only silence or non-finite values")

    # Pass 2: apply true-peak limiting + linear loudnorm normalization
    _run([
        _FFMPEG, "-v", "error", "-y", "-i", str(input_wav),
        "-af", f"{limit},{loudnorm_filter(target_lufs, stats)}",
        "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s24le", str(out_wav)
    ])

    measured = measure_loudness(out_wav)
    compliance = check_compliance(measured, standard, target_lufs)

    if video_in and out_video:
        out_video = Path(out_video)
        out_video.parent.mkdir(parents=True, exist_ok=True)
        _run([
            _FFMPEG, "-v", "error", "-y", "-i", str(video_in), "-i", str(out_wav),
            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(out_video)
        ])

    return {
        "out_wav": str(out_wav),
        "out_video": str(out_video) if video_in and out_video else None,
        "standard": standard,
        "target_lufs": target_lufs,
        "loudness": measured,
        "compliance": compliance,
    }


def master_plan(
    plan: SoundPlan,
    out_wav: Path,
    standard: MasterStandard = "youtube",
    custom_target_lufs: float | None = None,
    video_in: Path | None = None,
    out_video: Path | None = None,
    roles: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Renders the premix of a SoundPlan and masters it to the specified broadcast loudness standard."""
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="audiostudio-master-") as tmp:
        tmp_dir = Path(tmp)
        stem_dict = roles or render_roles(plan, tmp_dir)
        premix = stem_dict["premix"]
        res = master_audio(premix, out_wav, standard, custom_target_lufs, video_in, out_video)

    return res
