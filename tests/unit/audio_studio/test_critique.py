"""Unit tests for Audio Studio acoustic critique and 1-click remediation engine."""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from engine.api.app import app
from engine.audio.studio.critique import (
    apply_remediations,
    critique_plan,
    measure_spectral_profile,
)
from engine.audio.studio.measure import measure_take
from engine.audio.studio.plan import Cue, PlanStore, Provenance, SoundPlan, Take, Track

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SR = 48000
PROV = Provenance(source="test", licence="CC0")


def _write_wav(path: Path, x: np.ndarray) -> str:
    sf.write(str(path), np.asarray(x, dtype=np.float32), SR)
    return str(path)


def _tone(sec: float, f: float = 400.0, amp: float = 0.5) -> np.ndarray:
    return amp * np.sin(2 * np.pi * f * np.arange(int(SR * sec)) / SR)


def _make_take(tmp_path: Path, name: str, x: np.ndarray) -> Take:
    p = _write_wav(tmp_path / f"{name}.wav", x)
    m = measure_take(p)
    return Take(
        id=name,
        path=p,
        provenance=PROV,
        onset_s=m.onset_s,
        peak_s=m.peak_s,
        duration_s=m.duration_s,
        peak_db=m.peak_db,
        rms_db=m.rms_db,
        clipped_samples=m.clipped_samples,
    )


def test_measure_spectral_profile_bands(tmp_path):
    # 1. 40 Hz sub-bass
    sub_path = tmp_path / "sub.wav"
    _write_wav(sub_path, _tone(1.0, f=40.0))
    p_sub = measure_spectral_profile(sub_path)
    assert p_sub.sub_ratio > 0.70, f"Expected sub dominance, got {p_sub.sub_ratio}"

    # 2. 350 Hz mud
    mud_path = tmp_path / "mud.wav"
    _write_wav(mud_path, _tone(1.0, f=350.0))
    p_mud = measure_spectral_profile(mud_path)
    assert p_mud.mud_ratio > 0.70, f"Expected mud dominance, got {p_mud.mud_ratio}"

    # 3. 2000 Hz presence
    presence_path = tmp_path / "presence.wav"
    _write_wav(presence_path, _tone(1.0, f=2000.0))
    p_pres = measure_spectral_profile(presence_path)
    assert p_pres.presence_ratio > 0.70, f"Expected presence dominance, got {p_pres.presence_ratio}"

    # 4. 6000 Hz harsh sibilance
    harsh_path = tmp_path / "harsh.wav"
    _write_wav(harsh_path, _tone(1.0, f=6000.0))
    p_harsh = measure_spectral_profile(harsh_path)
    assert p_harsh.harsh_ratio > 0.70, f"Expected harsh dominance, got {p_harsh.harsh_ratio}"


def test_critique_sub_bass_and_spectral_mud(tmp_path):
    store = PlanStore(tmp_path / "store")
    plan = store.create("v.mp4", fps=24.0, duration=10.0)

    # Dialogue cue with 40 Hz sub rumble
    take_dialogue = _make_take(tmp_path, "take_dx", _tone(2.0, f=40.0))
    cue_dx = Cue(
        id="c_dx",
        track="dialogue",
        kind="dialogue",
        hit_t=1.0,
        t_in=1.0,
        takes=[take_dialogue],
        chosen_take=take_dialogue.id,
        status="ready",
        hpf_hz=0.0,
    )

    # SFX cue with 350 Hz mud
    take_sfx = _make_take(tmp_path, "take_sfx", _tone(1.0, f=350.0))
    cue_sfx = Cue(
        id="c_sfx",
        track="sfx",
        kind="thud",
        hit_t=5.0,
        takes=[take_sfx],
        chosen_take=take_sfx.id,
        status="ready",
        hpf_hz=0.0,
    )

    plan.cues = [cue_dx, cue_sfx]
    report = critique_plan(plan)

    rules = [iss.rule for iss in report.issues]
    assert "sub_rumble" in rules, f"Expected sub_rumble issue, found: {rules}"
    assert "spectral_mud" in rules, f"Expected spectral_mud issue, found: {rules}"
    assert len(report.remediations) >= 2


