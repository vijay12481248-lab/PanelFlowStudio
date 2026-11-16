"""Acoustic inspection, spectral mud detection, speech masking analysis, and 1-click DSP remediation."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Callable, Literal

import numpy as np
import soundfile as sf
from pydantic import BaseModel, Field
from scipy.signal import welch

from engine.audio.studio.plan import Cue, SoundPlan, Track


class Remediation(BaseModel):
    id: str
    cue_id: str
    action: Literal["hpf", "lpf", "ducking", "pan", "gain"]
    value: float
    reason: str


class CritiqueIssue(BaseModel):
    id: str
    cue_id: str
    track: str
    rule: str
    severity: Literal["error", "warn", "info"]
    message: str
    remediation: Remediation | None = None


class SpectralProfile(BaseModel):
    sub_ratio: float = 0.0
    mud_ratio: float = 0.0
    presence_ratio: float = 0.0
    harsh_ratio: float = 0.0
    air_ratio: float = 0.0


class AudioCritiqueReport(BaseModel):
    plan_id: str
    overall_quality_score: int = 100
    spectral_balance: dict[str, SpectralProfile] = Field(default_factory=dict)
    issues: list[CritiqueIssue] = Field(default_factory=list)
    remediations: list[Remediation] = Field(default_factory=list)


def measure_spectral_profile(audio_path: Path | str, sr_target: int = 48000) -> SpectralProfile:
    """Analyze frequency distribution across octave bands using Welch PSD."""
    p = Path(audio_path)
    if not p.is_file():
        return SpectralProfile()

    try:
        data, sr = sf.read(str(p), dtype="float32", always_2d=True)
    except Exception:
        return SpectralProfile()

    if data.shape[0] == 0:
        return SpectralProfile()

    # Downmix to mono
    mono = np.mean(data, axis=1)
    if np.max(np.abs(mono)) < 1e-5:
        return SpectralProfile()

    nperseg = min(len(mono), 2048)
    if nperseg < 64:
        return SpectralProfile()

    freqs, psd = welch(mono, fs=sr, nperseg=nperseg)
    total_energy = float(np.sum(psd)) + 1e-12

    def _band_energy(low: float, high: float) -> float:
        mask = (freqs >= low) & (freqs < high)
        return float(np.sum(psd[mask]))

    sub = _band_energy(0, 60) / total_energy
    mud = _band_energy(200, 500) / total_energy
    presence = _band_energy(1000, 3500) / total_energy
    harsh = _band_energy(4000, 8000) / total_energy
    air = _band_energy(10000, 24000) / total_energy

    return SpectralProfile(
        sub_ratio=round(sub, 4),
        mud_ratio=round(mud, 4),
        presence_ratio=round(presence, 4),
        harsh_ratio=round(harsh, 4),
        air_ratio=round(air, 4),
    )


def critique_plan(
    plan: SoundPlan,
    render_cue_fn: Callable[[SoundPlan, Cue, Path], Path] | None = None,
    work_dir: Path | None = None,
) -> AudioCritiqueReport:
    """Analyze sound plan for spectral mud, dialogue masking, transient collisions, and acoustic balance."""
    issues: list[CritiqueIssue] = []
    remediations: list[Remediation] = []
    profiles: dict[str, SpectralProfile] = {}

    dialogue_cues = [c for c in plan.cues if c.track == "dialogue" and c.status == "ready"]
    music_cues = [c for c in plan.cues if c.track == "music" and c.status == "ready"]
    sfx_cues = [c for c in plan.cues if c.track in ("sfx", "foley") and c.status == "ready"]

    # 1. Cue-Level Acoustic Analysis
    for cue in plan.cues:
        if cue.status != "ready":
            continue
        take = cue.chosen()
        if not take or not take.path:
            continue

        take_path = Path(take.path)
        prof = measure_spectral_profile(take_path)
        profiles[cue.id] = prof

        hpf_val = cue.hpf_hz if cue.hpf_hz is not None else 0.0
        lpf_val = cue.lpf_hz if cue.lpf_hz is not None else 24000.0

        # Rule A: Sub-bass rumble in dialogue / foley (<60 Hz > 18% of energy without HPF)
        if cue.track in ("dialogue", "foley") and prof.sub_ratio > 0.18 and hpf_val < 80.0:
            rem_id = f"rem_{cue.id}_hpf_90"
            rem = Remediation(
                id=rem_id,
                cue_id=cue.id,
                action="hpf",
                value=90.0,
                reason=f"Sub-bass rumble detected ({prof.sub_ratio*100:.1f}% energy below 60 Hz). Apply 90 Hz low-cut filter to eliminate DC mud.",
            )
            issues.append(
                CritiqueIssue(
                    id=f"iss_{cue.id}_sub_rumble",
                    cue_id=cue.id,
                    track=cue.track,
                    rule="sub_rumble",
                    severity="warn",
                    message=f"Sub-bass rumble in {cue.track} cue ({prof.sub_ratio*100:.1f}% < 60 Hz).",
                    remediation=rem,
                )
            )
            remediations.append(rem)

        # Rule B: Excessive low-mid mud (200-500 Hz > 45% of energy)
        if cue.track in ("sfx", "music") and prof.mud_ratio > 0.45 and hpf_val < 100.0:
            rem_id = f"rem_{cue.id}_hpf_120"
            rem = Remediation(
                id=rem_id,
                cue_id=cue.id,
                action="hpf",
                value=120.0,
                reason=f"Low-mid mud buildup ({prof.mud_ratio*100:.1f}% between 200-500 Hz). Apply 120 Hz HPF to clear acoustic space.",
            )
            issues.append(
                CritiqueIssue(
                    id=f"iss_{cue.id}_spectral_mud",
                    cue_id=cue.id,
                    track=cue.track,
                    rule="spectral_mud",
                    severity="warn",
                    message=f"Spectral mud buildup in {cue.kind} ({prof.mud_ratio*100:.1f}% in 200-500 Hz).",
                    remediation=rem,
                )
            )
            remediations.append(rem)

        # Rule C: Harsh high-frequency sibilance (> 40% in 4-8 kHz)
        if prof.harsh_ratio > 0.40 and lpf_val > 10000.0:
            rem_id = f"rem_{cue.id}_lpf_7500"
            rem = Remediation(
                id=rem_id,
                cue_id=cue.id,
                action="lpf",
                value=7500.0,
                reason=f"Harsh resonance detected ({prof.harsh_ratio*100:.1f}% in 4-8 kHz). Apply 7.5 kHz low-pass filter to soften edge.",
            )
            issues.append(
                CritiqueIssue(
                    id=f"iss_{cue.id}_harsh_sibilance",
                    cue_id=cue.id,
                    track=cue.track,
                    rule="harsh_sibilance",
                    severity="warn",
                    message=f"Harsh high frequency energy in {cue.kind} ({prof.harsh_ratio*100:.1f}% in 4-8 kHz).",
                    remediation=rem,
                )
            )
            remediations.append(rem)

    # 2. Track & Masking Analysis: Dialogue Intelligibility vs Music/SFX
    for d_cue in dialogue_cues:
        d_hit = d_cue.hit_t or d_cue.t_in
        d_take = d_cue.chosen()
        d_dur = d_take.duration_s if d_take else 2.0
        d_end = d_hit + d_dur

        # Check overlapping music cues
        for m_cue in music_cues:
            m_hit = m_cue.hit_t or m_cue.t_in
            m_take = m_cue.chosen()
            m_dur = m_take.duration_s if m_take else plan.duration
            m_end = m_hit + m_dur

            # Overlap check
            if max(d_hit, m_hit) < min(d_end, m_end):
                m_track = next((t for t in plan.tracks if t.role == "music" or t.id == "music"), None)
                duck_active = bool(m_track and m_track.duck_under == "dialogue" and (m_track.ducking_depth_db is None or m_track.ducking_depth_db <= -8.0))
                if (not duck_active and m_cue.gain_db > -10.0) or (m_cue.gain_db > -3.0):
                    rem_id = f"rem_{m_cue.id}_gain_cut"
                    rem = Remediation(
                        id=rem_id,
                        cue_id=m_cue.id,
                        action="gain",
                        value=round(min(m_cue.gain_db - 4.5, -8.0), 1),
                        reason=f"Music overlaps dialogue at {d_hit:.2f}s with high energy. Lower music gain to prevent masking.",
                    )
                    issues.append(
                        CritiqueIssue(
                            id=f"iss_{m_cue.id}_masking_{d_cue.id}",
                            cue_id=m_cue.id,
                            track="music",
                            rule="dialogue_masking",
                            severity="error",
                            message=f"Music cue '{m_cue.kind}' masks dialogue at {d_hit:.2f}s.",
                            remediation=rem,
                        )
                    )
                    remediations.append(rem)

    # 3. Transient Collision Analysis: Two hits at same timestamp and center pan
    all_hits = [c for c in plan.cues if c.hit_t is not None and c.status == "ready"]
    for i in range(len(all_hits)):
        for j in range(i + 1, len(all_hits)):
            c1, c2 = all_hits[i], all_hits[j]
            if abs(c1.hit_t - c2.hit_t) < 0.040 and abs(c1.pan - c2.pan) < 0.15:
                # Collision: pan c1 left, c2 right
                rem_id = f"rem_{c2.id}_pan_offset"
                rem = Remediation(
                    id=rem_id,
                    cue_id=c2.id,
                    action="pan",
                    value=0.45,
                    reason=f"Transient collision between '{c1.kind}' and '{c2.kind}' at {c1.hit_t:.2f}s. Offset pan to +0.45 for spatial clarity.",
                )
                issues.append(
                    CritiqueIssue(
                        id=f"iss_{c1.id}_{c2.id}_collision",
                        cue_id=c2.id,
                        track=c2.track,
                        rule="transient_collision",
                        severity="info",
                        message=f"Transient collision with '{c1.kind}' at {c1.hit_t:.2f}s.",
                        remediation=rem,
                    )
                )
                remediations.append(rem)

    # Compute overall quality score (100 base, -12 per error, -5 per warn, -2 per info)
    deductions = sum(12 for iss in issues if iss.severity == "error") + \
                 sum(5 for iss in issues if iss.severity == "warn") + \
                 sum(2 for iss in issues if iss.severity == "info")
    score = max(20, min(100, 100 - deductions))

    return AudioCritiqueReport(
        plan_id=plan.id,
        overall_quality_score=score,
        spectral_balance=profiles,
        issues=issues,
        remediations=remediations,
    )


def apply_remediations(plan: SoundPlan, remediation_ids: list[str]) -> tuple[SoundPlan, list[str]]:
    """Apply selected remediation fixes directly to plan cues and return updated plan and applied ids."""
    report = critique_plan(plan)
    rem_map = {r.id: r for r in report.remediations}

    applied: list[str] = []
    cue_map = {c.id: c for c in plan.cues}

    for rid in remediation_ids:
        if rid not in rem_map:
            continue
        rem = rem_map[rid]
        cue = cue_map.get(rem.cue_id)
        if not cue:
            continue

        if rem.action == "hpf":
            cue.hpf_hz = max(cue.hpf_hz or 0.0, rem.value)
            applied.append(rid)
        elif rem.action == "lpf":
            cue.lpf_hz = min(cue.lpf_hz or 24000.0, rem.value)
            applied.append(rid)
        elif rem.action == "gain":
            cue.gain_db = rem.value
            applied.append(rid)
        elif rem.action == "pan":
            cue.pan = rem.value
            applied.append(rid)
        elif rem.action == "ducking":
            track = next((t for t in plan.tracks if t.role == cue.track or t.id == cue.track), None)
            if track:
                track.ducking_depth_db = rem.value
                applied.append(rid)

    return plan, applied