def test_critique_dialogue_masking_and_transient_collision(tmp_path):
    store = PlanStore(tmp_path / "store")
    plan = store.create("v.mp4", fps=24.0, duration=10.0)

    take_dx = _make_take(tmp_path, "dx_clip", _tone(3.0, f=1500.0))
    cue_dx = Cue(
        id="c_dx",
        track="dialogue",
        kind="speech",
        hit_t=2.0,
        t_in=2.0,
        takes=[take_dx],
        chosen_take=take_dx.id,
        status="ready",
    )

    # Loud music bed overlapping dialogue without ducking
    take_mx = _make_take(tmp_path, "mx_clip", _tone(6.0, f=400.0))
    cue_mx = Cue(
        id="c_mx",
        track="music",
        kind="loud_rock",
        hit_t=1.0,
        t_in=1.0,
        gain_db=-2.0,
        takes=[take_mx],
        chosen_take=take_mx.id,
        status="ready",
    )

    # Transient collision: two hits at 7.0s with same pan (0.0)
    take_hit1 = _make_take(tmp_path, "hit1", _tone(0.2, f=800.0))
    cue_hit1 = Cue(
        id="c_hit1",
        track="sfx",
        kind="punch",
        hit_t=7.0,
        pan=0.0,
        takes=[take_hit1],
        chosen_take=take_hit1.id,
        status="ready",
    )

    take_hit2 = _make_take(tmp_path, "hit2", _tone(0.2, f=1200.0))
    cue_hit2 = Cue(
        id="c_hit2",
        track="sfx",
        kind="grunt",
        hit_t=7.01,
        pan=0.0,
        takes=[take_hit2],
        chosen_take=take_hit2.id,
        status="ready",
    )

    plan.cues = [cue_dx, cue_mx, cue_hit1, cue_hit2]
    report = critique_plan(plan)

    rules = [iss.rule for iss in report.issues]
    assert "dialogue_masking" in rules, f"Expected dialogue_masking, found: {rules}"
    assert "transient_collision" in rules, f"Expected transient_collision, found: {rules}"


def test_apply_remediations_workflow(tmp_path):
    store = PlanStore(tmp_path / "store")
    plan = store.create("v.mp4", fps=24.0, duration=10.0)

    take_sfx = _make_take(tmp_path, "sfx_mud", _tone(1.0, f=300.0))
    cue_sfx = Cue(
        id="cue_target",
        track="sfx",
        kind="boom",
        hit_t=3.0,
        hpf_hz=0.0,
        takes=[take_sfx],
        chosen_take=take_sfx.id,
        status="ready",
    )
    plan.cues = [cue_sfx]

    report = critique_plan(plan)
    assert len(report.remediations) > 0
    rem = report.remediations[0]
    assert rem.action == "hpf"
    assert rem.value >= 90.0

    updated_plan, applied_ids = apply_remediations(plan, [rem.id])
    assert rem.id in applied_ids
    assert updated_plan.cue("cue_target").hpf_hz == rem.value


def test_critique_router_endpoints(tmp_path):
    # Setup temporary video
    video = tmp_path / "v.mp4"
    sf.write(str(tmp_path / "v.wav"), np.zeros(SR, dtype=np.float32), SR)
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=d=1:s=320x240:r=24",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "1",
                    "-c:v", "libx264", "-c:a", "aac", str(video)], check=True, capture_output=True)

    client = TestClient(app)

    # 1. Create plan
    res = client.post("/api/audio/studio/plans", json={"video_path": str(video)})
    assert res.status_code == 200
    pid = res.json()["id"]

    # 2. Add muddy cue
    mud_sound = tmp_path / "muddy_take.wav"
    _write_wav(mud_sound, _tone(0.5, f=320.0))
    client.put(f"/api/audio/studio/plans/{pid}", json={
        "cues": [{"id": "c_mud", "track": "sfx", "kind": "bass_thump", "hit_t": 0.5, "hpf_hz": 0}]
    })
    client.post(f"/api/audio/studio/plans/{pid}/cues/c_mud/import_file", json={
        "file_path": str(mud_sound),
        "label": "Muddy Bass"
    })

    # 3. Call /critique
    res = client.post(f"/api/audio/studio/plans/{pid}/critique")
    assert res.status_code == 200, res.text
    data = res.json()
    assert "overall_quality_score" in data
    assert "issues" in data
    assert "remediations" in data
    assert any(iss["rule"] == "spectral_mud" for iss in data["issues"])

    # 4. Call /critique/apply
    rem_ids = [r["id"] for r in data["remediations"]]
    res = client.post(f"/api/audio/studio/plans/{pid}/critique/apply", json={"remediation_ids": rem_ids})
    assert res.status_code == 200, res.text
    apply_data = res.json()
    assert len(apply_data["applied_ids"]) > 0
    updated_cue = next(c for c in apply_data["plan"]["cues"] if c["id"] == "c_mud")
    assert updated_cue["hpf_hz"] >= 100.0
